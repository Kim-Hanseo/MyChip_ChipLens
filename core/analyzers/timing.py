"""Timing analyzer: rise/fall, path delays (D4 pairing), clock period/frequency/duty, setup/hold slack."""

from __future__ import annotations

import math

import numpy as np

from core.models import (
    METRICS,
    AnalysisSettings,
    AnalyzerOutput,
    EdgeKind,
    EdgeSample,
    Evidence,
    MeasurementSet,
    Path,
    Polarity,
    Role,
    WarningCode,
    make_result,
    notice_sort_key,
    result_sort_key,
)

from ._common import ChannelEdges, Collector, EdgeCache, aggregate_samples, channels_with_role, the_clk

_OPPOSITE = {EdgeKind.RISE: EdgeKind.FALL, EdgeKind.FALL: EdgeKind.RISE}


def _edge_rate(col: Collector, ce: ChannelEdges, channel_id: str) -> None:
    """rise_time (10 -> 90 %) and fall_time (90 -> 10 %) on the channel's own levels."""
    lv = ce.levels
    ref = {"low": lv.low, "high": lv.high, "v10": lv.at_pct(10.0), "v90": lv.at_pct(90.0)}
    rise = [
        EdgeSample(t_s=e.t50_s, value=e.t90_s - e.t10_s, t_start_s=e.t10_s, t_end_s=e.t90_s)
        for e in ce.of_kind(EdgeKind.RISE)
        if e.t10_s is not None and e.t90_s is not None
    ]
    fall = [
        EdgeSample(t_s=e.t50_s, value=e.t10_s - e.t90_s, t_start_s=e.t90_s, t_end_s=e.t10_s)
        for e in ce.of_kind(EdgeKind.FALL)
        if e.t10_s is not None and e.t90_s is not None
    ]
    col.from_samples("rise_time", rise, channel_id=channel_id, ref_levels=ref)
    col.from_samples("fall_time", fall, channel_id=channel_id, ref_levels=ref)


def _clock(col: Collector, ce: ChannelEdges, channel_id: str) -> None:
    """period (mean rising-to-rising), frequency (1 / mean period), duty (high time / period)."""
    ref = {"v50": ce.levels.at_pct(50.0)}
    rises = ce.t50(EdgeKind.RISE)
    falls = ce.t50(EdgeKind.FALL)
    if rises.shape[0] < 2:
        for mid in ("period", "frequency", "duty_cycle"):
            col.insufficient(mid, channel_id=channel_id, ref_levels=ref,
                             reason="상승 엣지가 2개 미만이라 주기를 구하지 못했습니다")
        return
    periods = np.diff(rises)
    period = col.from_samples(
        "period",
        [EdgeSample(t_s=float(rises[k]), value=float(periods[k]), t_start_s=float(rises[k]),
                    t_end_s=float(rises[k + 1])) for k in range(periods.shape[0])],
        channel_id=channel_id, ref_levels=ref,
    )
    col.add(make_result("frequency", source=col.source, channel_id=channel_id,
                        value=1.0 / period.value, evidence=Evidence(ref_levels_v=ref)))
    duty: list[EdgeSample] = []
    idx = np.searchsorted(falls, rises[:-1], side="right")
    for k in range(periods.shape[0]):
        if idx[k] < falls.shape[0] and falls[idx[k]] < rises[k + 1]:
            f = float(falls[idx[k]])
            duty.append(EdgeSample(t_s=float(rises[k]), value=float((f - rises[k]) / periods[k] * 100.0),
                                   t_start_s=float(rises[k]), t_end_s=f))
    col.from_samples("duty_cycle", duty, channel_id=channel_id, ref_levels=ref)


def _slack(col: Collector, data: ChannelEdges, clk: ChannelEdges, channel_id: str) -> None:
    """setup: next CLK rise - data transition; hold: data transition - previous CLK rise (50 %)."""
    ref = {"clk_v50": clk.levels.at_pct(50.0), "data_v50": data.levels.at_pct(50.0)}
    rises = clk.t50(EdgeKind.RISE)
    trans = data.t50()
    setup: list[EdgeSample] = []
    hold: list[EdgeSample] = []
    if rises.shape[0] and trans.shape[0]:
        nxt = np.searchsorted(rises, trans, side="right")  # first rise strictly after the transition
        for i, td in enumerate(trans):
            td = float(td)
            if nxt[i] < rises.shape[0]:
                r = float(rises[nxt[i]])
                setup.append(EdgeSample(t_s=td, value=r - td, t_start_s=td, t_end_s=r))
            if nxt[i] > 0:
                r = float(rises[nxt[i] - 1])
                hold.append(EdgeSample(t_s=td, value=td - r, t_start_s=r, t_end_s=td))
    col.from_samples("setup_slack", setup, channel_id=channel_id, ref_levels=ref)
    col.from_samples("hold_slack", hold, channel_id=channel_id, ref_levels=ref)


