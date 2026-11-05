"""Unit tests: DC/power and functional analyzers (iddq range, VDD channel, D7 bit compare, notices)."""

from __future__ import annotations

import numpy as np
import pytest

from core.analyzers import analyze_all, analyze_dc_power, analyze_functional, analyze_timing
from core.models import (
    AnalysisSettings,
    AnalyzerOutput,
    DCSweep,
    ExpectedPattern,
    WarningCode,
    notice_sort_key,
    result_sort_key,
)

S = AnalysisSettings(logic_vdd_v=1.8)
NS = 1e-9
BITS = "10110010"


def _get(out, metric_id, **kw):
    found = [r for r in out.results if r.metric_id == metric_id
             and all(getattr(r, k) == v for k, v in kw.items())]
    assert len(found) == 1, (metric_id, kw, len(found))
    return found[0]


@pytest.fixture
def t(time_axis):
    return time_axis(9_001, 0.1 * NS)  # 0 .. 900 ns


@pytest.fixture
def bit_set(t, wave, ramp, mset):
    """CLK rises at 50 + 100k ns (k = 0..7); OUT holds bit k during [100k, 100(k+1)) ns."""
    clk_edges = []
    for k in range(len(BITS)):
        clk_edges += [(50 + 100 * k) * NS, (75 + 100 * k) * NS]
    out_edges = [100 * k * NS for k in range(1, len(BITS)) if BITS[k] != BITS[k - 1]]

    def _make(roles=None, extra=()):
        waves = [wave("CLK", t, ramp(t, clk_edges, high=1.8)),
                 wave("OUT", t, ramp(t, out_edges, low=0.1, high=1.7, start_high=BITS[0] == "1")),
                 *extra]
        roles = roles or [("CLK", "CLK"), ("OUT", "OUT")]
        have = {c for c, _ in roles}
        return mset(roles, [w for w in waves if w.channel_id in have])

    return _make


def test_functional_without_expected_still_reports_bits(bit_set):
    out = analyze_functional(bit_set(), S, None)
    f = out.functional
    assert f.measured_bits == BITS
    assert f.sample_times_s == pytest.approx([(50 + 100 * k) * NS for k in range(len(BITS))])
    assert f.threshold_v == 0.9
    assert f.expected_bits is None and f.compared_cycles == 0 and f.match_rate_pct is None
    assert out.results == [] and out.notices == []


def test_functional_mismatches_are_one_based(bit_set):
    exp = BITS[:2] + ("0" if BITS[2] == "1" else "1") + BITS[3:5] + ("0" if BITS[5] == "1" else "1") + BITS[6:]
    out = analyze_functional(bit_set(), S, ExpectedPattern(bits=exp))
    f = out.functional
    assert f.mismatch_cycles == [3, 6] and f.first_mismatch == 3
    assert f.compared_cycles == 8 and f.matched_cycles == 6
    r = _get(out, "match_rate", channel_id="OUT")
    assert r.value == 75.0 and r.warnings == []
    assert r.evidence.ref_levels_v == {"threshold_v": 0.9}


@pytest.mark.parametrize("exp", [BITS + "11", BITS[:5], "1011_0010 1"])
def test_expected_length_mismatch(bit_set, exp):
    expected = ExpectedPattern(bits=exp)
    out = analyze_functional(bit_set(), S, expected)
    n = min(len(expected.bits), len(BITS))
    f = out.functional
    assert f.compared_cycles == n
    assert f.expected_bits == expected.bits
    r = _get(out, "match_rate", channel_id="OUT")
    assert r.warnings == [WarningCode.EXPECTED_LENGTH_MISMATCH]
    assert r.value == pytest.approx(f.matched_cycles / n * 100)
    notes = [x for x in out.notices if x.code == WarningCode.EXPECTED_LENGTH_MISMATCH]
    assert len(notes) == 1 and notes[0].metric_id == "match_rate" and notes[0].channel_id == "OUT"


