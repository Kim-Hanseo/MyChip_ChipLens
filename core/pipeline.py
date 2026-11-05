"""End-to-end analysis: AnalysisRequest -> AnalysisReport (docs/contract.md section 4.6).

Deterministic: no timestamps or random ids, every list sorted by the contract sort keys (D10).
"""

from __future__ import annotations

from core.analyzers import analyze_all
from core.judge import apply_bandwidth_check, apply_sim_comparison, apply_specs, build_cards, narrate
from core.models import (
    AnalysisReport,
    AnalysisRequest,
    AnalysisResult,
    AnalysisSettings,
    EdgeKind,
    MeasurementSet,
    Role,
    notice_sort_key,
    result_sort_key,
)
from core.preprocess import detect_edges, estimate_levels

_JUDGE_FIELDS_CLEARED = {"spec": None, "verdict": None, "margin_pct": None, "sim_value": None,
                         "deviation_pct": None}


def first_clk_rise_s(mset: MeasurementSet, settings: AnalysisSettings) -> float | None:
    """t50 of the first rising edge of "the CLK" (first CLK channel with a waveform), or None."""
    for ch in mset.channel_map.ids_with_role(Role.CLK):
        wf = mset.waveform(ch)
        if wf is None:
            continue
        levels = estimate_levels(wf, settings)
        edges = detect_edges(wf, levels, settings)
        return next((e.t50_s for e in edges if e.kind == EdgeKind.RISE), None)
    return None


def _unjudged(results: list[AnalysisResult]) -> list[AnalysisResult]:
    return sorted((r.model_copy(update=_JUDGE_FIELDS_CLEARED) for r in results), key=result_sort_key)


def run_analysis(request: AnalysisRequest) -> AnalysisReport:
    """Analyze measured (+ sim) sets, judge against specs, compare with sim, check bandwidth,
    build cards and summary lines."""
    settings = request.settings
    measured = request.measured

    m = analyze_all(measured, settings, request.expected)
    s = analyze_all(request.sim, settings, None) if request.sim is not None else None
    sim_results = s.results if s is not None else []

    results = apply_specs(m.results, request.specs, settings)
    results, sim_notices = apply_sim_comparison(results, sim_results, settings)
    results, bw_notices = apply_bandwidth_check(results, settings)
    results = sorted(results, key=result_sort_key)

    cards = build_cards(results, m.functional, settings)
    lines = narrate(results, m.functional, cards, measured.paths, measured.channel_map, settings)

    notices = list(m.notices) + (list(s.notices) if s is not None else []) + sim_notices + bw_notices

    return AnalysisReport(
        session=measured.session,
        sim_session=request.sim.session if request.sim is not None else None,
        settings=settings,
        channel_map=measured.channel_map,
        paths=measured.paths,
        specs=request.specs,
        results=results,
        sim_results=_unjudged(sim_results),
        functional=m.functional,
        cards=cards,
        summary_lines=lines,
        warnings=sorted(notices, key=notice_sort_key),
        clk_t0_s=first_clk_rise_s(measured, settings),
        sim_clk_t0_s=first_clk_rise_s(request.sim, settings) if request.sim is not None else None,
    )
