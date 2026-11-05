"""Enumerations. The string values are part of the contract (JSON + UI)."""

from __future__ import annotations

from enum import StrEnum


class Role(StrEnum):
    CLK = "CLK"
    IN = "IN"
    OUT = "OUT"
    EN = "EN"
    DATA = "DATA"
    VDD = "VDD"
    IDD = "IDD"
    UNUSED = "UNUSED"


class Source(StrEnum):
    MEASURED = "measured"
    SIM = "sim"


class Polarity(StrEnum):
    NON_INVERTING = "non_inverting"
    INVERTING = "inverting"


class Category(StrEnum):
    TIMING = "timing"
    DC = "dc"
    FUNCTIONAL = "functional"


class Verdict(StrEnum):
    PASS = "PASS"
    MARGINAL = "MARGINAL"
    FAIL = "FAIL"


class Aggregate(StrEnum):
    """How `AnalysisResult.value` is derived from per-edge values."""

    MAX = "max"  # worst = largest
    MIN = "min"  # worst = smallest
    MEAN = "mean"  # value is the mean
    SINGLE = "single"  # one scalar, no per-edge distribution


class Target(StrEnum):
    CHANNEL = "channel"
    PATH = "path"
    SWEEP = "sweep"


class Quantity(StrEnum):
    VOLTAGE = "V"
    CURRENT = "A"


class EdgeKind(StrEnum):
    RISE = "rise"
    FALL = "fall"


class FileKind(StrEnum):
    CSV = "csv"  # .csv
    XLSX = "xlsx"  # .xlsx / .xlsm
    TEXT = "text"  # any other delimited text (.txt, .dat, ngspice wrdata ...)


class WarningCode(StrEnum):
    """Warning codes. Owner (who emits it) is fixed in docs/contract.md section 5."""

    # judge
    BANDWIDTH_LIMIT = "BANDWIDTH_LIMIT"
    SIM_DEVIATION = "SIM_DEVIATION"
    # analyzers
    INSUFFICIENT_EDGES = "INSUFFICIENT_EDGES"
    UNPAIRED_EDGES = "UNPAIRED_EDGES"
    EXPECTED_LENGTH_MISMATCH = "EXPECTED_LENGTH_MISMATCH"
    OUT_OF_SWEEP_RANGE = "OUT_OF_SWEEP_RANGE"
    MISSING_ROLE = "MISSING_ROLE"
    # adapters
    ENCODING_FALLBACK = "ENCODING_FALLBACK"
    NAN_DROPPED = "NAN_DROPPED"
    NON_MONOTONIC_AXIS = "NON_MONOTONIC_AXIS"
    SUSPICIOUS_RANGE = "SUSPICIOUS_RANGE"
    TIME_COLUMN_MISMATCH = "TIME_COLUMN_MISMATCH"


# UI display helpers (pure data)
ROLE_LABELS: dict[Role, str] = {
    Role.CLK: "CLK (클럭)",
    Role.IN: "IN (입력)",
    Role.OUT: "OUT (출력)",
    Role.EN: "EN (인에이블)",
    Role.DATA: "DATA (데이터)",
    Role.VDD: "VDD (전원 전압)",
    Role.IDD: "IDD (전원 전류)",
    Role.UNUSED: "사용 안 함",
}

VERDICT_SYMBOLS: dict[Verdict | None, str] = {
    Verdict.PASS: "✓",
    Verdict.MARGINAL: "!",
    Verdict.FAIL: "✕",
    None: "–",
}

VERDICT_LABELS: dict[Verdict | None, str] = {
    Verdict.PASS: "PASS",
    Verdict.MARGINAL: "MARGINAL",
    Verdict.FAIL: "FAIL",
    None: "스펙 없음",
}