def test_expected_without_clk_is_missing_role(bit_set):
    out = analyze_functional(bit_set(roles=[("OUT", "OUT")]), S, ExpectedPattern(bits=BITS))
    assert out.functional is None and out.results == []
    assert [n.code for n in out.notices] == [WarningCode.MISSING_ROLE]
    assert out.notices[0].metric_id == "match_rate"


def test_expected_channel_selects_out(bit_set, t, wave):
    inverted = wave("OUT2", t, np.full(t.shape, 1.7))
    m = bit_set(roles=[("CLK", "CLK"), ("OUT", "OUT"), ("OUT2", "OUT")], extra=[inverted])
    out = analyze_functional(m, S, ExpectedPattern(bits="1" * 8, channel_id="OUT2"))
    assert out.functional.channel_id == "OUT2"
    assert _get(out, "match_rate", channel_id="OUT2").value == 100.0
    # default target = first OUT channel
    assert analyze_functional(m, S, None).functional.channel_id == "OUT"


def test_iddq_interpolation_and_out_of_range(mset):
    sweep = DCSweep(name="DMM", x=[1.0, 1.2, 1.4], y=[1e-6, 2e-6, 4e-6])
    m = mset([], [], sweeps=[sweep])
    out = analyze_dc_power(m, AnalysisSettings(logic_vdd_v=1.3))
    r = _get(out, "iddq", channel_id="DMM")
    assert r.value == pytest.approx(3e-6) and r.evidence.params == {"vdd_v": 1.3}
    assert _get(analyze_dc_power(m, AnalysisSettings(logic_vdd_v=1.4)), "iddq").value == pytest.approx(4e-6)
    out = analyze_dc_power(m, AnalysisSettings(logic_vdd_v=1.8))
    r = _get(out, "iddq", channel_id="DMM")
    assert r.value is None and r.warnings == [WarningCode.OUT_OF_SWEEP_RANGE]
    assert [(n.code, n.metric_id, n.channel_id) for n in out.notices] == [
        (WarningCode.OUT_OF_SWEEP_RANGE, "iddq", "DMM")
    ]


def test_power_uses_vdd_channel_when_present(t, wave, mset):
    idd = wave("I", t, np.full(t.shape, 100e-6), quantity="A")
    vdd = wave("V", t, np.full(t.shape, 3.3))
    out = analyze_dc_power(mset([("V", "VDD"), ("I", "IDD")], [vdd, idd]), S)
    p = _get(out, "avg_power", channel_id="I")
    assert p.value == pytest.approx(330e-6)
    assert p.evidence.params == pytest.approx({"vdd_v": 3.3, "idd_avg_a": 100e-6})
    out = analyze_dc_power(mset([("I", "IDD")], [idd]), S)
    assert _get(out, "avg_power").evidence.params["vdd_v"] == 1.8


def test_voh_vol(bit_set, t, wave, mset):
    out = analyze_dc_power(bit_set(), S)
    assert _get(out, "voh", channel_id="OUT").value == pytest.approx(1.7)
    assert _get(out, "vol", channel_id="OUT").value == pytest.approx(0.1)
    # stuck output: the only level is reported by logic VDD / 2, the other is INSUFFICIENT_EDGES
    out = analyze_dc_power(mset([("OUT", "OUT")], [wave("OUT", t, np.full(t.shape, 1.65))]), S)
    assert _get(out, "voh").value == pytest.approx(1.65)
    vol = _get(out, "vol")
    assert vol.value is None and vol.warnings == [WarningCode.INSUFFICIENT_EDGES]
    assert [(n.code, n.metric_id) for n in out.notices] == [(WarningCode.INSUFFICIENT_EDGES, "vol")]


def test_analyze_all_is_the_sorted_union(bit_set):
    m = bit_set()
    exp = ExpectedPattern(bits=BITS + "0")
    parts = [analyze_timing(m, S), analyze_dc_power(m, S), analyze_functional(m, S, exp)]
    union = AnalyzerOutput(
        results=sorted([r for p in parts for r in p.results], key=result_sort_key),
        notices=sorted([n for p in parts for n in p.notices], key=notice_sort_key),
        functional=parts[2].functional,
    )
    assert analyze_all(m, S, exp).model_dump_json() == union.model_dump_json()
