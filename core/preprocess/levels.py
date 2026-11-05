"""Logic level estimation: histogram two-peak estimate refined by stable-segment medians.

1. Rough levels: histogram of the record, Otsu split into two classes, the most populated bin of
   each class (bin centre). Good to a bin width - enough to place the hysteresis thresholds.
2. Edges are detected against the rough levels (hysteresis, see `edges.py`).
3. Refined levels: median of the samples of each logic state, excluding a guard band around every
   edge (the transition itself plus overshoot/ringing). The guard after an edge is
   max(POST_GUARD_EDGE_MULT x edge duration, POST_GUARD_FRACTION x segment length); before an edge it
   is max(PRE_GUARD_EDGE_MULT x edge duration, PRE_GUARD_FRACTION x segment length), where the edge
   duration is its 10-90 % span. The median of the remaining stable samples is precise to well below
   the noise sigma.
A record without a usable swing (no two levels separated by more than FLAT_NOISE_MULT x noise sigma, or
no edge at all) is "flat": Levels(low = high = median), and `detect_edges` then returns no edges.
"""

from __future__ import annotations

import numpy as np

from core.models import AnalysisSettings, Edge, EdgeKind, Levels, Waveform

from .edges import detect_edges_array
from .filters import signal_values

HIST_BINS = 256
FLAT_NOISE_MULT = 10.0  # rough swing must exceed this many noise sigmas
POST_GUARD_EDGE_MULT = 4.0
POST_GUARD_FRACTION = 0.25
PRE_GUARD_EDGE_MULT = 1.0
PRE_GUARD_FRACTION = 0.05
_MAD_TO_SIGMA = 1.0 / 0.6744897501960817
_REL_RESOLUTION = 1e-9  # a spread below this fraction of the magnitude is treated as constant


def estimate_noise_sigma(values: np.ndarray) -> float:
    """Robust white-noise sigma from first differences: MAD(diff) / 0.6745 / sqrt(2)."""
    if values.shape[0] < 3:
        return 0.0
    d = np.diff(values)
    mad = float(np.median(np.abs(d - np.median(d))))
    return mad * _MAD_TO_SIGMA / np.sqrt(2.0)


def rough_levels(values: np.ndarray) -> tuple[float, float]:
    """Two-peak histogram estimate (low, high). Equal values if the record is constant."""
    vmin = float(np.min(values))
    vmax = float(np.max(values))
    if not vmax - vmin > _REL_RESOLUTION * max(abs(vmin), abs(vmax)):
        return vmin, vmin  # constant up to floating-point resolution
    counts, bin_edges = np.histogram(values, bins=HIST_BINS, range=(vmin, vmax))
    centers = 0.5 * (bin_edges[:-1] + bin_edges[1:])
    c = counts.astype(np.float64)
    w0 = np.cumsum(c)
    w1 = w0[-1] - w0
    m0 = np.cumsum(c * centers)
    mu0 = m0 / np.maximum(w0, 1.0)
    mu1 = (m0[-1] - m0) / np.maximum(w1, 1.0)
    between = w0 * w1 * (mu0 - mu1) ** 2
    split = int(np.argmax(between[:-1]))  # class 0 = bins [0, split], class 1 = bins (split, end]
    lo_bin = int(np.argmax(counts[: split + 1]))
    hi_bin = split + 1 + int(np.argmax(counts[split + 1 :]))
    return float(centers[lo_bin]), float(centers[hi_bin])


def _edge_span(e: Edge) -> tuple[float, float]:
    """(start, end) of the transition: 10/90 % instants when known, else the 50 % instant."""
    pts = [e.t50_s] + [x for x in (e.t10_s, e.t90_s) if x is not None]
    return min(pts), max(pts)


def stable_masks(t: np.ndarray, edges: list[Edge]) -> tuple[np.ndarray, np.ndarray]:
    """Boolean masks (low, high) of samples in stable segments, guard bands around edges excluded."""
    n = t.shape[0]
    low = np.zeros(n, dtype=bool)
    high = np.zeros(n, dtype=bool)
    if not edges:
        return low, high
    spans = [_edge_span(e) for e in edges]
    for k in range(len(edges) + 1):
        prev = edges[k - 1] if k > 0 else None
        nxt = edges[k] if k < len(edges) else None
        seg_start = prev.t50_s if prev else float(t[0])
        seg_end = nxt.t50_s if nxt else float(t[-1])
        length = seg_end - seg_start
        if prev is not None:
            s0, s1 = spans[k - 1]
            a = s1 + max(POST_GUARD_EDGE_MULT * (s1 - s0), POST_GUARD_FRACTION * length)
        else:
            a = float(t[0])
        if nxt is not None:
            s0, s1 = spans[k]
            b = s0 - max(PRE_GUARD_EDGE_MULT * (s1 - s0), PRE_GUARD_FRACTION * length)
        else:
            b = float(t[-1])
        if not b > a:
            continue
        i0 = int(np.searchsorted(t, a, side="left"))
        i1 = int(np.searchsorted(t, b, side="right"))
        is_high = prev.kind == EdgeKind.RISE if prev else nxt.kind == EdgeKind.FALL
        (high if is_high else low)[i0:i1] = True
    return low, high


def _state_masks(t: np.ndarray, edges: list[Edge]) -> tuple[np.ndarray, np.ndarray]:
    """Unguarded state masks (fallback when a state has no stable samples)."""
    t50 = np.array([e.t50_s for e in edges])
    seg = np.searchsorted(t50, t, side="right")  # segment number of every sample
    first_high = edges[0].kind == EdgeKind.FALL
    is_high = (seg % 2 == 0) == first_high
    return ~is_high, is_high


def estimate_levels_array(
    t: np.ndarray,
    v: np.ndarray,
    hysteresis_pct: float = 10.0,
    min_pulse_width_s: float = 0.0,
) -> Levels:
    """Level estimation on plain arrays (see module docstring)."""
    med = float(np.median(v))
    lo, hi = rough_levels(v)
    if not hi - lo > FLAT_NOISE_MULT * estimate_noise_sigma(v):
        return Levels(low=med, high=med)
    edges = detect_edges_array(t, v, Levels(low=lo, high=hi), hysteresis_pct, min_pulse_width_s)
    if not edges:
        return Levels(low=med, high=med)
    low_mask, high_mask = stable_masks(t, edges)
    if not low_mask.any() or not high_mask.any():
        state_low, state_high = _state_masks(t, edges)
        if not low_mask.any():
            low_mask = state_low
        if not high_mask.any():
            high_mask = state_high
    low = float(np.median(v[low_mask])) if low_mask.any() else lo
    high = float(np.median(v[high_mask])) if high_mask.any() else hi
    if not high > low:  # pathological (e.g. a single runt pulse): keep the rough estimate
        return Levels(low=lo, high=hi)
    return Levels(low=low, high=high)


def estimate_levels(wf: Waveform, settings: AnalysisSettings) -> Levels:
    """Estimate the channel's low/high logic levels (V or A) from its own record."""
    return estimate_levels_array(
        wf.time_s,
        signal_values(wf, settings),
        settings.edge_hysteresis_pct,
        settings.min_pulse_width_s,
    )
