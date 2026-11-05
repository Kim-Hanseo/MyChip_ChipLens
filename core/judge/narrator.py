"""Rule-based Korean summary lines (decisions D9, contract section 4.5).

Line order: 0 headline, 1 FAIL, 1b MARGINAL, 2 functional mismatch, 3 common delay / 4 single slow path,
5 bandwidth. At most MAX_LINES lines; extra lines are cut from the end.
"""

from __future__ import annotations

from statistics import median

from core.models import (
    METRICS,
    AnalysisResult,
    AnalysisSettings,
    ChannelMap,
    FunctionalDetail,
    Path,
    Source,
    SummaryCards,
    Verdict,
    WarningCode,
    format_metric_value,
    format_spec,
    result_sort_key,
)

from .spec_margin import MATCH_RATE_ID

MAX_LINES = 8
COMMON_DELAY_METRICS = ("tplh", "tphl", "rise_time", "fall_time")  # rule 3 set D
PATH_DELAY_METRICS = ("tplh", "tphl")  # rule 4 per-path mean
COMMON_DELAY_MIN_COUNT = 2
COMMON_DELAY_MAX_RATIO = 2.0

LINE_COMMON_DELAY = "전 경로 공통 지연 증가 → 측정 경로(패드·PCB·프로브) 지연, VDD 강하, 공정 코너 가능성"


def _target(r: AnalysisResult, channel_map: ChannelMap) -> str:
    if r.path:
        return r.path
    return channel_map.display_name(r.channel_id) if r.channel_id else ""


def _label(metric_id: str) -> str:
    return METRICS[metric_id].short_label


def _headline(cards: SummaryCards, channel_map: ChannelMap) -> str:
    v = cards.verdicts
    line = f"전체 판정: PASS {v.pass_count} · MARGINAL {v.marginal_count} · FAIL {v.fail_count}"
    w = cards.worst_margin
    if w is not None:
        target = w.path or (channel_map.display_name(w.channel_id) if w.channel_id else "")
        line += f" — 최악 마진 {_label(w.metric_id)} {w.margin_pct:.1f}% ({target})"
    return line


def _fail_lines(results: list[AnalysisResult], channel_map: ChannelMap) -> list[str]:
    return [
        f"{_target(r, channel_map)} {_label(r.metric_id)} {format_metric_value(r.metric_id, r.value)}"
        f" — 스펙 {format_spec(r.spec)} 위반 (FAIL)"
        for r in results
        if r.verdict == Verdict.FAIL and r.metric_id != MATCH_RATE_ID and r.spec is not None
    ]


def _marginal_lines(results: list[AnalysisResult], channel_map: ChannelMap) -> list[str]:
    return [
        f"{_target(r, channel_map)} {_label(r.metric_id)} {format_metric_value(r.metric_id, r.value)}"
        f" — 스펙 {format_spec(r.spec)} 대비 마진 {r.margin_pct:.1f}% (MARGINAL)"
        for r in results
        if r.verdict == Verdict.MARGINAL and r.spec is not None and r.margin_pct is not None
    ]


def _functional_lines(functional: FunctionalDetail | None) -> list[str]:
    if functional is None or functional.expected_bits is None or functional.first_mismatch is None:
        return []
    i = functional.first_mismatch - 1
    if not (0 <= i < len(functional.expected_bits) and i < len(functional.measured_bits)):
        return []
    e, m = functional.expected_bits[i], functional.measured_bits[i]
    return [f"{functional.first_mismatch}번째 사이클에서 첫 불일치 (기대 {e}, 측정 {m})"]


def _slow_path_lines(results: list[AnalysisResult], paths: list[Path], tol: float) -> list[str]:
    """Rule 4: a path whose mean(tplh, tphl) deviation > tol and exceeds the median of the other
    paths by >= tol. Only when >= 2 paths have a deviation."""
    per_path: dict[str, float] = {}
    for p in paths:
        devs = [r.deviation_pct for r in results
                if r.path == p.name and r.metric_id in PATH_DELAY_METRICS and r.deviation_pct is not None]
        if devs:
            per_path[p.name] = sum(devs) / len(devs)
    if len(per_path) < 2:
        return []
    lines = []
    for name, dev in per_path.items():  # paths order
        others = [d for n, d in per_path.items() if n != name]
        if dev > tol and dev - median(others) >= tol:
            lines.append(f"{name}만 시뮬 대비 {dev:+.1f}% → 해당 경로 부하·배선 기생 확인 필요")
    return lines


def _common_delay_lines(results: list[AnalysisResult], tol: float) -> list[str]:
    """Rule 3: every deviation in D > tol, |D| >= 2 and max(D)/min(D) <= 2."""
    d = [r.deviation_pct for r in results
         if r.metric_id in COMMON_DELAY_METRICS and r.deviation_pct is not None]
    if len(d) < COMMON_DELAY_MIN_COUNT or not all(x > tol for x in d):
        return []
    lo, hi = min(d), max(d)
    if lo <= 0.0 or hi / lo > COMMON_DELAY_MAX_RATIO:
        return []
    return [LINE_COMMON_DELAY]


def _bandwidth_lines(results: list[AnalysisResult], channel_map: ChannelMap) -> list[str]:
    return [
        f"{_target(r, channel_map)} {_label(r.metric_id)} {format_metric_value(r.metric_id, r.stats.mean)}"
        ": 측정값이 오실로스코프 대역폭 한계에 가까움 → 실제 값은 더 짧을 수 있음"
        for r in results
        if WarningCode.BANDWIDTH_LIMIT in r.warnings and r.stats is not None
    ]


def narrate(results: list[AnalysisResult], functional: FunctionalDetail | None, cards: SummaryCards,
            paths: list[Path], channel_map: ChannelMap, settings: AnalysisSettings) -> list[str]:
    """Korean summary lines in D9 order, at most 8 (cut from the end)."""
    measured = sorted((r for r in results if r.source == Source.MEASURED), key=result_sort_key)
    tol = settings.sim_tolerance_pct
    lines = [_headline(cards, channel_map)]
    lines += _fail_lines(measured, channel_map)
    lines += _marginal_lines(measured, channel_map)
    lines += _functional_lines(functional)
    slow = _slow_path_lines(measured, paths, tol)
    lines += slow if slow else _common_delay_lines(measured, tol)
    lines += _bandwidth_lines(measured, channel_map)
    return lines[:MAX_LINES]
