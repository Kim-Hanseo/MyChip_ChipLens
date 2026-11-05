"""Summary cards 1-4 (decisions D9, contract section 4.4)."""

from __future__ import annotations

from core.models import (
    METRICS,
    AnalysisResult,
    AnalysisSettings,
    DeviationItem,
    FunctionalCard,
    FunctionalDetail,
    SimDeviationCard,
    Source,
    SummaryCards,
    Verdict,
    VerdictCard,
    WarningCode,
    WorstMarginCard,
    result_sort_key,
)

from .sim_compare import measured_for_comparison
from .spec_margin import MATCH_RATE_ID

SIM_TOP_N = 2


def _verdict_card(results: list[AnalysisResult]) -> VerdictCard:
    verdicts = [r.verdict for r in results]
    return VerdictCard(
        pass_count=verdicts.count(Verdict.PASS),
        marginal_count=verdicts.count(Verdict.MARGINAL),
        fail_count=verdicts.count(Verdict.FAIL),
        no_spec_count=verdicts.count(None),
    )


def _worst_margin_card(results: list[AnalysisResult]) -> WorstMarginCard | None:
    judged = [r for r in results if r.margin_pct is not None and r.verdict is not None and r.spec is not None]
    if not judged:
        return None
    w = min(judged, key=lambda r: (r.margin_pct, result_sort_key(r)))
    return WorstMarginCard(
        metric_id=w.metric_id, path=w.path, channel_id=w.channel_id, value=w.value,
        margin_pct=w.margin_pct, verdict=w.verdict, spec=w.spec,
    )


def _sim_deviation_card(results: list[AnalysisResult], settings: AnalysisSettings) -> SimDeviationCard | None:
    if not any(r.sim_value is not None for r in results):
        return None
    ranked = sorted((r for r in results if r.deviation_pct is not None and r.sim_value is not None),
                    key=lambda r: (-abs(r.deviation_pct), result_sort_key(r)))
    top: list[DeviationItem] = []
    families: set[str] = set()
    for r in ranked:
        family = METRICS[r.metric_id].family
        if family in families:
            continue
        m = measured_for_comparison(r, settings)
        if m is None:  # pragma: no cover - deviation_pct implies a measured value
            continue
        families.add(family)
        top.append(DeviationItem(
            metric_id=r.metric_id, path=r.path, channel_id=r.channel_id,
            measured_value=m, sim_value=r.sim_value, deviation_pct=r.deviation_pct,
        ))
        if len(top) == SIM_TOP_N:
            break
    return SimDeviationCard(
        top=top,
        warning_count=sum(1 for r in results if WarningCode.SIM_DEVIATION in r.warnings),
        tolerance_pct=settings.sim_tolerance_pct,
    )


def _functional_card(results: list[AnalysisResult], functional: FunctionalDetail | None) -> FunctionalCard | None:
    if functional is None or functional.expected_bits is None or functional.match_rate_pct is None:
        return None
    candidates = [r for r in results if r.metric_id == MATCH_RATE_ID and r.verdict is not None]
    if not candidates:
        return None
    mr = next((r for r in candidates if r.channel_id == functional.channel_id), candidates[0])
    return FunctionalCard(
        channel_id=functional.channel_id,
        match_rate_pct=functional.match_rate_pct,
        matched_cycles=functional.matched_cycles,
        compared_cycles=functional.compared_cycles,
        first_mismatch=functional.first_mismatch,
        verdict=mr.verdict,
    )


def build_cards(results: list[AnalysisResult], functional: FunctionalDetail | None,
                settings: AnalysisSettings) -> SummaryCards:
    """Cards 1-4 from judged measured results (sim results are ignored)."""
    measured = sorted((r for r in results if r.source == Source.MEASURED), key=result_sort_key)
    return SummaryCards(
        verdicts=_verdict_card(measured),
        worst_margin=_worst_margin_card(measured),
        sim_deviation=_sim_deviation_card(measured, settings),
        functional=_functional_card(measured, functional),
    )
