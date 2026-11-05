"""Connection-stage tests (dashboard-agent): the app on the real core.adapters + core.pipeline with synth/data.

- evidence markers of every edge metric lie on the real waveform at their reference level (metrics.md §3)
- sim overlay: both sets' first CLK rising 50 % crossing lands at t = 0 in the [-0.5P, 4.5P] window
- AppTest: sample flow -> cards PASS 4 · MARGINAL 1 (DMM + expected bits), VOH margin 9.4 %
- demo scenario 4.2 steps 5-8 with inputs kept across re-runs (DMM added, measured file swapped, BW changed)
- run_analysis exceptions are shown as a Korean st.error, never replaced by the mock report
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path

import numpy as np
import pytest

from core.models import (
    AnalysisRequest,
    ChannelConversion,
    ExpectedPattern,
    Role,
    Spec,
    TimeAxisSpec,
    Verdict,
)

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "app_streamlit" / "app.py"
DATA = ROOT / "synth" / "data"
TABS = ["파형", "타이밍", "DC·전력", "기능", "시뮬 비교", "원본 데이터"]

pytestmark = pytest.mark.skipif(
    not all((DATA / n).exists() for n in ("synth_scope.csv", "synth_scope_err.csv", "synth_sim.csv",
                                          "synth_dmm.xlsx", "golden.json")),
    reason="synth/data not generated",
)
ad = pytest.importorskip("core.adapters")
pipeline = pytest.importorskip("core.pipeline")

from app_streamlit import figures as F  # noqa: E402
from app_streamlit import request_builder as rb  # noqa: E402
from app_streamlit import viewmodel as vm  # noqa: E402

GOLDEN_BITS = json.loads((DATA / "golden.json").read_text(encoding="utf-8"))["bits"] if (DATA / "golden.json").exists() else ""


# ======================================================================= request via the real adapters


def _load(name: str):
    data = (DATA / name).read_bytes()
    preview = ad.preview_file(data, name)
    return ad.read_table(data, name, preview.options), preview


def _waveforms(name: str, mapping: dict[str, str] | None = None):
    table, preview = _load(name)
    tcol = preview.time_candidates[0]
    convs = []
    for c in table.columns:
        if not c.numeric or c.name == tcol:
            continue
        cid = (mapping or {}).get(c.name, c.base_name if mapping is None else None)
        if cid:
            convs.append(ChannelConversion(column=c.name, channel_id=cid, quantity="A" if c.si_unit == "A" else "V",
                                           scale=c.scale))
    return ad.to_waveforms(table, TimeAxisSpec(column=tcol), convs).waveforms


def _request(scope: str = "synth_scope.csv", bandwidth_mhz: float = 500.0, bits: str | None = GOLDEN_BITS
             ) -> AnalysisRequest:
    cmap = rb.build_channel_map([("CH1", Role.CLK, None), ("CH2", Role.IN, None), ("CH3", Role.OUT, None),
                                 ("CH4", Role.IDD, None)])
    paths, errs = rb.paths_from_rows([{"이름": "Buffer", "입력 채널": "CH2", "출력 채널": "CH3", "극성": "비반전"}],
                                     ["CH1", "CH2", "CH3", "CH4"])
    assert not errs
    dmm, _ = _load("synth_dmm.xlsx")
    x = next(c for c in dmm.columns if c.numeric and c.si_unit == "V")
    y = next(c for c in dmm.columns if c.numeric and c.si_unit == "A")
    sweep = ad.to_dc_sweep(dmm, x.name, y.name, x_scale=x.scale, y_scale=y.scale, name="DMM").sweep
    sim_table, _ = _load("synth_sim.csv")
    sim = _waveforms("synth_sim.csv", {k: v for k, v in ad.suggest_sim_mapping(sim_table.columns, cmap).items() if v})
    settings = rb.build_settings(logic_vdd_v=1.8, bandwidth_mhz=bandwidth_mhz, marginal_threshold_pct=10,
                                 sim_tolerance_pct=20, delay_offset_ns=0, edge_hysteresis_pct=10,
                                 min_pulse_width_ns=0, smoothing_points=0)
    specs = [Spec(metric_id="tpd", max=8e-9), Spec(metric_id="rise_time", max=4e-9), Spec(metric_id="voh", min=1.6),
             Spec(metric_id="iddq", max=2.5e-6)]
    req, errs = rb.build_request(channel_map=cmap, paths=paths, waveforms=_waveforms(scope), dc_sweeps=[sweep],
                                 sim_waveforms=sim, specs=specs,
                                 expected=ExpectedPattern(bits=bits) if bits else None, settings=settings)
    assert req is not None, errs
    return req


@pytest.fixture(scope="module")
def real():
    req = _request()
    return req, pipeline.run_analysis(req)


# ======================================================================= pure: report + figures


def test_real_report_card_texts(real):
    _, rep = real
    cmap = rep.channel_map
    assert vm.verdict_counts_text(rep.cards.verdicts) == "✓ PASS 4 · ! MARGINAL 1 · ✕ FAIL 0"
    head, detail = vm.worst_margin_texts(rep.cards.worst_margin, cmap)
    assert "VOH" in head and "마진 9.4%" in detail
    head, _ = vm.sim_deviation_texts(rep.cards.sim_deviation, cmap)
    assert "+49.2%" in head and "+33.4%" in head
    head, _, verdict = vm.functional_texts(rep.cards.functional, rep.functional)
    assert verdict == Verdict.PASS and "100%" in head and "40/40" in head
    assert len(rep.summary_lines) == 3


EDGE_METRICS = ["rise_time", "fall_time", "tplh", "tphl", "tpd", "period", "duty_cycle", "setup_slack", "hold_slack"]


@pytest.mark.parametrize("metric_id", EDGE_METRICS)
def test_evidence_markers_sit_on_real_edges(real, metric_id):
    """Every marker (50 % / 10-90 % / input 50 % / CLK 50 %) lies on its channel's waveform at its level."""
    req, rep = real
    mset = req.measured
    results = [r for r in rep.results if r.metric_id == metric_id]
    assert results, metric_id
    for r in results:
        ov = F.evidence_overlay(r, mset)
        assert ov.points, f"{metric_id}: no markers (evidence keys {sorted(r.evidence.ref_levels_v)})"
        assert len(ov.points) >= len(r.evidence.edges)
        for p in ov.points:
            wf = mset.waveform(p.channel_id)
            assert wf is not None, p.channel_id
            v = float(np.interp(p.t, wf.time_s, wf.values))
            assert abs(v - p.v) < 0.02, f"{metric_id} {p.kind} on {p.channel_id} @ {p.t:.4e}s: wave {v:.4f} V vs {p.v:.4f} V"
        for ch, t0, t1, _ in ov.shades:
            assert mset.waveform(ch) is not None and t0 <= t1
        if r.evidence.worst_time_s is not None and metric_id not in ("period", "duty_cycle"):
            assert ov.worst, metric_id
    # setup/hold also mark the CLK edge; tp* also mark the input edge
    if metric_id in ("setup_slack", "hold_slack"):
        assert any(p.channel_id == "CH1" for p in F.evidence_overlay(results[0], mset).points)
    if metric_id in ("tplh", "tphl", "tpd"):
        assert any(p.channel_id == "CH2" for p in F.evidence_overlay(results[0], mset).points)


