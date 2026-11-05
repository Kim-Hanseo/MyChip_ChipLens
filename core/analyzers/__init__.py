"""Analyzers: timing, DC/power and functional metrics (docs/contract.md section 3).

Every analyzer returns an `AnalyzerOutput` with unjudged results (spec/verdict/margin/sim fields left
None), sorted by `result_sort_key`, and Korean notices sorted by `notice_sort_key`.
"""

from __future__ import annotations

from core.models import (
    AnalysisSettings,
    AnalyzerOutput,
    ExpectedPattern,
    MeasurementSet,
    notice_sort_key,
    result_sort_key,
)

from ._common import Collector, EdgeCache
from .dc_power import analyze_dc_power, dc_power_into
from .functional import analyze_functional, functional_into
from .timing import analyze_timing, pair_path_edges, timing_into


def analyze_all(mset: MeasurementSet, settings: AnalysisSettings,
                expected: ExpectedPattern | None = None) -> AnalyzerOutput:
    """Timing + DC/power + functional in one pass (levels/edges computed once per channel)."""
    col = Collector(mset)
    cache = EdgeCache(mset, settings)
    timing_into(col, cache)
    dc_power_into(col, cache)
    functional = functional_into(col, cache, expected)
    return AnalyzerOutput(
        results=sorted(col.results, key=result_sort_key),
        notices=sorted(col.notices, key=notice_sort_key),
        functional=functional,
    )


__all__ = [
    "analyze_all",
    "analyze_dc_power",
    "analyze_functional",
    "analyze_timing",
    "pair_path_edges",
]
