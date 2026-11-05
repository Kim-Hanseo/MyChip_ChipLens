"""Unit tests: timing analyzer edge cases (no edges, inverting path, D4 pairing window, slack, clock)."""

from __future__ import annotations

import numpy as np
import pytest

from core.analyzers import analyze_timing
from core.models import AnalysisSettings, Source, WarningCode

S = AnalysisSettings(logic_vdd_v=1.8)
NS = 1e-9


def _get(out, metric_id, **kw):
    found = [r for r in out.results if r.metric_id == metric_id
             and all(getattr(r, k) == v for k, v in kw.items())]
    assert len(found) == 1, (metric_id, kw, len(found))
    return found[0]


def _ids(out):
    return sorted({r.metric_id for r in out.results})


def _has_notice(out, code, metric_id, **kw):
    return any(n.code == code and n.metric_id == metric_id
               and all(getattr(n, k) == v for k, v in kw.items()) for n in out.notices)


@pytest.fixture
def t(time_axis):
    return time_axis(10_001, 0.1 * NS)  # 0 .. 1000 ns


def test_no_edges_gives_insufficient_edges(t, wave, mset):
    flat_out = wave("OUT", t, np.full(t.shape, 1.2))
    flat_clk = wave("CLK", t, np.zeros(t.shape))
    flat_in = wave("IN", t, np.zeros(t.shape))
    m = mset([("CLK", "CLK"), ("IN", "IN"), ("OUT", "OUT")], [flat_clk, flat_in, flat_out],
             paths=[("P", "IN", "OUT", "non_inverting")])
    out = analyze_timing(m, S)
    for mid, ch in (("rise_time", "OUT"), ("fall_time", "OUT"), ("setup_slack", "OUT"),
                    ("hold_slack", "OUT"), ("period", "CLK"), ("frequency", "CLK"), ("duty_cycle", "CLK")):
        r = _get(out, mid, channel_id=ch)
        assert r.value is None and r.stats is None
        assert r.warnings == [WarningCode.INSUFFICIENT_EDGES]
        assert _has_notice(out, WarningCode.INSUFFICIENT_EDGES, mid, channel_id=ch, path=None)
    for mid in ("tplh", "tphl"):
        r = _get(out, mid, path="P")
        assert r.value is None and r.warnings == [WarningCode.INSUFFICIENT_EDGES]
        assert r.channel_id == "OUT"
        assert _has_notice(out, WarningCode.INSUFFICIENT_EDGES, mid, path="P", channel_id="OUT")
    assert "tpd" not in _ids(out)  # neither tplh nor tphl has a value
    assert all(n.source == Source.MEASURED and n.message for n in out.notices)


def test_inverting_path(t, wave, ramp, mset):
    in_t50 = [100 * NS, 300 * NS, 500 * NS, 700 * NS]
    out_t50 = [103 * NS, 304 * NS, 503 * NS, 704 * NS]  # IN rise -> OUT fall (3 ns), IN fall -> OUT rise (4 ns)
    waves = [wave("IN", t, ramp(t, in_t50, high=1.8, edge_s=1 * NS)),
             wave("OUT", t, ramp(t, out_t50, high=1.8, edge_s=2 * NS, start_high=True))]
    roles = [("IN", "IN"), ("OUT", "OUT")]
    out = analyze_timing(mset(roles, waves, paths=[("Inv", "IN", "OUT", "inverting")]), S)
    tphl = _get(out, "tphl", path="Inv")
    tplh = _get(out, "tplh", path="Inv")
    tpd = _get(out, "tpd", path="Inv")
    assert tphl.value == pytest.approx(3 * NS, abs=1e-15) and tphl.stats.n == 2
    assert tplh.value == pytest.approx(4 * NS, abs=1e-15) and tplh.stats.n == 2
    assert tpd.value == pytest.approx(4 * NS, abs=1e-15) and tpd.stats.n == 4
    assert [e.t_start_s for e in tphl.evidence.edges] == pytest.approx([100 * NS, 500 * NS])
    assert tpd.evidence.worst_time_s == pytest.approx(304 * NS)
    assert out.notices == []
    # the same data declared non_inverting: no output edge of the same direction inside the window
    out2 = analyze_timing(mset(roles, waves, paths=[("Inv", "IN", "OUT", "non_inverting")]), S)
    for mid in ("tplh", "tphl"):
        r = _get(out2, mid, path="Inv")
        assert r.value is None
        assert r.warnings == [WarningCode.INSUFFICIENT_EDGES, WarningCode.UNPAIRED_EDGES]
        assert _has_notice(out2, WarningCode.UNPAIRED_EDGES, mid, path="Inv", channel_id="OUT")
    assert "tpd" not in _ids(out2)


