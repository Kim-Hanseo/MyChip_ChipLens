"""Small artificial signals for analyzer unit tests (deterministic, no files)."""

from __future__ import annotations

from collections.abc import Callable, Sequence

import numpy as np
import pytest

from core.models import (
    ChannelInfo,
    ChannelMap,
    DCSweep,
    MeasurementSet,
    Path,
    SessionInfo,
    Waveform,
)


def trapezoid(t: np.ndarray, t50s: Sequence[float], *, low: float = 0.0, high: float = 1.0,
              edge_s: float = 1e-9, start_high: bool = False) -> np.ndarray:
    """Alternating linear-ramp edges centred on `t50s` (10-90 % time = edge_s, full ramp 1.25 x)."""
    full = 1.25 * edge_s
    y = np.full(t.shape, high if start_high else low, dtype=np.float64)
    sign = -1.0 if start_high else 1.0
    for t50 in t50s:
        frac = np.clip((t - (t50 - full / 2)) / full, 0.0, 1.0)
        y += sign * (high - low) * frac
        sign = -sign
    return y


@pytest.fixture
def time_axis() -> Callable[..., np.ndarray]:
    """time_axis(n, dt, t0) -> uniform time array (s)."""

    def _t(n: int = 2000, dt: float = 0.1e-9, t0: float = 0.0) -> np.ndarray:
        return t0 + np.arange(n, dtype=np.float64) * dt

    return _t


@pytest.fixture
def wave() -> Callable[..., Waveform]:
    """wave(channel_id, t, values, quantity="V") -> Waveform."""

    def _w(channel_id: str, t: np.ndarray, values: np.ndarray, quantity: str = "V") -> Waveform:
        return Waveform(channel_id=channel_id, quantity=quantity, time_s=t, values=values)

    return _w


@pytest.fixture
def ramp() -> Callable[..., np.ndarray]:
    return trapezoid


@pytest.fixture
def mset() -> Callable[..., MeasurementSet]:
    """mset(roles, waveforms, paths=(), sweeps=(), source="measured") -> MeasurementSet.

    `roles` is a list of (channel_id, role) in ChannelMap order; `paths` a list of
    (name, input, output, polarity).
    """

    def _m(roles: Sequence[tuple[str, str]], waveforms: Sequence[Waveform],
           paths: Sequence[tuple[str, str, str, str]] = (), sweeps: Sequence[DCSweep] = (),
           source: str = "measured") -> MeasurementSet:
        return MeasurementSet(
            session=SessionInfo(source=source),
            channel_map=ChannelMap(channels=[ChannelInfo(channel_id=c, role=r) for c, r in roles]),
            paths=[Path(name=n, input_channel=i, output_channel=o, polarity=p) for n, i, o, p in paths],
            waveforms=list(waveforms),
            dc_sweeps=list(sweeps),
        )

    return _m
