"""Golden test (D11): DC/power (scope + DMM), functional check, and the error-injected scope file."""

from __future__ import annotations

import pytest

from core.models import WarningCode


@pytest.mark.parametrize("metric_id", ("voh", "vol"))
def test_output_levels(metric_id, golden, scope_out, pick, check_answer):
    r = pick(scope_out.results, metric_id, channel_id="CH3")
    check_answer(r.value, golden["answers"]["scope"][metric_id], metric_id)
    assert r.stats is None
    assert set(r.evidence.ref_levels_v) == {"low", "high"}


def test_idd_and_power(golden, scope_out, pick, check_answer):
    ans = golden["answers"]["scope"]
    idd = pick(scope_out.results, "idd_avg", channel_id="CH4")
    check_answer(idd.value, ans["idd_avg"], "idd_avg")
    p = pick(scope_out.results, "avg_power", channel_id="CH4")
    check_answer(p.value, ans["avg_power"], "avg_power")
    # no VDD channel -> logic VDD is used and recorded
    assert p.evidence.params["vdd_v"] == ans["avg_power"]["logic_vdd_v"]
    assert p.evidence.params["idd_avg_a"] == pytest.approx(idd.value)


def test_iddq_from_dmm(golden, scope_out, pick, check_answer):
    ans = golden["answers"]["dmm"]["iddq"]
    r = pick(scope_out.results, "iddq", channel_id=ans["sweep_name"])
    check_answer(r.value, ans, "iddq")
    assert r.evidence.params["vdd_v"] == ans["logic_vdd_v"]


def test_functional_normal(golden, scope_out, pick):
    ans = golden["answers"]["scope"]["match_rate"]
    r = pick(scope_out.results, "match_rate", channel_id="CH3")
    assert r.value == ans["value"]
    assert r.warnings == []
    f = scope_out.functional
    assert f is not None
    assert f.channel_id == "CH3" and f.clk_channel_id == "CH1"
    assert f.threshold_v == golden["setup"]["logic_vdd_v"] / 2
    assert f.measured_bits == golden["bits"]
    assert f.expected_bits == golden["bits"]
    assert f.compared_cycles == ans["compared_cycles"]
    assert f.matched_cycles == ans["matched_cycles"]
    assert f.mismatch_cycles == ans["mismatch_cycles"]
    assert f.first_mismatch == ans["first_mismatch"]
    assert f.match_rate_pct == ans["value"]
    # sample times are the CLK rising 50 % crossings
    ref = golden["edges"]["scope"]["clk_rise_s"]
    assert len(f.sample_times_s) == len(ref)
    assert max(abs(a - b) for a, b in zip(f.sample_times_s, ref, strict=True)) < 0.05e-9


def test_functional_error_file(golden, scope_err_out, pick):
    ans = golden["answers"]["scope_err"]["match_rate"]
    r = pick(scope_err_out.results, "match_rate", channel_id="CH3")
    assert r.value == ans["value"]
    f = scope_err_out.functional
    assert f.measured_bits == golden["bits_err"]
    assert f.compared_cycles == ans["compared_cycles"]
    assert f.matched_cycles == ans["matched_cycles"]
    assert f.mismatch_cycles == ans["mismatch_cycles"]
    assert f.first_mismatch == ans["first_mismatch"]
    n = f.first_mismatch
    assert f.expected_bits[n - 1] == ans["expected_bit"]
    assert f.measured_bits[n - 1] == ans["measured_bit"]


@pytest.mark.parametrize("metric_id", ("tplh", "tphl"))
def test_error_file_delays_not_corrupted(metric_id, golden, scope_err_out, pick, check_answer):
    """The inverted bit shifts one OUT edge by a whole cycle; pairing must not produce a ~100 ns delay."""
    ans = golden["answers"]["scope_err"][metric_id]
    r = pick(scope_err_out.results, metric_id, path="Buffer")
    for mode in ans["check"]:
        measured = r.value if mode == "worst" else r.stats.mean
        check_answer(measured, ans, f"err {metric_id} {mode}")


def test_error_file_tpd_and_unpaired_warning(golden, scope_err_out, pick, check_answer):
    tpd = pick(scope_err_out.results, "tpd", path="Buffer")
    check_answer(tpd.value, golden["answers"]["scope"]["tpd"], "err tpd worst")
    # the IN edge whose OUT edge moved one cycle later is dropped (outside the D4 window)
    tplh = pick(scope_err_out.results, "tplh", path="Buffer")
    assert WarningCode.UNPAIRED_EDGES in tplh.warnings
    assert tplh.stats.n == golden["transitions"]["in_rise"] - 1
    notices = [
        n for n in scope_err_out.notices
        if n.code == WarningCode.UNPAIRED_EDGES and n.metric_id == "tplh"
    ]
    assert len(notices) == 1
    assert notices[0].path == "Buffer" and notices[0].channel_id == "CH3"


def test_normal_file_has_no_notices(scope_out):
    assert scope_out.notices == []
