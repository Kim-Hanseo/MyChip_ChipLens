"""Adapter-stage contract types (upload -> preview -> raw table -> Waveform/DCSweep)."""

from __future__ import annotations

import pandas as pd
from pydantic import ConfigDict, Field, model_validator

from .base import ContractModel
from .enums import FileKind, Quantity
from .inputs import DCSweep, Waveform
from .results import Notice

PREVIEW_RAW_ROWS = 30  # TablePreview.raw_rows length limit
PREVIEW_HEAD_ROWS = 10  # TablePreview.head_rows length limit


class ReadOptions(ContractModel):
    """How to read a file. Auto-guessed by preview_file; the user may edit any field."""

    encoding: str | None = None  # text only: "utf-8-sig" or "cp949"; None for xlsx
    delimiter: str | None = None  # text only: ",", "\t", ";" or " " (= any whitespace run)
    sheet: str | None = None  # xlsx only: sheet name; None = first sheet
    header_row: int | None = Field(default=0, ge=0)  # 0-based index into raw rows; None = no header
    data_start_row: int | None = Field(default=None, ge=0)  # None = header_row + 1 (or 0 if no header)


class ColumnInfo(ContractModel):
    """One column of a table, with the unit extracted from its header."""

    name: str  # unique column key in RawTable.data (header text; duplicates get "_2", "_3")
    header: str  # original header text ("" if no header)
    base_name: str  # header with unit removed: "CH1(V)" -> "CH1"; default channel_id in the UI
    unit_text: str | None = None  # extracted unit text, e.g. "µA"; None if none/unknown
    si_unit: str | None = None  # "s", "V", "A", "W", "Hz", "%" or None
    scale: float = 1.0  # raw * scale = SI (from unit prefix)
    numeric: bool = True  # True if the column parses as numbers


class TablePreview(ContractModel):
    """Result of preview_file: guessed options + preview, for the upload UI."""

    file_name: str
    kind: FileKind
    options: ReadOptions  # options actually used (guessed, or the ones passed in)
    sheets: list[str] = Field(default_factory=list)  # xlsx sheet names in workbook order; [] for text
    raw_rows: list[list[str]] = Field(default_factory=list)  # first <= 30 rows BEFORE header handling
    columns: list[ColumnInfo] = Field(default_factory=list)
    time_candidates: list[str] = Field(default_factory=list)  # column names, best first
    head_rows: list[list[str]] = Field(default_factory=list)  # first <= 10 data rows, aligned to columns
    notices: list[Notice] = Field(default_factory=list)


class RawTable(ContractModel):
    """Parsed table. `data` values are RAW (no unit scaling).

    data.columns == [c.name for c in columns]; numeric columns are float64 (unparsable -> NaN),
    non-numeric columns are str. RangeIndex.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    file_name: str
    options: ReadOptions
    columns: list[ColumnInfo]
    data: pd.DataFrame
    notices: list[Notice] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check(self) -> RawTable:
        if [str(c) for c in self.data.columns] != [c.name for c in self.columns]:
            raise ValueError("RawTable.data columns must equal [c.name for c in columns]")
        return self

    def column(self, name: str) -> ColumnInfo | None:
        return next((c for c in self.columns if c.name == name), None)


class TimeAxisSpec(ContractModel):
    """Time axis: a column, or synthesized from start + interval when column is None."""

    column: str | None = None
    scale: float = 1.0  # raw -> seconds (e.g. 1e-9 if the column is in ns)
    start_s: float = 0.0  # used only when column is None
    interval_s: float | None = Field(default=None, gt=0)  # required when column is None

    @model_validator(mode="after")
    def _check(self) -> TimeAxisSpec:
        if self.column is None and self.interval_s is None:
            raise ValueError("interval_s is required when no time column is given")
        return self


class ChannelConversion(ContractModel):
    """Column -> Waveform conversion. SI value = raw * scale * probe_factor.

    For sim files, channel_id is the MEASURED channel_id the column maps to (re-keying, D3).
    """

    column: str
    channel_id: str = Field(min_length=1)
    quantity: Quantity  # "V" or "A"
    scale: float = 1.0  # unit prefix factor (mV -> 1e-3)
    probe_factor: float = 1.0  # probe attenuation (x10 -> 10.0)


class WaveformBuildResult(ContractModel):
    waveforms: list[Waveform] = Field(default_factory=list)  # same order as the conversions
    notices: list[Notice] = Field(default_factory=list)


class DCSweepBuildResult(ContractModel):
    sweep: DCSweep | None = None  # None if fewer than 1 valid point
    notices: list[Notice] = Field(default_factory=list)
