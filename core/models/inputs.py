"""Input (normalized) models. All values SI (s, V, A); see decisions D2/D3."""

from __future__ import annotations

import numpy as np
from pydantic import ConfigDict, Field, field_validator, model_validator

from .base import ContractModel, FloatArray
from .enums import EdgeKind, Polarity, Quantity, Role, Source
from .metrics import METRICS


class Waveform(ContractModel):
    """One channel's time series. `time_s` strictly increasing, same length as `values` (>= 2).

    Role is NOT stored here: ChannelMap is the single source of truth for roles.
    Note: do not compare Waveforms with `==` (numpy arrays).
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    channel_id: str = Field(min_length=1)
    quantity: Quantity  # "V" or "A" (SI, after unit prefix and probe factor)
    time_s: FloatArray
    values: FloatArray
    source_column: str | None = None  # original column name, for the raw-data tab
    source_unit: str | None = None  # original unit text, e.g. "mV"
    probe_factor: float = 1.0  # applied probe attenuation (already multiplied into values)

    @model_validator(mode="after")
    def _check(self) -> Waveform:
        n = self.time_s.shape[0]
        if n < 2:
            raise ValueError("waveform needs at least 2 samples")
        if self.values.shape[0] != n:
            raise ValueError("time_s and values must have the same length")
        if np.any(np.diff(self.time_s) <= 0):
            raise ValueError("time_s must be strictly increasing")
        return self

    @property
    def n_samples(self) -> int:
        return int(self.time_s.shape[0])

    @property
    def sample_interval_s(self) -> float:
        """Median sample interval (s)."""
        return float(np.median(np.diff(self.time_s)))

    @property
    def duration_s(self) -> float:
        return float(self.time_s[-1] - self.time_s[0])


class DCSweep(ContractModel):
    """DC sweep table (multimeter / Excel). x strictly increasing (adapter sorts)."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str = Field(default="DC", min_length=1)  # used as AnalysisResult.channel_id for iddq
    x: FloatArray  # SI, normally V
    y: FloatArray  # SI, normally A
    x_quantity: Quantity = Quantity.VOLTAGE
    y_quantity: Quantity = Quantity.CURRENT
    x_label: str | None = None  # original header, e.g. "전압(V)"
    y_label: str | None = None  # e.g. "전류(µA)"

    @model_validator(mode="after")
    def _check(self) -> DCSweep:
        if self.x.shape[0] < 1 or self.y.shape[0] != self.x.shape[0]:
            raise ValueError("x and y must be non-empty and the same length")
        if np.any(np.diff(self.x) <= 0):
            raise ValueError("x must be strictly increasing")
        return self


class ChannelInfo(ContractModel):
    channel_id: str = Field(min_length=1)
    role: Role
    label: str | None = None  # optional user label, e.g. "WL0"


class ChannelMap(ContractModel):
    """channel_id -> role/label. List order = UI order ("first CLK" = first in this list)."""

    channels: list[ChannelInfo] = Field(default_factory=list)

    @model_validator(mode="after")
    def _unique(self) -> ChannelMap:
        ids = [c.channel_id for c in self.channels]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate channel_id in ChannelMap")
        return self

    def get(self, channel_id: str) -> ChannelInfo | None:
        return next((c for c in self.channels if c.channel_id == channel_id), None)

    def role_of(self, channel_id: str) -> Role | None:
        c = self.get(channel_id)
        return c.role if c else None

    def ids_with_role(self, role: Role) -> list[str]:
        return [c.channel_id for c in self.channels if c.role == role]

    def display_name(self, channel_id: str) -> str:
        """Label if set, else channel_id."""
        c = self.get(channel_id)
        return c.label if c and c.label else channel_id


class Path(ContractModel):
    """A user-defined module path: input channel -> output channel (D3/D4)."""

    name: str = Field(min_length=1)
    input_channel: str = Field(min_length=1)
    output_channel: str = Field(min_length=1)
    polarity: Polarity = Polarity.NON_INVERTING


SignalPath = Path  # alias to avoid clashing with pathlib.Path at import sites


class Spec(ContractModel):
    """Spec limit in SI units. path/channel_id None = applies to every result of metric_id."""

    metric_id: str
    path: str | None = None
    channel_id: str | None = None
    min: float | None = None
    max: float | None = None

    @model_validator(mode="after")
    def _check(self) -> Spec:
        if self.metric_id not in METRICS:
            raise ValueError(f"unknown metric_id: {self.metric_id}")
        if self.min is None and self.max is None:
            raise ValueError("spec needs min or max")
        if self.min is not None and self.max is not None and self.min > self.max:
            raise ValueError("spec min > max")
        return self


