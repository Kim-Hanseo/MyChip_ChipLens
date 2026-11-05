"""Functional analyzer (D7): sample OUT at every CLK rising 50 % crossing, compare with expected bits."""

from __future__ import annotations

import numpy as np

from core.models import (
    AnalysisSettings,
    AnalyzerOutput,
    EdgeKind,
    Evidence,
    ExpectedPattern,
    FunctionalDetail,
    MeasurementSet,
    Role,
    WarningCode,
    make_result,
    notice_sort_key,
    result_sort_key,
)

from ._common import Collector, EdgeCache, channels_with_role, the_clk


def _target_out(mset: MeasurementSet, expected: ExpectedPattern | None) -> str | None:
    """Expected pattern's channel, else the first OUT channel (ChannelMap order) with a waveform."""
    if expected is not None and expected.channel_id is not None:
        return expected.channel_id
    ids = channels_with_role(mset, Role.OUT)
    return ids[0] if ids else None


def functional_into(col: Collector, cache: EdgeCache, expected: ExpectedPattern | None) -> FunctionalDetail | None:
    mset, settings = col.mset, cache.settings
    clk_id = the_clk(mset)
    out_id = _target_out(mset, expected)
    out_wf = mset.waveform(out_id) if out_id is not None else None
    if clk_id is None or out_wf is None:
        if expected is not None:
            missing = "CLK" if clk_id is None else f"기능 대상 출력({out_id or 'OUT'})"
            col.notice(WarningCode.MISSING_ROLE,
                       f"기대 비트열이 있지만 {missing} 파형이 없어 기능 검증을 하지 못했습니다",
                       "match_rate", None, out_id)
        return None

    threshold = settings.logic_vdd_v / 2.0
    rises = cache.get(clk_id).t50(EdgeKind.RISE)
    t_out = out_wf.time_s
    rises = rises[(rises >= t_out[0]) & (rises <= t_out[-1])]  # cycles inside the OUT record
    samples = np.interp(rises, t_out, out_wf.values)
    bits = "".join(np.where(samples >= threshold, "1", "0").tolist())

    exp_bits = expected.bits if expected is not None else None
    compared = min(len(bits), len(exp_bits)) if exp_bits is not None else 0
    mismatches = [i + 1 for i in range(compared) if bits[i] != exp_bits[i]]
    matched = compared - len(mismatches)
    rate = matched / compared * 100.0 if compared > 0 else None
    detail = FunctionalDetail(
        channel_id=out_id,
        clk_channel_id=clk_id,
        threshold_v=threshold,
        sample_times_s=[float(x) for x in rises],
        sample_values_v=[float(x) for x in samples],
        measured_bits=bits,
        expected_bits=exp_bits,
        compared_cycles=compared,
        matched_cycles=matched,
        mismatch_cycles=mismatches,
        first_mismatch=mismatches[0] if mismatches else None,
        match_rate_pct=rate,
    )
    if exp_bits is None:
        return detail

    warnings: list[WarningCode] = []
    if len(exp_bits) != len(bits):
        warnings.append(WarningCode.EXPECTED_LENGTH_MISMATCH)
        col.notice(WarningCode.EXPECTED_LENGTH_MISMATCH,
                   f"기대 비트열 길이({len(exp_bits)})와 측정 사이클 수({len(bits)})가 달라 "
                   f"앞 {compared}개 사이클만 비교했습니다",
                   "match_rate", None, out_id)
    ref = {"threshold_v": threshold}
    if rate is None:
        col.insufficient("match_rate", channel_id=out_id, ref_levels=ref, extra_warnings=warnings,
                         reason="CLK 상승 엣지가 없어 비교할 사이클이 없습니다")
    else:
        col.add(make_result("match_rate", source=col.source, channel_id=out_id, value=rate,
                            evidence=Evidence(ref_levels_v=ref), warnings=warnings))
    return detail


def analyze_functional(mset: MeasurementSet, settings: AnalysisSettings,
                       expected: ExpectedPattern | None) -> AnalyzerOutput:
    """Measured bit string (always, when CLK and OUT exist) and match_rate (when bits are expected)."""
    col = Collector(mset)
    functional = functional_into(col, EdgeCache(mset, settings), expected)
    return AnalyzerOutput(
        results=sorted(col.results, key=result_sort_key),
        notices=sorted(col.notices, key=notice_sort_key),
        functional=functional,
    )
