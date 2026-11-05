"""Scope bandwidth warning (decisions D8, contract section 4.3)."""

from __future__ import annotations

from core.models import (
    METRICS,
    AnalysisResult,
    AnalysisSettings,
    Notice,
    Source,
    WarningCode,
    format_metric_value,
    format_si,
    notice_sort_key,
)

from .sim_compare import target_text, with_warning

BANDWIDTH_METRICS = frozenset({"rise_time", "fall_time"})
RISE_TIME_BW_PRODUCT = 0.35  # t_r ~= 0.35 / BW for a first-order (Gaussian-like) scope response
BANDWIDTH_MARGIN_FACTOR = 2.0  # warn when the measured edge is within 2x the scope's own rise time


def bandwidth_limit_s(bandwidth_hz: float) -> float:
    """2 x 0.35 / BW (500 MHz -> 1.4 ns, 100 MHz -> 7 ns)."""
    return BANDWIDTH_MARGIN_FACTOR * RISE_TIME_BW_PRODUCT / bandwidth_hz


def apply_bandwidth_check(results: list[AnalysisResult],
                          settings: AnalysisSettings) -> tuple[list[AnalysisResult], list[Notice]]:
    """Add BANDWIDTH_LIMIT (+ Notice) to measured rise/fall results whose stats.mean < 2 x 0.35 / BW."""
    if settings.bandwidth_hz is None:
        return list(results), []
    limit = bandwidth_limit_s(settings.bandwidth_hz)
    out: list[AnalysisResult] = []
    notices: list[Notice] = []
    for r in results:
        if (r.source != Source.MEASURED or r.metric_id not in BANDWIDTH_METRICS
                or r.stats is None or not r.stats.mean < limit):
            out.append(r)
            continue
        out.append(with_warning(r, WarningCode.BANDWIDTH_LIMIT))
        notices.append(Notice(
            code=WarningCode.BANDWIDTH_LIMIT,
            message=(f"{target_text(r)} {METRICS[r.metric_id].short_label} 평균 "
                     f"{format_metric_value(r.metric_id, r.stats.mean)} < 대역폭 한계 "
                     f"{format_metric_value(r.metric_id, limit)} "
                     f"(2 × 0.35 / {format_si(settings.bandwidth_hz, 'Hz')}) → 실제 값은 더 짧을 수 있음"),
            source=r.source,
            metric_id=r.metric_id,
            path=r.path,
            channel_id=r.channel_id,
        ))
    return out, sorted(notices, key=notice_sort_key)