def pair_path_edges(
    inp: ChannelEdges, out: ChannelEdges, polarity: Polarity
) -> tuple[dict[EdgeKind, list[tuple[float, float]]], dict[EdgeKind, int]]:
    """D4 pairing. Returns ({output kind: [(t_in, t_out)]}, {output kind: dropped input edges}).

    Each input edge is paired with the next output edge of the expected polarity
    (same direction for non_inverting, opposite for inverting) if that edge comes before the next
    input edge AND within 0.5 x the minimum spacing between input edges; otherwise it is dropped.
    """
    in_t = inp.t50()
    in_kind = [e.kind for e in inp.edges]
    window = 0.5 * float(np.min(np.diff(in_t))) if in_t.shape[0] >= 2 else math.inf
    out_t = {k: out.t50(k) for k in (EdgeKind.RISE, EdgeKind.FALL)}
    pairs: dict[EdgeKind, list[tuple[float, float]]] = {EdgeKind.RISE: [], EdgeKind.FALL: []}
    dropped = {EdgeKind.RISE: 0, EdgeKind.FALL: 0}
    for i in range(in_t.shape[0]):
        t_in = float(in_t[i])
        k_out = in_kind[i] if polarity == Polarity.NON_INVERTING else _OPPOSITE[in_kind[i]]
        cand = out_t[k_out]
        j = int(np.searchsorted(cand, t_in, side="right"))
        t_next = float(in_t[i + 1]) if i + 1 < in_t.shape[0] else math.inf
        if j < cand.shape[0] and cand[j] < t_next and cand[j] - t_in <= window:
            pairs[k_out].append((t_in, float(cand[j])))
        else:
            dropped[k_out] += 1
    return pairs, dropped


def _path(col: Collector, p: Path, inp: ChannelEdges, out: ChannelEdges) -> None:
    """tplh / tphl (per output direction) and tpd (both directions) for one path."""
    ref = {"in_v50": inp.levels.at_pct(50.0), "out_v50": out.levels.at_pct(50.0)}
    pairs, dropped = pair_path_edges(inp, out, p.polarity)
    all_samples: list[EdgeSample] = []
    have_value = False
    for mid, kind in (("tplh", EdgeKind.RISE), ("tphl", EdgeKind.FALL)):
        samples = [EdgeSample(t_s=to, value=to - ti, t_start_s=ti, t_end_s=to) for ti, to in pairs[kind]]
        warnings = []
        if dropped[kind]:
            warnings.append(WarningCode.UNPAIRED_EDGES)
            col.notice(
                WarningCode.UNPAIRED_EDGES,
                f"{p.name} {METRICS[mid].label}: 짝짓기 창 밖 입력 엣지 {dropped[kind]}개를 제외했습니다",
                mid, p.name, p.output_channel,
            )
        if col.from_samples(mid, samples, path=p.name, channel_id=p.output_channel, ref_levels=ref,
                            warnings=warnings) is not None:
            have_value = True
        all_samples.extend(samples)
    if have_value:
        col.add(make_result("tpd", source=col.source, path=p.name, channel_id=p.output_channel,
                            **aggregate_samples("tpd", all_samples, ref)))


def timing_into(col: Collector, cache: EdgeCache) -> None:
    mset = col.mset
    for ch in channels_with_role(mset, Role.OUT):
        _edge_rate(col, cache.get(ch), ch)
    clk_id = the_clk(mset)
    if clk_id is not None:
        clk = cache.get(clk_id)
        _clock(col, clk, clk_id)
        for ch in channels_with_role(mset, Role.DATA, Role.OUT):
            _slack(col, cache.get(ch), clk, ch)
    for p in mset.paths:
        roles = (mset.channel_map.role_of(p.input_channel), mset.channel_map.role_of(p.output_channel))
        if Role.UNUSED in roles:
            continue
        inp = cache.get(p.input_channel)
        out = cache.get(p.output_channel)
        if inp is None or out is None:
            continue
        _path(col, p, inp, out)


def analyze_timing(mset: MeasurementSet, settings: AnalysisSettings) -> AnalyzerOutput:
    """Timing metrics for every OUT/DATA/CLK channel and every path that has waveforms."""
    col = Collector(mset)
    timing_into(col, EdgeCache(mset, settings))
    return AnalyzerOutput(
        results=sorted(col.results, key=result_sort_key),
        notices=sorted(col.notices, key=notice_sort_key),
    )
