"""Measured vs simulation deviation (decisions D6, contract section 4.2)."""

from __future__ import annotations

from core.models import (
    METRICS,
    AnalysisResult,
    AnalysisSettings,
    Notice,
    WarningCode,
    notice_sort_key,
)

OFFSET_METRICS = frozenset({"tplh", "tphl"})  # delay_offset_s applies only to these (D6)


def with_warning(result: AnalysisResult, code: WarningCode) -> AnalysisResult:
    """Copy of `result` with `code` added (warnings stay a sorted, duplicate-free list)."""
    return result.model_copy(update={"warnings": sorted(set(result.warnings) | {code})})


def measured_for_comparison(result: AnalysisResult, settings: AnalysisSettings) -> float | None:
    """Measured representative minus the delay offset (tplh/tphl only)."""
    m = result.representative()
    if m is None:
        return None
    if result.metric_id in OFFSET_METRICS:
        m -= settings.delay_offset_s
    return m


def deviation_pct(measured: float | None, sim_value: float | None) -> float | None:
    """(m - sim)/|sim| x 100; None if either side is missing or sim is 0."""
    if measured is None or sim_value is None or sim_value == 0.0:
        return None
    return (measured - sim_value) / abs(sim_value) * 100.0


def target_text(result: AnalysisResult) -> str:
    """Path name for path metrics, else channel_id (no ChannelMap at this stage)."""
    return result.path or result.channel_id or ""


def apply_sim_comparison(results: list[AnalysisResult], sim_results: list[AnalysisResult],
                         settings: AnalysisSettings) -> tuple[list[AnalysisResult], list[Notice]]:
    """Pair measured results with sim results by (metric_id, path, channel_id) and fill
    sim_value / deviation_pct. |deviation| > sim_tolerance_pct adds SIM_DEVIATION + a Notice.
    """
    sim_index: dict[tuple[str, str | None, str | None], AnalysisResult] = {}
    for s in sim_results:
        sim_index.setdefault(s.key, s)

    tol = settings.sim_tolerance_pct
    out: list[AnalysisResult] = []
    notices: list[Notice] = []
    for r in results:
        sim = sim_index.get(r.key)
        if not METRICS[r.metric_id].sim_compare or sim is None:
            out.append(r)
            continue
        sim_value = sim.representative()
        dev = deviation_pct(measured_for_comparison(r, settings), sim_value)
        new = r.model_copy(update={"sim_value": sim_value, "deviation_pct": dev})
        if dev is not None and abs(dev) > tol:
            new = with_warning(new, WarningCode.SIM_DEVIATION)
            notices.append(Notice(
                code=WarningCode.SIM_DEVIATION,
                message=(f"{target_text(r)} {METRICS[r.metric_id].short_label} 시뮬 대비 "
                         f"{dev:+.1f}% (허용 ±{tol:.1f}% 초과)"),
                source=r.source,
                metric_id=r.metric_id,
                path=r.path,
                channel_id=r.channel_id,
            ))
        out.append(new)
    return out, sorted(notices, key=notice_sort_key)
