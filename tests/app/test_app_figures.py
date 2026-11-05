"""Pure UI helpers: Plotly figure builders (waveform + evidence markers, margin bars, functional lanes,
sim overlay ...), view-model texts and the request builder. No streamlit runtime needed."""

from __future__ import annotations

import re
from pathlib import Path as FsPath

import numpy as np
import pytest

from app_streamlit import figures as F
from app_streamlit import request_builder as rb
from app_streamlit import viewmodel as vm
from app_streamlit.theme import VERDICT_COLORS
from core.models import (
    AnalysisReport,
    ChannelInfo,
    ChannelMap,
    DCSweep,
    MeasurementSet,
    Role,
    SessionInfo,
    Verdict,
    Waveform,
)

ROOT = FsPath(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def report() -> AnalysisReport:
    return vm.load_mock_report()


def _square(t: np.ndarray, t0: float, period: float = 100e-9) -> np.ndarray:
    return np.where(((t - t0) % period) < period / 2, 1.8, 0.0)


@pytest.fixture(scope="module")
def mset(report: AnalysisReport) -> MeasurementSet:
    """Synthetic 4-channel set on the mock's channel map (waveform shapes are irrelevant for markers)."""
    t = np.arange(-2e-6, 2e-6, 1e-9)
    clk = _square(t, -2e-6 + 25e-9)
    return MeasurementSet(
        session=report.session, channel_map=report.channel_map, paths=report.paths,
        waveforms=[
            Waveform(channel_id="CH1", quantity="V", time_s=t, values=clk),
            Waveform(channel_id="CH2", quantity="V", time_s=t, values=np.roll(clk, 50)),
            Waveform(channel_id="CH3", quantity="V", time_s=t, values=np.roll(clk, 56) * 0.94 + 0.05),
            Waveform(channel_id="CH4", quantity="A", time_s=t, values=np.full_like(t, 120e-6)),
        ],
        dc_sweeps=[DCSweep(name="DMM", x=np.linspace(1.0, 2.0, 11),
                           y=1.5e-6 * np.exp((np.linspace(1.0, 2.0, 11) - 1.8) / 0.25))],
    )


def _result(report: AnalysisReport, metric_id: str):
    return next(r for r in report.results if r.metric_id == metric_id)


def _trace(fig, name: str):
    return next(t for t in fig.data if t.name == name)


def _rects(fig) -> list:
    return [s for s in fig.layout.shapes if s.type == "rect"]


# ------------------------------------------------------------------ waveform + evidence


def test_waveform_rows_follow_channel_map_and_skip_unused(report, mset):
    cmap = ChannelMap(channels=[*report.channel_map.channels, ChannelInfo(channel_id="CH5", role=Role.UNUSED)])
    t = mset.waveforms[0].time_s
    ms = mset.model_copy(update={"channel_map": cmap,
                                 "waveforms": [*mset.waveforms, Waveform(channel_id="CH5", quantity="V",
                                                                         time_s=t, values=np.zeros_like(t))]})
    fig = F.waveform_figure(ms)
    assert [tr.name for tr in fig.data] == ["CH1 · CLK", "CH2 · IN", "CH3 · OUT", "CH4 · IDD"]
    assert F.waveform_figure(mset, channels=["CH4"]).data[0].name == "CH4 · IDD"


def test_rise_time_markers_come_from_evidence(report, mset):
    r = _result(report, "rise_time")
    ev = r.evidence
    fig = F.waveform_figure(mset, r)
    mid = _trace(fig, "50 % 교차")
    assert list(mid.x) == [e.t_s for e in ev.edges]
    v50 = (ev.ref_levels_v["low"] + ev.ref_levels_v["high"]) / 2
    assert all(y == pytest.approx(v50) for y in mid.y)
    assert mid.yaxis == "y3"  # CH3 row
    pts = _trace(fig, "10/90 % 점")
    assert sorted(pts.x) == sorted([e.t_start_s for e in ev.edges] + [e.t_end_s for e in ev.edges])
    star = _trace(fig, "최악 엣지")
    assert list(star.x) == [ev.worst_time_s]
    assert star.marker.color == VERDICT_COLORS[Verdict.PASS]
    assert len(_rects(fig)) == len(ev.edges)  # one shade per edge (10 % -> 90 %)
    lo, hi = fig.layout.xaxis.range
    assert lo < ev.worst_time_s < hi and hi - lo < 1e-6  # zoomed around the worst edge


def test_tpd_markers_span_input_and_output_rows(report, mset):
    r = _result(report, "tpd")
    fig = F.waveform_figure(mset, r, zoom_to_highlight=False)
    assert _trace(fig, "입력 50 %").yaxis == "y2"  # CH2 = Buffer input
    assert list(_trace(fig, "입력 50 %").x) == [e.t_start_s for e in r.evidence.edges]
    assert _trace(fig, "출력 50 %").yaxis == "y3"
    assert len(_rects(fig)) == 2 * len(r.evidence.edges)  # tpd interval shaded on both rows
    assert fig.layout.xaxis.range is None


def test_setup_slack_marks_the_clk_row(report, mset):
    r = _result(report, "setup_slack")
    fig = F.waveform_figure(mset, r)
    clk = _trace(fig, "CLK 상승 50 %")
    assert clk.yaxis == "y" and list(clk.x) == [e.t_end_s for e in r.evidence.edges]


def test_level_metrics_draw_lines(report, mset):
    fig = F.waveform_figure(mset, _result(report, "voh"))
    texts = [a.text for a in fig.layout.annotations]
    assert any(t.startswith("VOH 1.75 V") for t in texts)
    assert any(t.startswith("스펙 하한 1.60 V") for t in texts)


def test_window_override_and_empty(mset):
    fig = F.waveform_figure(mset, None, window=(-1e-7, 1e-7))
    assert tuple(fig.layout.xaxis.range) == (-1e-7, 1e-7)
    empty = F.waveform_figure(MeasurementSet(channel_map=ChannelMap()))
    assert empty.layout.annotations[0].text == "표시할 파형이 없습니다"


# ------------------------------------------------------------------ other charts


def test_margin_bars_carry_symbol_and_verdict_color(report):
    fig = F.margin_bar_figure(report)
    bar = fig.data[0]
    assert len(bar.x) == 5  # tpd, rise, voh, iddq + match_rate
    assert all(t[0] in "✓!✕–" for t in bar.text)
    allowed = {VERDICT_COLORS[v] for v in (Verdict.PASS, Verdict.MARGINAL, Verdict.FAIL)}
    assert set(bar.marker.color) <= allowed
    assert "! MARGINAL 9.4%" in bar.text
    assert len(F.margin_bar_figure(report, include_no_spec=True).data[0].x) == len(report.results)


def test_functional_figure_marks_mismatches(report):
    d = report.functional
    exp = list(d.expected_bits)
    exp[36] = "1" if exp[36] == "0" else "0"
    bad = d.model_copy(update={"expected_bits": "".join(exp), "mismatch_cycles": [37], "first_mismatch": 37,
                               "matched_cycles": 39, "match_rate_pct": 97.5})
    fig = F.functional_figure(bad)
    assert list(_trace(fig, "불일치").x) == [37]
    assert len(_rects(fig)) == 3  # cycle 37 shaded on all three lanes
    assert ":red[**" in vm.bits_markdown(bad, "measured")
    head, tail, verdict = vm.functional_texts(None, bad)
    assert verdict is None and "기대 비트열 없음" in head


def test_sim_overlay_aligns_on_first_clk_edge(report, mset):
    sim = MeasurementSet(session=SessionInfo(source="sim"), channel_map=report.channel_map, paths=report.paths,
                         waveforms=mset.waveforms[:3])
    fig = F.sim_overlay_figure(mset, sim, clk_t0_s=report.clk_t0_s, sim_clk_t0_s=report.sim_clk_t0_s)
    meas = [t for t in fig.data if t.name == "측정"]
    sims = [t for t in fig.data if t.name == "시뮬"]
    assert len(meas) == len(sims) == 3  # CH4 has no sim waveform
    assert meas[0].x[0] == pytest.approx(mset.waveforms[0].time_s[0] - report.clk_t0_s)
    assert sims[0].x[0] == pytest.approx(mset.waveforms[0].time_s[0] - report.sim_clk_t0_s)
    assert sims[0].line.dash == "dash"


def test_deviation_bars_flag_over_tolerance(report):
    bar = F.deviation_figure(report).data[0]
    assert sum(t.startswith("!") for t in bar.text) == report.cards.sim_deviation.warning_count == 4
    assert any("계산 안 함" in t for t in bar.text)  # vol: sim value 0


def test_iv_and_distribution(report, mset):
    iddq = [_result(report, "iddq")]
    fig = F.iv_figure(mset.dc_sweeps, logic_vdd_v=1.8, iddq_results=iddq, log_y=True)
    assert fig.layout.yaxis.type == "log"
    assert min(fig.data[0].y) > 0
    assert _trace(fig, "IDDQ (DMM)").marker.color == VERDICT_COLORS[Verdict.PASS]
    dist = F.edge_distribution_figure(report.results, report.channel_map)
    boxes = [t for t in dist.data if t.type == "box"]
    assert len(boxes) == sum(1 for r in report.results if r.evidence.edges)  # one box per result with edges
    assert any(t.name == "시뮬 평균" for t in dist.data)


# ------------------------------------------------------------------ view model


def test_card_texts(report):
    cm = report.channel_map
    assert vm.verdict_counts_text(report.cards.verdicts) == "✓ PASS 4 · ! MARGINAL 1 · ✕ FAIL 0"
    assert vm.overall_verdict(report.cards.verdicts) == Verdict.MARGINAL
    assert vm.worst_margin_texts(report.cards.worst_margin, cm) == ("! VOH 1.75 V", "CH3 · 스펙 ≥ 1.60 V · 마진 9.4%")
    head, detail = vm.sim_deviation_texts(report.cards.sim_deviation, cm)
    assert head == "rise(CH3) +50.0% · tpLH(Buffer) +33.3%" and "경고 4건" in detail
    assert vm.functional_texts(report.cards.functional, report.functional)[0] == "✓ 100% (40/40 사이클)"
    assert vm.default_highlight(report).metric_id == "rise_time"
    assert len(vm.results_table(report.results, cm)) == len(report.results)


# ------------------------------------------------------------------ request builder


def test_specs_from_display_units_to_si():
    opt = rb.metric_option_of()
    rows = [
        {"지표": opt["tpd"], "경로": rb.ALL, "채널": rb.ALL, "최소": None, "최대": 8.0},
        {"지표": opt["iddq"], "경로": None, "채널": "DMM", "최소": float("nan"), "최대": 2.5},
        {"지표": opt["voh"], "경로": "", "채널": "", "최소": 1.6, "최대": None},
        {"지표": None, "경로": None, "채널": None, "최소": None, "최대": None},  # empty editor row
    ]
    specs, errors = rb.specs_from_rows(rows)
    assert errors == []
    assert [(s.metric_id, s.path, s.channel_id) for s in specs] == [("tpd", None, None), ("iddq", None, "DMM"),
                                                                     ("voh", None, None)]
    assert specs[0].max == pytest.approx(8e-9) and specs[1].max == pytest.approx(2.5e-6) and specs[2].min == 1.6
    _, errors = rb.specs_from_rows([{"지표": opt["tpd"], "최소": None, "최대": None}, {"지표": "x", "최대": 1}])
    assert len(errors) == 2
    assert "match_rate" not in rb.metric_options().values()


def test_paths_expected_and_request():
    paths, errors = rb.paths_from_rows(
        [{"이름": "Buffer", "입력 채널": "CH2", "출력 채널": "CH3", "극성": "비반전"},
         {"이름": "Inv", "입력 채널": "CH2", "출력 채널": "CH9", "극성": "반전"},
         {"이름": None, "입력 채널": None, "출력 채널": None, "극성": None}], ["CH1", "CH2", "CH3"])
    assert [p.name for p in paths] == ["Buffer"] and len(errors) == 1
    pat, err = rb.expected_from_text("0000 0010_1,1", None)
    assert pat.bits == "0000001011" and err is None
    assert rb.expected_from_text("01x", None)[1] is not None
    assert rb.expected_from_text("  ", None) == (None, None)

    t = np.arange(0, 1e-6, 1e-9)
    cmap = rb.build_channel_map([("CH1", Role.CLK, ""), ("CH3", "OUT", "WL0")])
    assert cmap.display_name("CH3") == "WL0"
    wf = [Waveform(channel_id="CH1", quantity="V", time_s=t, values=_square(t, 0.0)),
          Waveform(channel_id="CH3", quantity="V", time_s=t, values=_square(t, 5e-9))]
    settings = rb.build_settings(logic_vdd_v=1.8, bandwidth_mhz=500.0, marginal_threshold_pct=10,
                                 sim_tolerance_pct=20, delay_offset_ns=1.0, edge_hysteresis_pct=10,
                                 min_pulse_width_ns=0, smoothing_points=0)
    assert settings.bandwidth_hz == 5e8 and settings.delay_offset_s == pytest.approx(1e-9)
    req, errors = rb.build_request(channel_map=cmap, paths=[], waveforms=wf, dc_sweeps=[], sim_waveforms=wf[:1],
                                   specs=[], expected=pat, settings=settings, chip_id="칩 #1",
                                   measured_files=["a.csv"], sim_files=["s.csv"])
    assert errors == [] and req is not None
    assert req.measured.session.source == "measured" and req.sim.session.source == "sim"
    assert req.sim.channel_map == req.measured.channel_map and req.measured.session.files == ["a.csv"]
    none_req, errors = rb.build_request(channel_map=ChannelMap(), paths=[], waveforms=[], dc_sweeps=[],
                                        sim_waveforms=[], specs=[], expected=None, settings=settings)
    assert none_req is None and errors


def test_pure_helpers_do_not_import_streamlit():
    for name in ("figures.py", "viewmodel.py", "request_builder.py", "theme.py"):
        src = (ROOT / "app_streamlit" / name).read_text(encoding="utf-8")
        assert not re.search(r"^\s*(import|from)\s+streamlit\b", src, re.MULTILINE), name
