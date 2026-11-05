"""synth.generate: D11 numbers, file formats, error-file diff, determinism."""

from __future__ import annotations

import json
import math
from pathlib import Path as FsPath

import numpy as np
import pytest
from openpyxl import load_workbook

from synth import generate as g

BITS = "0000001000001100001010001111001000101100"


def _scope_matrix(raw: bytes) -> tuple[list[str], np.ndarray]:
    lines = raw.decode("utf-8").splitlines()
    data = np.array([[float(x) for x in ln.split(",")] for ln in lines[5:]])
    return lines[:5], data


def test_prbs7_bits_and_transitions():
    bits = g.prbs7()
    assert bits == BITS and len(bits) == 40
    rises, falls = g.count_transitions(bits)
    assert rises >= 8 and falls >= 8


def test_output_bits_error_flips_cycle_37_only():
    err = g.output_bits(BITS, error=True)
    diff = [i + 1 for i, (a, b) in enumerate(zip(BITS, err, strict=True)) if a != b]
    assert diff == [37]
    assert g.output_bits(BITS) == BITS


def test_scope_header_and_axis(synth_bytes):
    head, m = _scope_matrix(synth_bytes["synth_scope.csv"])
    assert head == [
        "Model,ChipLens-SynthScope",
        "Sample Interval,2.000000E-10",
        "Record Length,20000",
        "Trigger Position,-2.000000E-06",
        "Time(s),CH1(V),CH2(V),CH3(V),CH4(A)",
    ]
    assert m.shape == (20000, 5)
    assert m[0, 0] == -2.0e-6
    assert synth_bytes["synth_scope.csv"].decode().splitlines()[5].startswith("-2.0000000000E-06,")
    np.testing.assert_allclose(np.diff(m[:, 0]), 0.2e-9, rtol=1e-6)
    assert m[-1, 0] == pytest.approx(-2.0e-6 + 19999 * 0.2e-9, rel=1e-12)


def test_error_file_differs_only_in_out_and_idd(synth_bytes):
    _, ok = _scope_matrix(synth_bytes["synth_scope.csv"])
    _, err = _scope_matrix(synth_bytes["synth_scope_err.csv"])
    assert np.array_equal(ok[:, :3], err[:, :3])  # time, CLK, IN identical
    tau = ok[:, 0] + 2.0e-6
    for col in (3, 4):  # OUT, IDD
        changed = np.nonzero(ok[:, col] != err[:, col])[0]
        assert changed.size > 0
        # only around cycle 36-38 (tau 3500 ... 3800 ns)
        assert tau[changed].min() > 3500e-9 and tau[changed].max() < 3800e-9


def test_out_sampled_at_clk_rise(synth_bytes, golden):
    t_rise = np.array(golden["edges"]["scope"]["clk_rise_s"])
    assert t_rise.size == 40
    for name, expected in (("synth_scope.csv", BITS), ("synth_scope_err.csv", golden["bits_err"])):
        _, m = _scope_matrix(synth_bytes[name])
        v = np.interp(t_rise, m[:, 0], m[:, 3])
        got = "".join("1" if x >= 0.9 else "0" for x in v)
        assert got == expected
    assert golden["bits_err"][36] != BITS[36]


def test_crossing_times_hit_50_percent(golden):
    clean = g.scope_clean(error=False)
    e = golden["edges"]["scope"]
    checks = [("clk_rise_s", "CH1", 0.9), ("clk_fall_s", "CH1", 0.9), ("in_rise_s", "CH2", 0.9),
              ("in_fall_s", "CH2", 0.9), ("out_rise_s", "CH3", 0.9), ("out_fall_s", "CH3", 0.9)]
    for key, ch, mid in checks:
        ts = np.array(e[key])
        assert ts.size >= 8
        np.testing.assert_allclose(np.interp(ts, clean["t"], clean[ch]), mid, atol=1e-9)
    # tpLH / tpHL: OUT crossing - IN crossing
    np.testing.assert_allclose(np.array(e["out_rise_s"]) - np.array(e["in_rise_s"]), 6.0e-9, atol=1e-15)
    np.testing.assert_allclose(np.array(e["out_fall_s"]) - np.array(e["in_fall_s"]), 5.5e-9, atol=1e-15)
    assert e["clk_rise_s"][0] == pytest.approx(-2.0e-6 + 25.03e-9, abs=1e-18)
    assert e["in_rise_s"][0] == pytest.approx(-2.0e-6 + 75.03e-9 + 5 * 100e-9, abs=1e-18)


def test_levels_ramps_and_ringing():
    clean = g.scope_clean(error=False)
    out = clean["CH3"]
    # 5 % overshoot of the 1.7 V swing (sample grid can miss the exact peak by a little)
    assert out.max() == pytest.approx(1.75 + 0.085, abs=2e-3)
    assert out.min() == pytest.approx(0.05 - 0.085, abs=2e-3)
    assert clean["CH1"].max() == pytest.approx(1.8 + 0.09, abs=2e-3)
    assert g.ringing_unit_peak() * g.ringing_amplitude(1.0) == pytest.approx(0.05)
    # 10-90 % of the full ramp = 0.8 x ramp length
    tau = np.linspace(0, 20e-9, 200001)
    tr = g.Transition(1000, 0.0, 1.0, 3.0e-9 * g.RAMP_FULL_FACTOR)
    y = g.ramp_signal(tau, 0.0, [tr])
    ramp = (y > 0) & (y < 1)
    t10 = np.interp(0.1, y[ramp], tau[ramp])
    t90 = np.interp(0.9, y[ramp], tau[ramp])
    assert t90 - t10 == pytest.approx(3.0e-9, rel=1e-4)


