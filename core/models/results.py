"""Output models (JSON, deterministic). AnalysisReport is the core <-> UI contract."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Literal

from pydantic import Field, model_validator

from .base import ContractModel
from .enums import Category, Source, Verdict, WarningCode
from .inputs import AnalysisSettings, ChannelMap, Path, SessionInfo, Spec
from .metrics import METRIC_INDEX, METRICS


class Stats(ContractModel):
    """Per-edge distribution. std = population std (ddof=0)."""

    mean: float
    min: float
    max: float
    std: float
    n: int = Field(ge=1)


class EdgeSample(ContractModel):
    """One per-edge measurement (marker + distribution point). Times on the waveform's own time axis."""

    t_s: float  # marker time (meaning per metric: docs/metrics.md)
    value: float  # per-edge value in the metric's SI unit
    t_start_s: float | None = None  # interval start (e.g. input 50 % crossing for tpd, 10 % for rise)
    t_end_s: float | None = None  # interval end (e.g. output 50 % crossing, 90 % for rise)


class Evidence(ContractModel):
    edges: list[EdgeSample] = Field(default_factory=list)  # sorted by t_s
    ref_levels_v: dict[str, float] = Field(default_factory=dict)  # keys fixed per metric (docs/metrics.md)
    worst_time_s: float | None = None  # t_s of the worst edge (aggregate MAX/MIN), else None
    params: dict[str, float] = Field(default_factory=dict)  # extra numbers (e.g. vdd_v used)

    @property
    def edge_times_s(self) -> list[float]:
        return [e.t_s for e in self.edges]


class AnalysisResult(ContractModel):
    metric_id: str
    label: str
    category: Category
    unit: str
    source: Source = Source.MEASURED
    path: str | None = None  # Path.name for path metrics, else None
    channel_id: str | None = None  # channel (path metrics: output channel; iddq: DCSweep.name)
    value: float | None = None  # value used for judgment (worst / mean / single per catalog)
    stats: Stats | None = None  # filled iff METRICS[metric_id].has_stats and value is not None
    evidence: Evidence = Field(default_factory=Evidence)
    # --- filled by judge (analyzers leave these at defaults) ---
    spec: Spec | None = None
    verdict: Verdict | None = None
    margin_pct: float | None = None
    sim_value: float | None = None  # sim representative value
    deviation_pct: float | None = None
    # --- both: codes only; messages live in AnalysisReport.warnings ---
    warnings: list[WarningCode] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check(self) -> AnalysisResult:
        if self.metric_id not in METRICS:
            raise ValueError(f"unknown metric_id: {self.metric_id}")
        return self

    def representative(self) -> float | None:
        """Value used for sim comparison: stats.mean if stats else value (D6)."""
        return self.stats.mean if self.stats is not None else self.value

    @property
    def key(self) -> tuple[str, str | None, str | None]:
        """(metric_id, path, channel_id) — pairing key for sim comparison."""
        return (self.metric_id, self.path, self.channel_id)


class Notice(ContractModel):
    """A warning with a Korean message. Emitted by adapters, analyzers and judge."""

    code: WarningCode
    message: str
    source: Source = Source.MEASURED
    metric_id: str | None = None
    path: str | None = None
    channel_id: str | None = None


class FunctionalDetail(ContractModel):
    """Functional check (D7). Cycles are 1-based: cycle n = n-th CLK rising edge in the record."""

    channel_id: str  # sampled OUT channel
    clk_channel_id: str
    threshold_v: float  # logic_vdd_v / 2
    sample_times_s: list[float]  # CLK rising 50 % crossing times, one per cycle
    sample_values_v: list[float]  # OUT value at each sample time (linear interpolation)
    measured_bits: str  # '0'/'1', len == len(sample_times_s)
    expected_bits: str | None = None  # cleaned expected bits (full length) or None
    compared_cycles: int = 0  # min(len(measured), len(expected)); 0 if no expected
    matched_cycles: int = 0
    mismatch_cycles: list[int] = Field(default_factory=list)  # 1-based, ascending
    first_mismatch: int | None = None  # 1-based
    match_rate_pct: float | None = None  # None if no expected

    @model_validator(mode="after")
    def _check(self) -> FunctionalDetail:
        n = len(self.sample_times_s)
        if len(self.sample_values_v) != n or len(self.measured_bits) != n:
            raise ValueError("sample_times_s, sample_values_v and measured_bits must align")
        return self


