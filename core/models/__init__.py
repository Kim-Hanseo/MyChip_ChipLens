"""ChipLens contract: standard data models, AnalysisReport, metric catalog, unit helpers.

Owned by schema-architect. Other agents import from here and never modify it.
"""

from .base import ContractModel, FloatArray
from .enums import (
    ROLE_LABELS,
    VERDICT_LABELS,
    VERDICT_SYMBOLS,
    Aggregate,
    Category,
    EdgeKind,
    FileKind,
    Polarity,
    Quantity,
    Role,
    Source,
    Target,
    Verdict,
    WarningCode,
)
from .inputs import (
    AnalysisRequest,
    AnalysisSettings,
    ChannelInfo,
    ChannelMap,
    DCSweep,
    Edge,
    ExpectedPattern,
    Levels,
    MeasurementSet,
    Path,
    SessionInfo,
    SignalPath,
    Spec,
    Waveform,
)
from .metrics import METRIC_IDS, METRIC_INDEX, METRICS, MetricDef
from .results import (
    AnalysisReport,
    AnalysisResult,
    AnalyzerOutput,
    DeviationItem,
    EdgeSample,
    Evidence,
    FunctionalCard,
    FunctionalDetail,
    Notice,
    SimDeviationCard,
    Stats,
    SummaryCards,
    VerdictCard,
    WorstMarginCard,
    make_result,
    notice_sort_key,
    result_sort_key,
)
from .tables import (
    PREVIEW_HEAD_ROWS,
    PREVIEW_RAW_ROWS,
    ChannelConversion,
    ColumnInfo,
    DCSweepBuildResult,
    RawTable,
    ReadOptions,
    TablePreview,
    TimeAxisSpec,
    WaveformBuildResult,
)
from .units import (
    MICRO,
    format_metric_value,
    format_number,
    format_pct,
    format_si,
    format_spec,
    parse_unit,
)

__all__ = [
    "ContractModel", "FloatArray",
    "Aggregate", "Category", "EdgeKind", "FileKind", "Polarity", "Quantity", "Role", "Source",
    "Target", "Verdict", "WarningCode", "ROLE_LABELS", "VERDICT_LABELS", "VERDICT_SYMBOLS",
    "AnalysisRequest", "AnalysisSettings", "ChannelInfo", "ChannelMap", "DCSweep", "Edge",
    "ExpectedPattern", "Levels", "MeasurementSet", "Path", "SessionInfo", "SignalPath", "Spec",
    "Waveform",
    "METRIC_IDS", "METRIC_INDEX", "METRICS", "MetricDef",
    "AnalysisReport", "AnalysisResult", "AnalyzerOutput", "DeviationItem", "EdgeSample", "Evidence",
    "FunctionalCard", "FunctionalDetail", "Notice", "SimDeviationCard", "Stats", "SummaryCards",
    "VerdictCard", "WorstMarginCard", "make_result", "notice_sort_key", "result_sort_key",
    "PREVIEW_HEAD_ROWS", "PREVIEW_RAW_ROWS", "ChannelConversion", "ColumnInfo",
    "DCSweepBuildResult", "RawTable", "ReadOptions", "TablePreview", "TimeAxisSpec",
    "WaveformBuildResult",
    "MICRO", "format_metric_value", "format_number", "format_pct", "format_si", "format_spec",
    "parse_unit",
]