@pytest.mark.parametrize("metric_id", ["voh", "vol", "idd_avg"])
def test_level_lines_match_real_waveform(real, metric_id):
    req, rep = real
    r = next(r for r in rep.results if r.metric_id == metric_id)
    wf = req.measured.waveform(r.channel_id)
    ov = F.evidence_overlay(r, req.measured)
    assert any(h[0] == r.channel_id and h[1] == pytest.approx(r.value) for h in ov.hlines)
    if metric_id == "idd_avg":
        assert r.value == pytest.approx(float(np.mean(wf.values)), rel=0.05)
    else:  # the plateau really sits at that level: many samples within 50 mV
        assert np.mean(np.abs(wf.values - r.value) < 0.05) > 0.2


def test_sim_overlay_aligns_first_clk_edge_and_shows_real_edges(real):
    req, rep = real
    assert rep.clk_t0_s == pytest.approx(-1.975e-6, rel=1e-3)
    assert rep.sim_clk_t0_s == pytest.approx(25.03e-9, rel=1e-3)
    period = next(r.value for r in rep.results if r.metric_id == "period")
    window = vm.sim_overlay_window(rep)
    assert window is not None and window[1] - window[0] == pytest.approx(5 * period)
    fig = F.sim_overlay_figure(req.measured, req.sim, clk_t0_s=rep.clk_t0_s, sim_clk_t0_s=rep.sim_clk_t0_s,
                               window=window)
    assert tuple(fig.layout.xaxis.range) == pytest.approx(window)
    by = {(tr.name, tr.yaxis or "y"): tr for tr in fig.data}

    def crossings(tr, level, lo=-np.inf, hi=np.inf):
        x, y = np.asarray(tr.x, float), np.asarray(tr.y, float)
        idx = np.flatnonzero((y[:-1] < level) & (y[1:] >= level))
        t = x[idx] + (level - y[idx]) * (x[idx + 1] - x[idx]) / (y[idx + 1] - y[idx])
        return t[(t >= lo) & (t <= hi)]

    # each set's first CLK rising 50 % crossing sits at t = 0 after alignment (D6)
    assert abs(crossings(by[("측정", "y")], 0.9)[0]) < 0.2e-9
    assert abs(crossings(by[("시뮬", "y")], 0.9)[0]) < 0.2e-9
    # IN (row 2) and OUT (row 3) really switch inside the default window, in both sets
    for axis in ("y2", "y3"):
        for name in ("측정", "시뮬"):
            assert len(crossings(by[(name, axis)], 0.9, *window)) >= 1, (name, axis)
    d = crossings(by[("측정", "y3")], 0.9, *window)[0] - crossings(by[("시뮬", "y3")], 0.9, *window)[0]
    assert 0 < d < 3e-9  # measured OUT lags sim by about tpLH(meas) - tpLH(sim) ≈ 1.5 ns