def test_pairing_window_drops_late_output_edge(t, wave, ramp, mset):
    in_t50 = [100 * NS, 200 * NS, 600 * NS, 900 * NS]  # min spacing 100 ns -> window 50 ns
    out_t50 = [106 * NS, 205.5 * NS, 680 * NS, 905.5 * NS]  # third OUT edge 80 ns late
    m = mset(
        [("IN", "IN"), ("OUT", "OUT")],
        [wave("IN", t, ramp(t, in_t50, high=1.8)), wave("OUT", t, ramp(t, out_t50, high=1.8))],
        paths=[("Buf", "IN", "OUT", "non_inverting")],
    )
    out = analyze_timing(m, S)
    tplh = _get(out, "tplh", path="Buf")
    assert tplh.warnings == [WarningCode.UNPAIRED_EDGES]
    assert tplh.stats.n == 1 and tplh.value == pytest.approx(6 * NS, abs=1e-15)
    tphl = _get(out, "tphl", path="Buf")
    assert tphl.warnings == [] and tphl.stats.n == 2
    assert tphl.value == pytest.approx(5.5 * NS, abs=1e-15)
    assert _get(out, "tpd", path="Buf").value == pytest.approx(6 * NS, abs=1e-15)
    unpaired = [n for n in out.notices if n.code == WarningCode.UNPAIRED_EDGES]
    assert len(unpaired) == 1
    assert (unpaired[0].metric_id, unpaired[0].path, unpaired[0].channel_id) == ("tplh", "Buf", "OUT")


def test_single_input_edge_has_unbounded_window(t, wave, ramp, mset):
    m = mset(
        [("IN", "IN"), ("OUT", "OUT")],
        [wave("IN", t, ramp(t, [100 * NS])), wave("OUT", t, ramp(t, [150 * NS]))],
        paths=[("P", "IN", "OUT", "non_inverting")],
    )
    out = analyze_timing(m, S)
    assert _get(out, "tplh", path="P").value == pytest.approx(50 * NS, abs=1e-15)
    assert _get(out, "tphl", path="P").value is None  # no falling edge at all


def test_clock_period_frequency_duty(t, wave, ramp, mset):
    edges = []
    for k in range(5):
        edges += [(10 + 100 * k) * NS, (40 + 100 * k) * NS]  # 10 MHz, 30 % duty
    m = mset([("CLK", "CLK")], [wave("CLK", t, ramp(t, edges, high=1.8))])
    out = analyze_timing(m, S)
    period = _get(out, "period", channel_id="CLK")
    assert period.value == pytest.approx(100 * NS, abs=1e-15) and period.stats.n == 4
    assert period.evidence.ref_levels_v["v50"] == pytest.approx(0.9)
    assert _get(out, "frequency", channel_id="CLK").value == pytest.approx(1e7)
    duty = _get(out, "duty_cycle", channel_id="CLK")
    assert duty.value == pytest.approx(30.0) and duty.stats.n == 4
    assert duty.evidence.edges[0].t_end_s == pytest.approx(40 * NS)


def test_setup_hold_slack_on_data_channel(t, wave, ramp, mset):
    clk_edges = []
    for k in range(4):
        clk_edges += [(50 + 100 * k) * NS, (100 + 100 * k) * NS]
    data_t50 = [20 * NS, 120 * NS, 230 * NS]  # first transition precedes every CLK rise (no hold)
    m = mset(
        [("CLK", "CLK"), ("D", "DATA")],
        [wave("CLK", t, ramp(t, clk_edges, high=1.8)), wave("D", t, ramp(t, data_t50, high=1.8))],
    )
    out = analyze_timing(m, S)
    setup = _get(out, "setup_slack", channel_id="D")
    assert setup.stats.n == 3
    assert [e.value for e in setup.evidence.edges] == pytest.approx([30 * NS, 30 * NS, 20 * NS])
    assert setup.value == pytest.approx(20 * NS) and setup.evidence.worst_time_s == pytest.approx(230 * NS)
    hold = _get(out, "hold_slack", channel_id="D")
    assert hold.stats.n == 2
    assert hold.value == pytest.approx(70 * NS) and hold.evidence.worst_time_s == pytest.approx(120 * NS)
    assert set(hold.evidence.ref_levels_v) == {"clk_v50", "data_v50"}
    assert "rise_time" not in _ids(out)  # DATA channels get slack only


def test_skips_without_waveforms_clk_or_for_unused(t, wave, ramp, mset):
    out_wf = wave("OUT", t, ramp(t, [100 * NS, 300 * NS], high=1.8))
    m = mset(
        [("CLK", "CLK"), ("IN", "IN"), ("OUT", "OUT"), ("X", "UNUSED")],
        [out_wf, wave("X", t, ramp(t, [100 * NS]))],
        paths=[("NoIn", "IN", "OUT", "non_inverting"), ("Unused", "X", "OUT", "non_inverting")],
    )
    out = analyze_timing(m, S)
    assert _ids(out) == ["fall_time", "rise_time"]  # no CLK waveform -> no slack/clock, no paths
    assert out.notices == []


def test_sim_source_propagates(t, wave, ramp, mset):
    m = mset([("OUT", "OUT")], [wave("OUT", t, np.zeros(t.shape))], source="sim")
    out = analyze_timing(m, S)
    assert {r.source for r in out.results} == {Source.SIM}
    assert {n.source for n in out.notices} == {Source.SIM}
