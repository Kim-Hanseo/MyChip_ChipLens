"""D6 / D8 (contract 4.2, 4.3): sim deviation (mean vs mean, offset, sim 0) and bandwidth warning."""

from __future__ import annotations

import math

import pytest

from core.judge import apply_bandwidth_check, apply_sim_comparison, bandwidth_limit_s
from core.models import AnalysisSettings, Source, Stats, WarningCode, make_result

SIM = Source.SIM


def _timing(metric_id: str, mean: float, worst: float | None = None, *, path: str | None = None,
            channel_id: str = "CH3", source: Source = Source.MEASURED):
    worst = mean if worst is None else worst
    return make_result(metric_id, source=source, path=path, channel_id=channel_id, value=worst,
                       stats=Stats(mean=mean, min=min(mean, worst), max=max(mean, worst), std=0.0, n=8))


def _level(metric_id: str, value: float | None, *, source: Source = Source.MEASURED):
    return make_result(metric_id, source=source, channel_id="CH3", value=value)


# ---- sim deviation --------------------------------------------------------------------------


def test_deviation_uses_means_and_warns():
    meas = _timing("tplh", 6.0e-9, worst=6.4e-9, path="Buffer")
    sim = _timing("tplh", 4.5e-9, worst=4.6e-9, path="Buffer", source=SIM)
    (r,), notices = apply_sim_comparison([meas], [sim], AnalysisSettings())
    assert r.sim_value == pytest.approx(4.5e-9)  # sim mean, not worst
    assert r.deviation_pct == pytest.approx(100.0 / 3.0)  # (6.0 - 4.5) / 4.5, means only
    assert r.warnings == [WarningCode.SIM_DEVIATION]
    (n,) = notices
    assert n.code == WarningCode.SIM_DEVIATION
    assert (n.metric_id, n.path, n.channel_id, n.source) == ("tplh", "Buffer", "CH3", Source.MEASURED)
    assert n.message == "Buffer tpLH 시뮬 대비 +33.3% (허용 ±20.0% 초과)"
    assert meas.sim_value is None and meas.warnings == []  # input untouched


def test_delay_offset_only_for_tplh_tphl():
    settings = AnalysisSettings(delay_offset_s=1.5e-9)
    meas = [_timing("tplh", 6.0e-9, path="Buffer"), _timing("tphl", 5.7e-9, path="Buffer"),
            _timing("rise_time", 3.0e-9)]
    sim = [_timing("tplh", 4.5e-9, path="Buffer", source=SIM), _timing("tphl", 4.2e-9, path="Buffer", source=SIM),
           _timing("rise_time", 2.0e-9, source=SIM)]
    out, notices = apply_sim_comparison(meas, sim, settings)
    tplh, tphl, rise = out
    assert tplh.deviation_pct == pytest.approx(0.0, abs=1e-9)  # 6.0 - 1.5 = 4.5
    assert tphl.deviation_pct == pytest.approx(0.0, abs=1e-9)
    assert rise.deviation_pct == pytest.approx(50.0)  # offset not applied
    assert [n.metric_id for n in notices] == ["rise_time"]
    assert tplh.warnings == [] and rise.warnings == [WarningCode.SIM_DEVIATION]


def test_sim_zero_gives_no_deviation_but_keeps_sim_value():
    (r,), notices = apply_sim_comparison([_level("vol", 0.05)], [_level("vol", 0.0, source=SIM)],
                                         AnalysisSettings())
    assert r.sim_value == 0.0
    assert r.deviation_pct is None
    assert r.warnings == [] and notices == []


def test_missing_values_give_no_deviation():
    (r,), _ = apply_sim_comparison([_level("voh", 1.75)], [_level("voh", None, source=SIM)], AnalysisSettings())
    assert r.sim_value is None and r.deviation_pct is None
    (r,), _ = apply_sim_comparison([_level("voh", None)], [_level("voh", 1.8, source=SIM)], AnalysisSettings())
    assert r.sim_value == 1.8 and r.deviation_pct is None