def test_large_waveforms_use_webgl(real):
    req, rep = real
    assert max(w.n_samples for w in req.measured.waveforms) > F.GL_MIN_POINTS
    fig = F.waveform_figure(req.measured, vm.default_highlight(rep))
    assert {tr.type for tr in fig.data} == {"scattergl"}  # markers stay above GL lines
    thumbs = F.thumbnails_figure(req.measured.waveforms)
    assert {tr.type for tr in thumbs.data} == {"scattergl"}


def test_error_file_and_bandwidth_lines():
    rep = pipeline.run_analysis(_request(scope="synth_scope_err.csv", bandwidth_mhz=100.0))
    assert "37번째 사이클에서 첫 불일치 (기대 1, 측정 0)" in rep.summary_lines
    bw = [s for s in rep.summary_lines if "대역폭 한계" in s]
    assert len(bw) == 2 and any("rise" in s for s in bw) and any("fall" in s for s in bw)


# ======================================================================= AppTest: real flow


def _plain(md: str) -> str:
    return re.sub(r":[a-z]+(?:-[a-z]+)?\[([^\]]*)\]", r"\1", md)


def _texts(at) -> str:
    out: list[str] = []
    for kind in ("markdown", "caption", "info", "error", "warning", "success"):
        out += [_plain(str(e.value)) for e in getattr(at, kind)]
    return "\n".join(out)


def _app():
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(APP), default_timeout=180)
    at.run()
    assert not at.exception
    return at


def _select(at, names: list[str]) -> None:
    at.multiselect(key="in_samples").set_value(names).run()
    assert not at.exception


def _run(at) -> float:
    t = time.perf_counter()
    at.button(key="btn_run").click().run()
    dt = time.perf_counter() - t
    assert not at.exception
    assert at.session_state["view"] == "대시보드", [e.value for e in at.error]
    return dt


def _back(at) -> None:
    at.button(key="dash_edit_mapping").click().run()
    assert at.session_state["view"] == "입력·분석"


def _inputs(at) -> dict:
    ss = at.session_state
    return {
        "roles": [str(ss[f"role::CH{i}"]) for i in range(1, 5)],
        "paths": ss["paths_base"],
        "specs": [r["지표"].split(" · ")[0] for r in ss["specs_base"]],
        "vdd": ss["in_logic_vdd"],
        "bits": ss["in_expected_bits"],
    }


def _results(at, metric_id: str):
    return [r for r in at.session_state["report"].results if r.metric_id == metric_id]


def test_app_real_flow_cards_and_voh_margin():
    at = _app()
    _select(at, ["synth_scope.csv", "synth_sim.csv", "synth_dmm.xlsx"])
    at.button(key="btn_demo_defaults").click().run()
    at.button(key="btn_sample_bits").click().run()
    assert at.session_state["in_expected_bits"] == GOLDEN_BITS
    assert [e.value for e in at.error] == []
    dt = _run(at)
    assert dt < 3.0, f"click -> dashboard {dt:.2f}s"
    assert at.session_state["report_is_mock"] is False
    text = _texts(at)
    assert "✓ PASS 4 · ! MARGINAL 1 · ✕ FAIL 0" in text
    assert "마진 9.4%" in text
    assert "+49.2%" in text and "+33.4%" in text
    assert "100% (40/40 사이클)" in text
    assert "목업" not in text
    assert "분석 0.0" in text or "분석 0.1" in text  # header timing caption
    for tab in TABS:
        at.session_state["dash_tab"] = tab
        at.run()
        assert not at.exception, tab
        assert not any("파형 데이터 없음" in i.value for i in at.info), tab
        assert not any("DC 스윕 데이터 없음" in i.value for i in at.info), tab