class AnalyzerOutput(ContractModel):
    """Return type of every analyzer function."""

    results: list[AnalysisResult] = Field(default_factory=list)
    notices: list[Notice] = Field(default_factory=list)
    functional: FunctionalDetail | None = None


# ---- summary cards (D9) ----


class VerdictCard(ContractModel):
    pass_count: int = 0
    marginal_count: int = 0
    fail_count: int = 0
    no_spec_count: int = 0  # results with verdict None


class WorstMarginCard(ContractModel):
    metric_id: str
    path: str | None = None
    channel_id: str | None = None
    value: float | None = None
    margin_pct: float
    verdict: Verdict
    spec: Spec


class DeviationItem(ContractModel):
    metric_id: str
    path: str | None = None
    channel_id: str | None = None
    measured_value: float  # measured representative (after delay offset for tplh/tphl)
    sim_value: float
    deviation_pct: float


class SimDeviationCard(ContractModel):
    top: list[DeviationItem] = Field(default_factory=list)  # <= 2, rule in contract.md 4.3
    warning_count: int = 0  # number of results carrying SIM_DEVIATION
    tolerance_pct: float


class FunctionalCard(ContractModel):
    channel_id: str
    match_rate_pct: float
    matched_cycles: int
    compared_cycles: int
    first_mismatch: int | None = None
    verdict: Verdict


class SummaryCards(ContractModel):
    verdicts: VerdictCard = Field(default_factory=VerdictCard)
    worst_margin: WorstMarginCard | None = None
    sim_deviation: SimDeviationCard | None = None  # None if no sim set
    functional: FunctionalCard | None = None  # None if no expected pattern


class AnalysisReport(ContractModel):
    """Single JSON output of core.pipeline.run_analysis. No timestamps / random ids (D10)."""

    schema_version: Literal["0.1"] = "0.1"
    session: SessionInfo
    sim_session: SessionInfo | None = None
    settings: AnalysisSettings
    channel_map: ChannelMap
    paths: list[Path] = Field(default_factory=list)
    specs: list[Spec] = Field(default_factory=list)
    results: list[AnalysisResult] = Field(default_factory=list)  # measured, judged, sorted
    sim_results: list[AnalysisResult] = Field(default_factory=list)  # sim, unjudged, sorted
    functional: FunctionalDetail | None = None  # measured set only
    cards: SummaryCards = Field(default_factory=SummaryCards)
    summary_lines: list[str] = Field(default_factory=list)  # Korean, <= 8 lines, D9 order
    warnings: list[Notice] = Field(default_factory=list)  # analyzer + judge notices, sorted
    clk_t0_s: float | None = None  # measured first CLK rising 50 % crossing (overlay alignment)
    sim_clk_t0_s: float | None = None  # same for sim set


# ---- helpers (pure) ----

_SOURCE_ORDER = {Source.MEASURED: 0, Source.SIM: 1}


def make_result(
    metric_id: str,
    *,
    source: Source = Source.MEASURED,
    path: str | None = None,
    channel_id: str | None = None,
    value: float | None = None,
    stats: Stats | None = None,
    evidence: Evidence | None = None,
    warnings: Iterable[WarningCode] = (),
) -> AnalysisResult:
    """Build an unjudged result with label/category/unit taken from METRICS."""
    m = METRICS[metric_id]
    return AnalysisResult(
        metric_id=metric_id,
        label=m.label,
        category=m.category,
        unit=m.unit,
        source=source,
        path=path,
        channel_id=channel_id,
        value=value,
        stats=stats,
        evidence=evidence or Evidence(),
        warnings=sorted(set(warnings)),
    )


def result_sort_key(r: AnalysisResult) -> tuple:
    """Canonical result order: catalog order, then path, channel_id, source."""
    return (METRIC_INDEX[r.metric_id], r.path or "", r.channel_id or "", _SOURCE_ORDER[r.source])


def notice_sort_key(n: Notice) -> tuple:
    """Canonical notice order: source, metric (catalog order, none first), path, channel, code, message."""
    midx = METRIC_INDEX.get(n.metric_id, -1) if n.metric_id else -1
    return (_SOURCE_ORDER[n.source], midx, n.path or "", n.channel_id or "", n.code.value, n.message)