def test_pairing_by_key_and_sim_compare_flag():
    meas = [_timing("tpd", 6.0e-9, path="Buffer"),  # sim_compare False
            _timing("rise_time", 3.0e-9, channel_id="CH3")]
    sim = [_timing("tpd", 4.5e-9, path="Buffer", source=SIM),
           _timing("rise_time", 2.0e-9, channel_id="CH5", source=SIM)]  # different channel: no pair
    out, notices = apply_sim_comparison(meas, sim, AnalysisSettings())
    assert all(r.sim_value is None and r.deviation_pct is None for r in out)
    assert notices == []


def test_tolerance_is_strict_and_negative_deviation_warns():
    meas, sim = _level("voh", 3.0), _level("voh", 2.0, source=SIM)  # exactly +50 %
    (r,), notices = apply_sim_comparison([meas], [sim], AnalysisSettings(sim_tolerance_pct=50.0))
    assert r.deviation_pct == 50.0 and r.warnings == [] and notices == []
    (r,), notices = apply_sim_comparison([meas], [sim], AnalysisSettings(sim_tolerance_pct=49.9))
    assert r.warnings == [WarningCode.SIM_DEVIATION]
    (r,), notices = apply_sim_comparison([_level("voh", 1.0)], [sim], AnalysisSettings())
    assert r.deviation_pct == -50.0
    assert notices[0].message == "CH3 VOH 시뮬 대비 -50.0% (허용 ±20.0% 초과)"


def test_existing_warnings_are_kept_sorted():
    meas = make_result("tplh", path="Buffer", channel_id="CH3", value=6e-9,
                       stats=Stats(mean=6e-9, min=6e-9, max=6e-9, std=0.0, n=3),
                       warnings=[WarningCode.UNPAIRED_EDGES])
    (r,), _ = apply_sim_comparison([meas], [_timing("tplh", 4.5e-9, path="Buffer", source=SIM)], AnalysisSettings())
    assert r.warnings == sorted([WarningCode.SIM_DEVIATION, WarningCode.UNPAIRED_EDGES])


# ---- bandwidth ------------------------------------------------------------------------------


def test_bandwidth_limit_values():
    assert bandwidth_limit_s(500e6) == pytest.approx(1.4e-9)
    assert bandwidth_limit_s(100e6) == pytest.approx(7.0e-9)


@pytest.mark.parametrize(("bw", "flagged"), [(500e6, []), (100e6, ["rise_time", "fall_time"]), (None, [])])
def test_bandwidth_demo_cases(bw, flagged):
    results = [_timing("rise_time", 3.0e-9, worst=3.1e-9), _timing("fall_time", 2.5e-9),
               _timing("tplh", 6.0e-9, path="Buffer")]
    out, notices = apply_bandwidth_check(results, AnalysisSettings(bandwidth_hz=bw))
    got = [r.metric_id for r in out if WarningCode.BANDWIDTH_LIMIT in r.warnings]
    assert got == flagged
    assert sorted(n.metric_id for n in notices) == sorted(flagged)
    assert all(n.code == WarningCode.BANDWIDTH_LIMIT and n.channel_id == "CH3" for n in notices)


def test_bandwidth_boundary_is_strict_and_uses_mean():
    bw = 100e6
    limit = bandwidth_limit_s(bw)
    at_limit = _timing("rise_time", limit, worst=limit * 0.5)
    below = _timing("fall_time", math.nextafter(limit, 0.0), worst=limit * 2.0)  # worst above, mean below
    out, notices = apply_bandwidth_check([at_limit, below], AnalysisSettings(bandwidth_hz=bw))
    assert out[0].warnings == []
    assert out[1].warnings == [WarningCode.BANDWIDTH_LIMIT]
    assert [n.metric_id for n in notices] == ["fall_time"]
    assert "100 MHz" in notices[0].message and "7.00 ns" in notices[0].message


def test_bandwidth_ignores_sim_and_missing_stats():
    sim = _timing("rise_time", 1e-9, source=SIM)
    no_stats = make_result("rise_time", channel_id="CH3", value=None)
    out, notices = apply_bandwidth_check([sim, no_stats], AnalysisSettings(bandwidth_hz=100e6))
    assert all(r.warnings == [] for r in out) and notices == []
