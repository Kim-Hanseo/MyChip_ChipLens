"""Unit tests: level estimation and hysteresis edge detection on small artificial signals."""

from __future__ import annotations

import numpy as np
import pytest

from core.models import AnalysisSettings, EdgeKind, Levels
from core.preprocess import (
    detect_edges,
    detect_edges_array,
    estimate_levels,
    estimate_noise_sigma,
    smooth_values,
)

S = AnalysisSettings()
NS = 1e-9


def test_clean_ramps_exact_levels_and_crossings(time_axis, wave, ramp):
    t = time_axis(2001, 0.1 * NS)
    t50s = [50.03 * NS, 120.07 * NS]
    wf = wave("A", t, ramp(t, t50s, low=0.2, high=1.5, edge_s=2 * NS))
    lv = estimate_levels(wf, S)
    assert lv.low == pytest.approx(0.2, abs=1e-12)
    assert lv.high == pytest.approx(1.5, abs=1e-12)
    edges = detect_edges(wf, lv, S)
    assert [e.kind for e in edges] == [EdgeKind.RISE, EdgeKind.FALL]
    for e, t50 in zip(edges, t50s, strict=True):
        assert e.t50_s == pytest.approx(t50, abs=1e-15)
    rise, fall = edges
    # linear ramp: 10 % at t50 - edge/2, 90 % at t50 + edge/2
    assert rise.t10_s == pytest.approx(t50s[0] - 1 * NS, abs=1e-15)
    assert rise.t90_s == pytest.approx(t50s[0] + 1 * NS, abs=1e-15)
    assert fall.t90_s == pytest.approx(t50s[1] - 1 * NS, abs=1e-15)
    assert fall.t10_s == pytest.approx(t50s[1] + 1 * NS, abs=1e-15)


def test_negative_time_axis(time_axis, wave, ramp):
    t = time_axis(2001, 0.2 * NS, t0=-200 * NS)
    wf = wave("A", t, ramp(t, [-100.01 * NS, 50.05 * NS], high=1.8, edge_s=1 * NS))
    edges = detect_edges(wf, estimate_levels(wf, S), S)
    assert [round(e.t50_s / NS, 6) for e in edges] == [-100.01, 50.05]


def test_noise_and_ringing_do_not_duplicate_edges(time_axis, wave, ramp):
    rng = np.random.default_rng(7)
    t = time_axis(10_000, 0.2 * NS)
    t50s = [100.03 * NS + k * 173.1 * NS for k in range(11)]
    clean = ramp(t, t50s, low=0.0, high=1.0, edge_s=1.5 * NS)
    ring = np.zeros_like(t)
    sign = 1.0
    for t50 in t50s:  # 10 % overshoot ringing after every ramp end
        x = t - (t50 + 0.94 * NS)
        m = x >= 0
        ring[m] += sign * 0.16 * np.sin(2 * np.pi * 300e6 * x[m]) * np.exp(-x[m] / (3 * NS))
        sign = -sign
    wf = wave("A", t, clean + ring + rng.normal(0, 0.02, t.shape))
    edges = detect_edges(wf, estimate_levels(wf, S), S)
    assert len(edges) == len(t50s)
    assert [e.kind for e in edges] == [EdgeKind.RISE, EdgeKind.FALL] * 5 + [EdgeKind.RISE]
    assert np.max(np.abs(np.array([e.t50_s for e in edges]) - np.array(t50s))) < 0.1 * NS


def test_levels_exclude_ringing_precisely(time_axis, wave, ramp):
    """VOL/VOH to +/-0.5 mV although every edge rings with a 10 % overshoot."""
    rng = np.random.default_rng(11)
    t = time_axis(20_000, 0.2 * NS)
    t50s = [150.0 * NS + k * 211.3 * NS for k in range(18)]
    low, high = 0.05, 1.75
    clean = ramp(t, t50s, low=low, high=high, edge_s=3 * NS)
    ring = np.zeros_like(t)
    sign = 1.0
    for t50 in t50s:
        x = t - (t50 + 1.875 * NS)
        m = x >= 0
        ring[m] += sign * 0.27 * np.sin(2 * np.pi * 250e6 * x[m]) * np.exp(-x[m] / (2 * NS))
        sign = -sign
    wf = wave("A", t, clean + ring + rng.normal(0, 0.01, t.shape))
    lv = estimate_levels(wf, S)
    assert lv.low == pytest.approx(low, abs=5e-4)
    assert lv.high == pytest.approx(high, abs=5e-4)