def test_sample_bits_button_only_in_sample_mode_and_never_automatic():
    at = _app()
    assert "btn_sample_bits" not in [b.key for b in at.button]
    _select(at, ["synth_scope_err.csv"])
    assert "btn_sample_bits" in [b.key for b in at.button]
    assert at.session_state["in_expected_bits"] == ""  # not applied until clicked
    at.button(key="btn_sample_bits").click().run()
    assert at.session_state["in_expected_bits"] == GOLDEN_BITS  # normal bits even with the error file


def test_dc_sweep_default_name_is_dmm():
    at = _app()
    _select(at, ["synth_dmm.xlsx"])
    names = [t.value for t in at.text_input if t.key and t.key.endswith("::dcname")]
    assert names == ["DMM"]


def test_demo_scenario_steps_5_to_8_keep_inputs():
    at = _app()
    # 1-4: scope, demo defaults (roles, path, VDD, BW, specs), sim
    _select(at, ["synth_scope.csv"])
    at.button(key="btn_demo_defaults").click().run()
    _select(at, ["synth_scope.csv", "synth_sim.csv"])
    # 5: run without DMM -> IDDQ not judged yet
    _run(at)
    assert _results(at, "voh")[0].margin_pct == pytest.approx(9.4, abs=0.05)
    assert all(r.value is None for r in _results(at, "iddq"))
    kept = _inputs(at)
    assert kept["roles"] == ["CLK", "IN", "OUT", "IDD"] and kept["specs"] == ["tpd", "rise_time", "voh", "iddq"]

    # 6: add the DMM xlsx and re-run -> I-V + IDDQ PASS (margin 40 %)
    _back(at)
    _select(at, ["synth_scope.csv", "synth_sim.csv", "synth_dmm.xlsx"])
    _run(at)
    iddq = _results(at, "iddq")[0]
    assert iddq.channel_id == "DMM" and iddq.verdict == Verdict.PASS and iddq.margin_pct == pytest.approx(40, abs=1)
    assert _inputs(at) == kept

    # 7: expected bits -> 100 %; then swap the measured file for the error file (two clicks) -> cycle 37
    _back(at)
    at.button(key="btn_sample_bits").click().run()
    _run(at)
    assert at.session_state["report"].functional.match_rate_pct == pytest.approx(100)
    kept = _inputs(at)
    _back(at)
    _select(at, ["synth_sim.csv", "synth_dmm.xlsx"])  # measured file removed: its role widgets disappear
    _select(at, ["synth_sim.csv", "synth_dmm.xlsx", "synth_scope_err.csv"])
    assert _inputs(at) == kept  # roles restored from memory, paths/specs/bits untouched
    assert [e.value for e in at.error] == []
    _run(at)
    assert "37번째 사이클에서 첫 불일치 (기대 1, 측정 0)" in at.session_state["report"].summary_lines
    assert "37번째 사이클에서 첫 불일치" in _texts(at)

    # 8: only the bandwidth changes -> rise/fall bandwidth-limit lines
    _back(at)
    at.number_input(key="in_bandwidth_mhz").set_value(100.0).run()
    _run(at)
    lines = [s for s in at.session_state["report"].summary_lines if "대역폭 한계" in s]
    assert len(lines) == 2
    text = _texts(at)
    assert "CH3 rise" in text and "CH3 fall" in text and "대역폭 한계" in text
    assert _inputs(at) == kept
    assert at.session_state["in_samples"] == ["synth_sim.csv", "synth_dmm.xlsx", "synth_scope_err.csv"]


def test_run_error_is_shown_not_replaced_by_mock(monkeypatch):
    def boom(_request):
        raise ValueError("테스트용 실패")

    monkeypatch.setattr(pipeline, "run_analysis", boom)
    at = _app()
    _select(at, ["synth_scope.csv"])
    at.button(key="btn_demo_defaults").click().run()
    at.button(key="btn_run").click().run()
    assert not at.exception
    assert any("분석 중 오류가 발생했습니다: 테스트용 실패" in e.value for e in at.error)
    assert at.session_state["view"] == "입력·분석"
    assert at.session_state["report"] is None
