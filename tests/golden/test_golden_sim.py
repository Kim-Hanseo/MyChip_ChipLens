"""Golden test (D11): ngspice wrdata sim file (no noise, no ringing) through the same analyzers."""

from __future__ import annotations

import pytest

from core.models import Source

SIM_TARGETS = {
    "tplh": {"path": "Buffer"},
    "tphl": {"path": "Buffer"},
    "rise_time": {"channel_id": "CH3"},
    "fall_time": {"channel_id": "CH3"},
    "voh": {"channel_id": "CH3"},
    "vol": {"channel_id": "CH3"},
    "period": {"channel_id": "CH1"},
    "duty_cycle": {"channel_id": "CH1"},
}


@pytest.mark.parametrize("metric_id", sorted(SIM_TARGETS))
def test_sim_metrics(metric_id, golden, sim_out, pick, check_answer):
    r = pick(sim_out.results, metric_id, **SIM_TARGETS[metric_id])
    ans = golden["answers"]["sim"][metric_id]
    check_answer(r.representative(), ans, f"sim {metric_id} mean")
    check_answer(r.value, ans, f"sim {metric_id} value")


def test_sim_set_shape(sim_out):
    assert all(r.source == Source.SIM for r in sim_out.results)
    ids = {r.metric_id for r in sim_out.results}
    # no IDD waveform and no DC sweep in the sim set -> skipped silently
    assert not ids & {"idd_avg", "avg_power", "iddq"}
    # no expected pattern -> no match_rate result, but the measured bit string is still produced
    assert "match_rate" not in ids
    assert sim_out.functional is not None and sim_out.functional.expected_bits is None
    assert sim_out.notices == []


def test_sim_functional_bits(golden, sim_out):
    assert sim_out.functional.measured_bits == golden["bits"]


@pytest.mark.parametrize("metric_id", ("tplh", "tphl", "rise_time", "fall_time", "voh"))
def test_sim_deviation_inputs(metric_id, golden, scope_out, sim_out, pick):
    """Analyzer side of D6: (measured mean - sim mean) / |sim mean| lands within ±2 %p of D11."""
    tgt = SIM_TARGETS[metric_id]
    m = pick(scope_out.results, metric_id, **tgt).representative()
    s = pick(sim_out.results, metric_id, **tgt).representative()
    dev = (m - s) / abs(s) * 100
    ans = golden["answers"]["sim_deviation_pct"][metric_id]
    assert dev == pytest.approx(ans["value"], abs=ans["abs_tol_pp"])
