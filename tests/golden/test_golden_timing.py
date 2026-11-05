"""Golden test (D11): timing metrics on the normal scope file (synth_scope.csv)."""

from __future__ import annotations

import numpy as np
import pytest

from core.models import METRICS, EdgeKind, Source
from core.preprocess import detect_edges, estimate_levels

PATH_METRICS = ("tplh", "tphl", "tpd")
OUT_EDGE_METRICS = ("rise_time", "fall_time")


def _target(metric_id: str) -> dict:
    if metric_id in PATH_METRICS:
        return {"path": "Buffer", "channel_id": "CH3"}
    if metric_id in ("period", "frequency", "duty_cycle"):
        return {"channel_id": "CH1"}
    return {"channel_id": "CH3"}


@pytest.mark.parametrize("metric_id", PATH_METRICS + OUT_EDGE_METRICS)
def test_edge_metrics_mean_and_worst(metric_id, golden, scope_out, pick, check_answer):
    ans = golden["answers"]["scope"][metric_id]
    r = pick(scope_out.results, metric_id, **_target(metric_id))
    assert r.stats is not None
    for mode in ans["check"]:
        measured = r.value if mode == "worst" else r.stats.mean
        check_answer(measured, ans, f"{metric_id} {mode}")
    # worst = max per catalog; value is the per-edge maximum
    assert r.value == pytest.approx(r.stats.max)
    assert r.warnings == []


@pytest.mark.parametrize("metric_id", ("period", "frequency", "duty_cycle"))
def test_clock_metrics(metric_id, golden, scope_out, pick, check_answer):
    r = pick(scope_out.results, metric_id, channel_id="CH1")
    check_answer(r.value, golden["answers"]["scope"][metric_id], metric_id)
    if METRICS[metric_id].has_stats:
        assert r.stats is not None and r.stats.n == golden["transitions"]["clk_rise"] - 1
        assert r.value == pytest.approx(r.stats.mean)
    else:
        assert r.stats is None


@pytest.mark.parametrize("metric_id", ("setup_slack", "hold_slack"))
def test_slack_worst(metric_id, golden, scope_out, pick, check_answer):
    r = pick(scope_out.results, metric_id, channel_id="CH3")
    check_answer(r.value, golden["answers"]["scope"][metric_id], f"{metric_id} worst")
    assert r.value == pytest.approx(r.stats.min)
    n_out = golden["transitions"]["out_rise"] + golden["transitions"]["out_fall"]
    assert r.stats.n == n_out


def test_edge_counts_and_times_match_golden(golden, scope_waveforms, settings):
    """No duplicated edges under 10 mV noise + 5 % ringing; 50 % crossings close to the exact times."""
    e = golden["edges"]["scope"]
    wf = {w.channel_id: w for w in scope_waveforms}
    cases = {
        "CH1": (e["clk_rise_s"], e["clk_fall_s"], 0.05e-9),
        "CH2": (e["in_rise_s"], e["in_fall_s"], 0.05e-9),
        "CH3": (e["out_rise_s"], e["out_fall_s"], 0.15e-9),
    }
    for ch, (rise_ref, fall_ref, tol) in cases.items():
        edges = detect_edges(wf[ch], estimate_levels(wf[ch], settings), settings)
        rises = np.array([x.t50_s for x in edges if x.kind == EdgeKind.RISE])
        falls = np.array([x.t50_s for x in edges if x.kind == EdgeKind.FALL])
        assert len(rises) == len(rise_ref), ch
        assert len(falls) == len(fall_ref), ch
        assert np.max(np.abs(rises - np.array(rise_ref))) < tol, ch
        assert np.max(np.abs(falls - np.array(fall_ref))) < tol, ch
        t50 = [x.t50_s for x in edges]
        assert t50 == sorted(t50)


def test_levels_are_refined(golden, scope_waveforms, settings):
    wf = {w.channel_id: w for w in scope_waveforms}
    clk = estimate_levels(wf["CH1"], settings)
    out = estimate_levels(wf["CH3"], settings)
    p = golden["params"]
    assert clk.low == pytest.approx(p["clk"]["low_v"], abs=1e-3)
    assert clk.high == pytest.approx(p["clk"]["high_v"], abs=1e-3)
    assert out.low == pytest.approx(p["out_scope"]["vol_v"], abs=5e-4)
    assert out.high == pytest.approx(p["out_scope"]["voh_v"], abs=5e-4)


def test_path_evidence(golden, scope_out, pick):
    n_rise = golden["transitions"]["out_rise"]
    n_fall = golden["transitions"]["out_fall"]
    for metric_id, n in (("tplh", n_rise), ("tphl", n_fall), ("tpd", n_rise + n_fall)):
        r = pick(scope_out.results, metric_id, path="Buffer")
        ev = r.evidence
        assert r.stats.n == n == len(ev.edges)
        ts = [x.t_s for x in ev.edges]
        assert ts == sorted(ts)
        assert set(ev.ref_levels_v) == {"in_v50", "out_v50"}
        worst = max(ev.edges, key=lambda x: x.value)
        assert ev.worst_time_s == worst.t_s
        for x in ev.edges:
            assert x.t_start_s < x.t_end_s == x.t_s
            assert x.value == pytest.approx(x.t_end_s - x.t_start_s)
    # tplh markers sit on the exact OUT rising crossings
    r = pick(scope_out.results, "tplh", path="Buffer")
    ref = np.array(golden["edges"]["scope"]["out_rise_s"])
    assert np.max(np.abs(np.array(r.evidence.edge_times_s) - ref)) < 0.15e-9


def test_rise_fall_evidence(scope_out, pick):
    for metric_id in OUT_EDGE_METRICS:
        r = pick(scope_out.results, metric_id, channel_id="CH3")
        ev = r.evidence
        assert set(ev.ref_levels_v) == {"low", "high", "v10", "v90"}
        assert ev.ref_levels_v["v10"] < ev.ref_levels_v["v90"]
        assert ev.worst_time_s == max(ev.edges, key=lambda x: x.value).t_s
        for x in ev.edges:
            assert x.t_start_s < x.t_s < x.t_end_s


def test_results_are_unjudged_and_sorted(scope_out):
    from core.models import result_sort_key

    assert scope_out.results == sorted(scope_out.results, key=result_sort_key)
    for r in scope_out.results:
        assert r.source == Source.MEASURED
        assert (r.spec, r.verdict, r.margin_pct, r.sim_value, r.deviation_pct) == (None,) * 5


def test_demo_margins_follow_from_worst_values(golden, scope_out, pick):
    """Analyzer side of the demo judgment: worst values put margins within ±2 %p of D11."""
    for s in golden["answers"]["demo_judgment"]["specs"]:
        r = pick(scope_out.results, s["metric_id"])
        if "max" in s:
            margin = (s["max"] - r.value) / abs(s["max"]) * 100
        else:
            margin = (r.value - s["min"]) / abs(s["min"]) * 100
        assert margin == pytest.approx(s["margin_pct"], abs=s["abs_tol_pp"]), s["metric_id"]