def test_flat_signal_has_no_edges(time_axis, wave):
    t = time_axis(1000)
    for values in (np.full(t.shape, 0.7), 0.7 + np.random.default_rng(3).normal(0, 0.01, t.shape)):
        wf = wave("A", t, values)
        lv = estimate_levels(wf, S)
        assert lv.low == lv.high
        assert detect_edges(wf, lv, S) == []


def test_hysteresis_ignores_wobble_around_mid_level(time_axis, wave):
    t = time_axis(3000, 0.1 * NS)
    v = np.where(t < 100 * NS, 0.0, 1.0)
    mid = (t >= 100 * NS) & (t < 200 * NS)  # 100 ns plateau wobbling +/-4 % around 50 %
    v[mid] = 0.5 + 0.04 * np.sin(2 * np.pi * 50e6 * t[mid])
    edges = detect_edges_array(t, v, Levels(low=0.0, high=1.0))
    assert len(edges) == 1 and edges[0].kind == EdgeKind.RISE


def test_min_pulse_width_filter(time_axis, wave, ramp):
    t = time_axis(5000, 0.1 * NS)
    t50s = [100 * NS, 300 * NS, 301.5 * NS, 450 * NS]  # 1.5 ns glitch low pulse at 300 ns
    wf = wave("A", t, ramp(t, t50s, edge_s=0.3 * NS))
    lv = estimate_levels(wf, S)
    assert len(detect_edges(wf, lv, S)) == 4
    filt = AnalysisSettings(min_pulse_width_s=5 * NS)
    edges = detect_edges(wf, estimate_levels(wf, filt), filt)
    assert [e.kind for e in edges] == [EdgeKind.RISE, EdgeKind.FALL]
    assert [round(e.t50_s / NS, 6) for e in edges] == [100.0, 450.0]


def test_runt_pulse_has_no_far_level_crossing(time_axis, wave, ramp):
    t = time_axis(6000, 0.1 * NS)
    v = ramp(t, [100 * NS, 200 * NS], edge_s=1 * NS)
    runt = ramp(t, [400 * NS, 430 * NS], edge_s=1 * NS) * 0.75  # reaches 75 % only
    edges = detect_edges_array(t, v + runt, Levels(low=0.0, high=1.0))
    assert len(edges) == 4
    full_rise, full_fall, runt_rise, runt_fall = edges
    assert full_rise.t90_s is not None and full_fall.t90_s is not None
    assert runt_rise.t10_s is not None and runt_rise.t90_s is None
    assert runt_fall.t90_s is None and runt_fall.t10_s is not None


def test_smoothing_option(time_axis, wave, ramp):
    rng = np.random.default_rng(5)
    t = time_axis(8000, 0.1 * NS)
    t50s = [100 * NS + k * 97 * NS for k in range(8)]
    wf = wave("A", t, ramp(t, t50s, edge_s=4 * NS) + rng.normal(0, 0.12, t.shape))
    s = AnalysisSettings(smoothing_points=15)
    edges = detect_edges(wf, estimate_levels(wf, s), s)
    assert len(edges) == len(t50s)
    assert np.max(np.abs(np.array([e.t50_s for e in edges]) - np.array(t50s))) < 0.5 * NS
    x = np.arange(10.0)
    assert smooth_values(x, 0) is x and smooth_values(x, 2) is x
    assert smooth_values(x, 5).shape == x.shape


def test_noise_sigma_estimate():
    v = np.random.default_rng(1).normal(0, 0.01, 20_000)
    assert estimate_noise_sigma(v) == pytest.approx(0.01, rel=0.05)