class SessionInfo(ContractModel):
    """Metadata for one data set (display only; analysis reads only `source`)."""

    source: Source = Source.MEASURED
    chip_id: str | None = None
    temperature_c: float | None = None
    vdd_v: float | None = None  # condition shown in header; analysis uses AnalysisSettings.logic_vdd_v
    frequency_hz: float | None = None
    instrument: str | None = None
    sample_interval_s: float | None = None
    files: list[str] = Field(default_factory=list)
    notes: dict[str, str] = Field(default_factory=dict)


class AnalysisSettings(ContractModel):
    logic_vdd_v: float = Field(default=1.8, gt=0)
    bandwidth_hz: float | None = Field(default=None, gt=0)  # scope bandwidth; None = no D8 check
    marginal_threshold_pct: float = Field(default=10.0, ge=0)
    sim_tolerance_pct: float = Field(default=20.0, ge=0)
    delay_offset_s: float = 0.0  # PCB/probe delay, subtracted from measured tplh/tphl mean (D6)
    # edge detection
    edge_hysteresis_pct: float = Field(default=10.0, gt=0, lt=50)  # thresholds at 50 ± h % of swing
    min_pulse_width_s: float = Field(default=0.0, ge=0)  # 0 = filter off
    smoothing_points: int = Field(default=0, ge=0)  # Savitzky-Golay window in samples; 0 = off


class ExpectedPattern(ContractModel):
    """Expected output bit string. Spaces, '_', ',' (and tabs/newlines) are removed on validation."""

    bits: str
    channel_id: str | None = None  # None = first OUT channel in ChannelMap

    @field_validator("bits", mode="before")
    @classmethod
    def _clean(cls, v: object) -> str:
        s = "".join(ch for ch in str(v) if ch not in " _,\t\r\n")
        if not s:
            raise ValueError("expected bit string is empty")
        if set(s) - {"0", "1"}:
            raise ValueError("expected bits may contain only '0' and '1'")
        return s


class MeasurementSet(ContractModel):
    """Normalized data set (measured or sim) = analyzer input together with AnalysisSettings.

    The sim set uses the SAME channel_map and paths as the measured set, with its waveforms
    re-keyed to measured channel_ids (D3). Channels/paths without a waveform are skipped silently.
    """

    session: SessionInfo = Field(default_factory=SessionInfo)
    channel_map: ChannelMap = Field(default_factory=ChannelMap)
    paths: list[Path] = Field(default_factory=list)
    waveforms: list[Waveform] = Field(default_factory=list)
    dc_sweeps: list[DCSweep] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check(self) -> MeasurementSet:
        ids = [w.channel_id for w in self.waveforms]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate waveform channel_id")
        known = {c.channel_id for c in self.channel_map.channels}
        missing = [i for i in ids if i not in known]
        if missing:
            raise ValueError(f"waveform channel(s) not in ChannelMap: {missing}")
        names = [p.name for p in self.paths]
        if len(names) != len(set(names)):
            raise ValueError("duplicate path name")
        for p in self.paths:
            for ch in (p.input_channel, p.output_channel):
                if ch not in known:
                    raise ValueError(f"path '{p.name}' refers to unknown channel '{ch}'")
        sweep_names = [s.name for s in self.dc_sweeps]
        if len(sweep_names) != len(set(sweep_names)):
            raise ValueError("duplicate DC sweep name")
        return self

    def waveform(self, channel_id: str) -> Waveform | None:
        return next((w for w in self.waveforms if w.channel_id == channel_id), None)


class AnalysisRequest(ContractModel):
    measured: MeasurementSet
    sim: MeasurementSet | None = None
    specs: list[Spec] = Field(default_factory=list)
    expected: ExpectedPattern | None = None
    settings: AnalysisSettings = Field(default_factory=AnalysisSettings)

    @model_validator(mode="after")
    def _check(self) -> AnalysisRequest:
        if self.measured.session.source != Source.MEASURED:
            raise ValueError("measured set must have session.source == 'measured'")
        if self.sim is not None and self.sim.session.source != Source.SIM:
            raise ValueError("sim set must have session.source == 'sim'")
        return self


# ---- preprocess value objects (core.preprocess outputs) ----


class Levels(ContractModel):
    """Estimated logic levels of one channel (V or A)."""

    low: float
    high: float

    @property
    def swing(self) -> float:
        return self.high - self.low

    def at_pct(self, pct: float) -> float:
        """Level at pct % of the swing (50 -> mid level)."""
        return self.low + self.swing * pct / 100.0


class Edge(ContractModel):
    """One detected transition. Times are linear-interpolated crossings on the waveform time axis."""

    kind: EdgeKind
    t50_s: float
    t10_s: float | None = None  # 10 % crossing time (None if not found)
    t90_s: float | None = None  # 90 % crossing time (None if not found)
