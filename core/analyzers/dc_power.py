"""DC / power analyzer: VOH/VOL (stable-segment medians), IDD average, average power, IDDQ from a DC sweep."""

from __future__ import annotations

import numpy as np

from core.models import (
    AnalysisSettings,
    AnalyzerOutput,
    DCSweep,
    Evidence,
    MeasurementSet,
    Role,
    WarningCode,
    make_result,
    notice_sort_key,
    result_sort_key,
)

from ._common import ChannelEdges, Collector, EdgeCache, channels_with_role


def _output_levels(col: Collector, ce: ChannelEdges, channel_id: str, settings: AnalysisSettings) -> None:
    """voh = high level, vol = low level (medians of stable segments, edges excluded).

    Without any edge the whole record is one stable state: it is reported as VOH if its median is
    >= logic VDD / 2, else as VOL; the other level is INSUFFICIENT_EDGES.
    """
    lv = ce.levels
    ref = {"low": lv.low, "high": lv.high}
    if ce.edges:
        col.add(make_result("voh", source=col.source, channel_id=channel_id, value=lv.high,
                            evidence=Evidence(ref_levels_v=ref)))
        col.add(make_result("vol", source=col.source, channel_id=channel_id, value=lv.low,
                            evidence=Evidence(ref_levels_v=ref)))
        return
    level = float(np.median(ce.wf.values)) if lv.high != lv.low else lv.high
    present, missing = ("voh", "vol") if level >= settings.logic_vdd_v / 2.0 else ("vol", "voh")
    col.add(make_result(present, source=col.source, channel_id=channel_id, value=level,
                        evidence=Evidence(ref_levels_v=ref)))
    col.insufficient(missing, channel_id=channel_id, ref_levels=ref,
                     reason="전이가 없어 이 레벨의 안정 구간을 찾지 못했습니다")


def _supply(col: Collector, channel_id: str, vdd_v: float) -> None:
    wf = col.mset.waveform(channel_id)
    idd = float(np.mean(wf.values))
    col.add(make_result("idd_avg", source=col.source, channel_id=channel_id, value=idd))
    col.add(make_result("avg_power", source=col.source, channel_id=channel_id, value=vdd_v * idd,
                        evidence=Evidence(params={"vdd_v": vdd_v, "idd_avg_a": idd})))


def _iddq(col: Collector, sweep: DCSweep, vdd_v: float) -> None:
    ev = Evidence(params={"vdd_v": vdd_v})
    if not (sweep.x[0] <= vdd_v <= sweep.x[-1]):
        col.add(make_result("iddq", source=col.source, channel_id=sweep.name, evidence=ev,
                            warnings=[WarningCode.OUT_OF_SWEEP_RANGE]))
        col.notice(
            WarningCode.OUT_OF_SWEEP_RANGE,
            f"{sweep.name} 정적 전류 IDDQ: 논리 VDD {vdd_v:g} V가 스윕 범위"
            f"({sweep.x[0]:g}–{sweep.x[-1]:g} V) 밖이라 보간하지 못했습니다",
            "iddq", None, sweep.name,
        )
        return
    value = float(np.interp(vdd_v, sweep.x, sweep.y))
    col.add(make_result("iddq", source=col.source, channel_id=sweep.name, value=value, evidence=ev))


def dc_power_into(col: Collector, cache: EdgeCache) -> None:
    mset, settings = col.mset, cache.settings
    for ch in channels_with_role(mset, Role.OUT):
        _output_levels(col, cache.get(ch), ch, settings)
    vdd_ids = channels_with_role(mset, Role.VDD)
    vdd_v = float(np.mean(mset.waveform(vdd_ids[0]).values)) if vdd_ids else settings.logic_vdd_v
    for ch in channels_with_role(mset, Role.IDD):
        _supply(col, ch, vdd_v)
    for sweep in mset.dc_sweeps:
        _iddq(col, sweep, settings.logic_vdd_v)


def analyze_dc_power(mset: MeasurementSet, settings: AnalysisSettings) -> AnalyzerOutput:
    """voh/vol per OUT channel, idd_avg/avg_power per IDD channel, iddq per DC sweep."""
    col = Collector(mset)
    dc_power_into(col, EdgeCache(mset, settings))
    return AnalyzerOutput(
        results=sorted(col.results, key=result_sort_key),
        notices=sorted(col.notices, key=notice_sort_key),
    )
