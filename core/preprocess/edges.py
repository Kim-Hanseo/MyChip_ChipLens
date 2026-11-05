"""Hysteresis edge detection with linear-interpolated 10 / 50 / 90 % crossings (plan B2).

Algorithm (all numpy-vectorized over samples; loops only over edges):
1. Classify every sample against the hysteresis thresholds 50 % +/- h % of the swing:
   +1 above the upper threshold, -1 below the lower one, 0 in between.
2. The logic state is the last non-zero class (forward fill); an edge is a change of state.
   Noise and ringing that never cross both thresholds cannot create (duplicate) edges.
3. 50 % instant: between the last sample of the old state and the first sample of the new state,
   the first and the last 50 % crossings are linear-interpolated and averaged (they coincide
   unless noise re-crosses the 50 % level inside the transition).
4. Pulses shorter than `min_pulse_width_s` (between 50 % instants) are removed as a pair.
5. 10 % / 90 % instants: the crossing of that level nearest to the 50 % instant on each side,
   searched only inside the edge's own stable segments (None for runt pulses that never reach it).
"""

from __future__ import annotations

import math

import numpy as np

from core.models import AnalysisSettings, Edge, EdgeKind, Levels, Waveform

from .filters import signal_values


def _last_index_where(mask: np.ndarray) -> np.ndarray:
    """out[i] = largest k <= i with mask[k], or -1."""
    idx = np.where(mask, np.arange(mask.shape[0]), -1)
    return np.maximum.accumulate(idx)


def _next_index_where(mask: np.ndarray) -> np.ndarray:
    """out[i] = smallest k >= i with mask[k], or len(mask)."""
    n = mask.shape[0]
    idx = np.where(mask, np.arange(n), n)
    return np.minimum.accumulate(idx[::-1])[::-1]


def _cross_time(t: np.ndarray, v: np.ndarray, k: np.ndarray, level: float) -> np.ndarray:
    """Linear-interpolated time where the segment (k, k+1) crosses `level`."""
    v0 = v[k]
    v1 = v[k + 1]
    t0 = t[k]
    return t0 + (level - v0) / (v1 - v0) * (t[k + 1] - t0)


def _remove_short_pulses(t50: np.ndarray, min_pulse_width_s: float) -> np.ndarray:
    """Indices of edges kept after dropping pulses shorter than the minimum width (as pairs)."""
    if min_pulse_width_s <= 0 or t50.shape[0] < 2:
        return np.arange(t50.shape[0])
    kept: list[int] = []
    for i in range(t50.shape[0]):
        if kept and t50[i] - t50[kept[-1]] < min_pulse_width_s:
            kept.pop()  # the pulse between kept[-1] and i is too short: drop both of its edges
            continue
        kept.append(i)
    return np.asarray(kept, dtype=np.int64)


def detect_edges_array(
    t: np.ndarray,
    v: np.ndarray,
    levels: Levels,
    hysteresis_pct: float = 10.0,
    min_pulse_width_s: float = 0.0,
) -> list[Edge]:
    """Edge detection on plain arrays (`t` strictly increasing). Returns edges sorted by t50_s."""
    swing = levels.high - levels.low
    n = int(v.shape[0])
    if not swing > 0 or n < 2:
        return []
    lo_th = levels.at_pct(50.0 - hysteresis_pct)
    hi_th = levels.at_pct(50.0 + hysteresis_pct)
    v50 = levels.at_pct(50.0)

    cls = np.zeros(n, dtype=np.int8)
    cls[v > hi_th] = 1
    cls[v < lo_th] = -1
    nz = np.flatnonzero(cls)
    if nz.size < 2:
        return []
    states = cls[nz]
    change = np.flatnonzero(states[1:] != states[:-1]) + 1
    if change.size == 0:
        return []
    j_new = nz[change]  # first sample of the new state (beyond the far threshold)
    j_old = nz[change - 1]  # last sample of the old state (beyond the near threshold)
    rising = states[change] > 0

    # 50 % instants: first and last crossing inside (j_old, j_new), averaged
    last_below50 = _last_index_where(v < v50)
    last_above50 = _last_index_where(v > v50)
    next_ge50 = _next_index_where(v >= v50)
    next_le50 = _next_index_where(v <= v50)
    k_last = np.where(rising, last_below50[j_new - 1], last_above50[j_new - 1])
    k_first = np.where(rising, next_ge50[j_old], next_le50[j_old]) - 1
    t50 = 0.5 * (_cross_time(t, v, k_first, v50) + _cross_time(t, v, k_last, v50))

    keep = _remove_short_pulses(t50, min_pulse_width_s)
    if keep.size == 0:
        return []
    t50 = t50[keep]
    rising = rising[keep]
    k_first = k_first[keep]
    k_last = k_last[keep]
    j_new = j_new[keep]
    j_old = j_old[keep]

    # 10 % / 90 % instants, bounded by the neighbouring edges' stable segments
    v10 = levels.at_pct(10.0)
    v90 = levels.at_pct(90.0)
    last_below10 = _last_index_where(v < v10)
    last_above90 = _last_index_where(v > v90)
    next_ge90 = _next_index_where(v >= v90)
    next_le10 = _next_index_where(v <= v10)
    m = t50.shape[0]
    lower_bound = np.empty(m, dtype=np.int64)  # earliest sample of this edge's "from" segment
    lower_bound[0] = 0
    lower_bound[1:] = j_new[:-1]
    upper_bound = np.empty(m, dtype=np.int64)  # latest sample of this edge's "to" segment
    upper_bound[-1] = n - 1
    upper_bound[:-1] = j_old[1:]

    level_from = np.where(rising, v10, v90)  # rise: 10 % before t50, fall: 90 % before t50
    level_to = np.where(rising, v90, v10)  # rise: 90 % after t50, fall: 10 % after t50
    k_from = np.where(rising, last_below10[k_first], last_above90[k_first])
    from_ok = (k_from >= lower_bound) & (k_from >= 0)
    k_to = np.where(rising, next_ge90[k_last + 1], next_le10[k_last + 1])
    to_ok = (k_to <= upper_bound) & (k_to < n)
    with np.errstate(divide="ignore", invalid="ignore"):  # rejected (not ok) entries may divide by 0
        t_from = _cross_time(t, v, np.clip(k_from, 0, n - 2), level_from)
        t_to = _cross_time(t, v, np.clip(k_to, 1, n - 1) - 1, level_to)

    edges: list[Edge] = []
    for i in range(m):
        tf = float(t_from[i]) if from_ok[i] and math.isfinite(t_from[i]) else None
        tt = float(t_to[i]) if to_ok[i] and math.isfinite(t_to[i]) else None
        if rising[i]:
            edges.append(Edge(kind=EdgeKind.RISE, t50_s=float(t50[i]), t10_s=tf, t90_s=tt))
        else:
            edges.append(Edge(kind=EdgeKind.FALL, t50_s=float(t50[i]), t10_s=tt, t90_s=tf))
    return edges


def detect_edges(wf: Waveform, levels: Levels, settings: AnalysisSettings) -> list[Edge]:
    """Detect rising/falling edges of `wf` against `levels` (hysteresis 50 % +/- edge_hysteresis_pct,
    minimum pulse width, optional smoothing). Sorted by t50_s."""
    return detect_edges_array(
        wf.time_s,
        signal_values(wf, settings),
        levels,
        settings.edge_hysteresis_pct,
        settings.min_pulse_width_s,
    )