def test_idd_mean_before_noise():
    for err in (False, True):
        clean = g.scope_clean(error=err)
        assert float(np.mean(clean["CH4"])) == pytest.approx(120e-6, rel=1e-12)
        spike = float(np.max(clean["CH4"]) - np.min(clean["CH4"]))
        assert 0.98 * 1.5e-3 < spike <= 1.5e-3 + 1e-12  # 0.2 ns grid can miss the exact peak
    # exact peak on the crossing itself
    tr = g.out_transitions(BITS, g.SCOPE_OUT)
    assert g.idd_spikes(np.array([tr[0].t50_s]), tr)[0] == pytest.approx(1.5e-3, rel=1e-9)


def test_noise_same_for_both_files():
    a, b = g.scope_noise(), g.scope_noise()
    for ch in ("CH1", "CH2", "CH3", "CH4"):
        assert np.array_equal(a[ch], b[ch])
    assert float(np.std(a["CH1"])) == pytest.approx(10e-3, rel=0.05)
    assert float(np.std(a["CH4"])) == pytest.approx(1e-6, rel=0.05)


def test_sim_file_format(synth_bytes, golden):
    lines = synth_bytes["synth_sim.csv"].decode("utf-8").splitlines()
    assert lines[0] == "time v(clk) time v(in) time v(out)"
    m = np.array([[float(x) for x in ln.split()] for ln in lines[1:]])
    assert m.shape == (40001, 6)
    assert np.array_equal(m[:, 0], m[:, 2]) and np.array_equal(m[:, 0], m[:, 4])
    assert m[0, 0] == 0.0 and m[-1, 0] == pytest.approx(4.0e-6)
    np.testing.assert_allclose(np.diff(m[:, 0]), 0.1e-9, rtol=1e-6)
    assert "e-" in lines[2]  # scientific notation
    out = m[:, 5]
    assert out.min() == 0.0 and out.max() == pytest.approx(1.8)
    e = golden["edges"]["sim"]
    np.testing.assert_allclose(np.array(e["out_rise_s"]) - np.array(e["in_rise_s"]), 4.5e-9, atol=1e-15)
    np.testing.assert_allclose(np.array(e["out_fall_s"]) - np.array(e["in_fall_s"]), 4.2e-9, atol=1e-15)
    np.testing.assert_allclose(np.interp(e["out_rise_s"], m[:, 0], out), 0.9, atol=1e-9)


def test_dmm_workbook(synth_bytes, synth_dir):
    wb = load_workbook(synth_dir / "synth_dmm.xlsx")
    assert wb.sheetnames == ["DC측정", "조건"]
    ws = wb["DC측정"]
    assert [str(r) for r in ws.merged_cells.ranges] == ["A1:C1"]
    assert ws["A1"].value == "멀티미터 DC 측정 — 칩 #1, 25 °C"
    assert all(c.value is None for c in ws[2])
    assert [c.value for c in ws[3]] == ["전압(V)", "전류(µA)", "비고"]
    assert "µ" in ws["B3"].value
    rows = [[c.value for c in r] for r in ws.iter_rows(min_row=4, max_row=14)]
    assert [round(r[0], 1) for r in rows] == [round(1.0 + 0.1 * i, 1) for i in range(11)]
    for v, cur, _ in rows:
        assert cur == round(1.5 * math.exp((v - 1.8) / 0.25), 4)
    row18 = next(r for r in rows if r[0] == 1.8)
    assert row18[1] == 1.5 and row18[2] == "IDDQ 기준"
    assert ws.max_row == 14
    cond = [tuple(c.value for c in r) for r in wb["조건"].iter_rows()]
    assert cond[0] == ("항목", "값") and {r[0] for r in cond[1:]} >= {"칩 ID", "온도(°C)", "장비"}


def test_golden_structure(golden):
    assert golden["seed"] == 20261105
    assert golden["bits"] == BITS
    assert set(golden) >= {"params", "bits", "bits_err", "edges", "answers", "transitions", "setup"}
    a = golden["answers"]
    assert a["scope"]["tplh"]["value"] == 6.0e-9 and a["scope"]["setup_slack"]["value"] == 44.0e-9
    assert a["scope"]["hold_slack"]["value"] == 55.5e-9
    assert a["scope_err"]["match_rate"]["value"] == 97.5
    assert a["scope_err"]["match_rate"]["first_mismatch"] == 37
    assert a["dmm"]["iddq"]["value"] == 1.5e-6
    assert golden["transitions"]["in_rise"] >= 8 and golden["transitions"]["in_fall"] >= 8
    for key in ("scope", "scope_err", "sim"):
        e = golden["edges"][key]
        assert len(e["clk_rise_s"]) == 40 and len(e["clk_fall_s"]) == 40
        assert len(e["out_rise_s"]) + len(e["out_fall_s"]) == 16


def test_regeneration_is_byte_identical(tmp_path: FsPath, synth_dir: FsPath):
    g.write_all(tmp_path)
    for name in ("synth_scope.csv", "synth_scope_err.csv", "synth_sim.csv", "golden.json"):
        assert (tmp_path / name).read_bytes() == (synth_dir / name).read_bytes(), name
    assert json.loads((tmp_path / "golden.json").read_text(encoding="utf-8")) == g.golden_dict()
    a = load_workbook(tmp_path / "synth_dmm.xlsx")
    b = load_workbook(synth_dir / "synth_dmm.xlsx")
    for sheet in a.sheetnames:
        assert list(a[sheet].iter_rows(values_only=True)) == list(b[sheet].iter_rows(values_only=True))
