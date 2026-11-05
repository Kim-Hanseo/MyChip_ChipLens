"""Shared helpers for the analyzers: channel selection, per-channel edge cache, result builders."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

import numpy as np

from core.models import (
    METRICS,
    Aggregate,
    AnalysisResult,
    AnalysisSettings,
    Edge,
    EdgeKind,
    EdgeSample,
    Evidence,
    Levels,
    MeasurementSet,
    Notice,
    Role,
    Source,
    Stats,
    WarningCode,
    Waveform,
    make_result,
)
from core.preprocess import detect_edges, estimate_levels


@dataclass(frozen=True)
class ChannelEdges:
    """Levels and edges of one waveform (computed once per analysis run)."""

    wf: Waveform
    levels: Levels
    edges: list[Edge]

    def t50(self, kind: EdgeKind | None = None) -> np.ndarray:
        return np.array([e.t50_s for e in self.edges if kind is None or e.kind == kind], dtype=np.float64)

    def of_kind(self, kind: EdgeKind) -> list[Edge]:
        return [e for e in self.edges if e.kind == kind]


@dataclass
class EdgeCache:
    """channel_id -> ChannelEdges, shared by the analyzers inside one `analyze_all` call."""

    mset: MeasurementSet
    settings: AnalysisSettings
    _store: dict[str, ChannelEdges] = field(default_factory=dict)

    def get(self, channel_id: str) -> ChannelEdges | None:
        if channel_id in self._store:
            return self._store[channel_id]
        wf = self.mset.waveform(channel_id)
        if wf is None:
            return None
        levels = estimate_levels(wf, self.settings)
        ce = ChannelEdges(wf=wf, levels=levels, edges=detect_edges(wf, levels, self.settings))
        self._store[channel_id] = ce
        return ce


@dataclass
class Collector:
    """Accumulates results and notices of one analyzer."""

    mset: MeasurementSet
    results: list[AnalysisResult] = field(default_factory=list)
    notices: list[Notice] = field(default_factory=list)

    @property
    def source(self) -> Source:
        return self.mset.session.source

    def target_name(self, path: str | None, channel_id: str | None) -> str:
        if path:
            return path
        if channel_id is None:
            return "-"
        if self.mset.channel_map.get(channel_id) is not None:
            return self.mset.channel_map.display_name(channel_id)
        return channel_id

    def notice(self, code: WarningCode, message: str, metric_id: str | None,
               path: str | None = None, channel_id: str | None = None) -> None:
        self.notices.append(
            Notice(code=code, message=message, source=self.source, metric_id=metric_id,
                   path=path, channel_id=channel_id)
        )

    def add(self, result: AnalysisResult) -> None:
        self.results.append(result)

    def insufficient(self, metric_id: str, *, path: str | None = None, channel_id: str | None = None,
                     ref_levels: dict[str, float] | None = None,
                     extra_warnings: Iterable[WarningCode] = (), reason: str | None = None) -> None:
        """Result with value=None + INSUFFICIENT_EDGES and the matching Notice."""
        label = METRICS[metric_id].label
        msg = f"{self.target_name(path, channel_id)} {label}: " + (
            reason or "계산에 필요한 엣지가 부족해 값을 구하지 못했습니다"
        )
        self.add(make_result(
            metric_id, source=self.source, path=path, channel_id=channel_id,
            evidence=Evidence(ref_levels_v=dict(ref_levels or {})),
            warnings=[WarningCode.INSUFFICIENT_EDGES, *extra_warnings],
        ))
        self.notice(WarningCode.INSUFFICIENT_EDGES, msg, metric_id, path, channel_id)

    def from_samples(self, metric_id: str, samples: list[EdgeSample], *, path: str | None = None,
                     channel_id: str | None = None, ref_levels: dict[str, float] | None = None,
                     warnings: Iterable[WarningCode] = ()) -> AnalysisResult | None:
        """Per-edge samples -> result (value per catalog aggregate, stats, worst time).

        Empty `samples` -> INSUFFICIENT_EDGES result (value None). Returns the result added.
        """
        warnings = list(warnings)
        if not samples:
            self.insufficient(metric_id, path=path, channel_id=channel_id, ref_levels=ref_levels,
                              extra_warnings=warnings)
            return None
        result = make_result(
            metric_id, source=self.source, path=path, channel_id=channel_id,
            **aggregate_samples(metric_id, samples, ref_levels or {}),
            warnings=warnings,
        )
        self.add(result)
        return result


def stats_of(values: np.ndarray) -> Stats:
    return Stats(
        mean=float(np.mean(values)),
        min=float(np.min(values)),
        max=float(np.max(values)),
        std=float(np.std(values)),
        n=int(values.shape[0]),
    )


def aggregate_samples(metric_id: str, samples: list[EdgeSample],
                      ref_levels: dict[str, float]) -> dict:
    """value / stats / evidence for a non-empty list of per-edge samples (sorted by t_s here)."""
    m = METRICS[metric_id]
    samples = sorted(samples, key=lambda s: (s.t_s, s.value))
    vals = np.array([s.value for s in samples], dtype=np.float64)
    worst: float | None = None
    if m.aggregate == Aggregate.MAX:
        i = int(np.argmax(vals))
        value, worst = float(vals[i]), samples[i].t_s
    elif m.aggregate == Aggregate.MIN:
        i = int(np.argmin(vals))
        value, worst = float(vals[i]), samples[i].t_s
    else:
        value = float(np.mean(vals))
    return {
        "value": value,
        "stats": stats_of(vals) if m.has_stats else None,
        "evidence": Evidence(edges=samples, ref_levels_v=dict(ref_levels), worst_time_s=worst),
    }


def channels_with_role(mset: MeasurementSet, *roles: Role) -> list[str]:
    """channel_ids (ChannelMap order) whose role is in `roles` and that have a waveform."""
    have = {w.channel_id for w in mset.waveforms}
    return [c.channel_id for c in mset.channel_map.channels if c.role in roles and c.channel_id in have]


def the_clk(mset: MeasurementSet) -> str | None:
    """"The CLK": first CLK channel (ChannelMap order) that has a waveform."""
    ids = channels_with_role(mset, Role.CLK)
    return ids[0] if ids else None
