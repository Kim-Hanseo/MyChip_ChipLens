"""E2E demo (plan 4.2 steps 3-8): file bytes -> core.adapters public API -> core.pipeline.run_analysis.

Expected values come from synth/data/golden.json (answers.demo_judgment, sim_deviation_pct, bandwidth).
"""

from __future__ import annotations

import json
import time
from pathlib import Path as FsPath
from typing import Any

import pytest

from core.adapters import preview_file, read_table, suggest_sim_mapping, to_dc_sweep, to_waveforms
from core.models import (
    AnalysisReport,
    AnalysisRequest,
    AnalysisResult,
    AnalysisSettings,
    ChannelConversion,
    ChannelInfo,
    ChannelMap,
    DCSweep,
    ExpectedPattern,
    MeasurementSet,
    Path,
    SessionInfo,
    Source,
    Spec,
    TimeAxisSpec,
    Verdict,
    WarningCode,
    Waveform,
    format_metric_value,
    notice_sort_key,
    result_sort_key,
)
from core.pipeline import run_analysis

DATA = FsPath(__file__).resolve().parents[2] / "synth" / "data"
GOLDEN: dict[str, Any] = json.loads((DATA / "golden.json").read_text(encoding="utf-8"))
FILES = GOLDEN["files"]
SETUP = GOLDEN["setup"]
DEMO = GOLDEN["answers"]["demo_judgment"]

PERF_LIMIT_S = 3.0
COMMON_DELAY = "전 경로 공통 지연 증가 → 측정 경로(패드·PCB·프로브) 지연, VDD 강하, 공정 코너 가능성"
BW_TAIL = ": 측정값이 오실로스코프 대역폭 한계에 가까움 → 실제 값은 더 짧을 수 있음"
TIMING_SIM_WARNINGS = {"tplh", "tphl", "rise_time", "fall_time"}


# ---- adapter stage (public API only) --------------------------------------------------------


def _channel_map() -> ChannelMap:
    return ChannelMap(channels=[ChannelInfo(**c) for c in SETUP["channel_map"]])


def _paths() -> list[Path]:
    return [Path(**p) for p in SETUP["paths"]]


def load_scope(name: str) -> list[Waveform]:
    """Scope CSV bytes -> preview (auto) -> RawTable -> Waveforms keyed by header base name (CH1..CH4)."""
    data = (DATA / name).read_bytes()
    preview = preview_file(data, name)
    table = read_table(data, name, preview.options)
    time_col = preview.time_candidates[0]
    convs = [
        ChannelConversion(column=c.name, channel_id=c.base_name, quantity=c.si_unit, scale=c.scale)
        for c in table.columns
        if c.name != time_col and c.numeric and c.si_unit in ("V", "A")
    ]
    built = to_waveforms(table, TimeAxisSpec(column=time_col), convs)
    assert built.notices == []
    return built.waveforms


def load_sim(cmap: ChannelMap) -> list[Waveform]:
    """ngspice wrdata bytes -> RawTable -> suggest_sim_mapping -> Waveforms re-keyed to measured ids (D3)."""
    name = FILES["sim"]
    data = (DATA / name).read_bytes()
    preview = preview_file(data, name)
    table = read_table(data, name, preview.options)
    mapping = suggest_sim_mapping(table.columns, cmap)
    assert mapping == SETUP["sim_mapping"]
    convs = [
        ChannelConversion(column=col, channel_id=ch, quantity=table.column(col).si_unit or "V",
                          scale=table.column(col).scale)
        for col, ch in mapping.items()
        if ch is not None
    ]
    built = to_waveforms(table, TimeAxisSpec(column=preview.time_candidates[0]), convs)
    assert built.notices == []
    return built.waveforms


def load_dmm() -> DCSweep:
    """DMM xlsx bytes -> preview (sheet/header guessed) -> to_dc_sweep(V column, A column)."""
    name = FILES["dmm"]
    data = (DATA / name).read_bytes()
    preview = preview_file(data, name)
    table = read_table(data, name, preview.options)
    x = next(c for c in table.columns if c.si_unit == "V")
    y = next(c for c in table.columns if c.si_unit == "A")
    built = to_dc_sweep(table, x.name, y.name, x_scale=x.scale, y_scale=y.scale, name=SETUP["dmm"]["sweep_name"])
    assert built.sweep is not None
    return built.sweep


def demo_specs() -> list[Spec]:
    keep = ("metric_id", "min", "max")
    return [Spec(**{k: s[k] for k in keep if k in s}) for s in DEMO["specs"]]


def build_request(*, scope: str = FILES["scope"], bandwidth_hz: float | None = 500e6, sim: bool = True,
                  dmm: bool = True, expected: bool = True, specs: bool = True) -> AnalysisRequest:
    cmap, paths = _channel_map(), _paths()
    measured = MeasurementSet(
        session=SessionInfo(source=Source.MEASURED, chip_id="synth #1", files=[scope] + ([FILES["dmm"]] if dmm else [])),
        channel_map=cmap,
        paths=paths,
        waveforms=load_scope(scope),
        dc_sweeps=[load_dmm()] if dmm else [],
    )
    sim_set = MeasurementSet(
        session=SessionInfo(source=Source.SIM, files=[FILES["sim"]]),
        channel_map=cmap,
        paths=paths,
        waveforms=load_sim(cmap),
    ) if sim else None
    return AnalysisRequest(
        measured=measured,
        sim=sim_set,
        specs=demo_specs() if specs else [],
        expected=ExpectedPattern(bits=GOLDEN["bits"]) if expected else None,
        settings=AnalysisSettings(logic_vdd_v=SETUP["logic_vdd_v"], bandwidth_hz=bandwidth_hz,
                                  marginal_threshold_pct=DEMO["settings"]["marginal_threshold_pct"],
                                  sim_tolerance_pct=DEMO["settings"]["sim_tolerance_pct"]),
    )


def pick(report: AnalysisReport, metric_id: str) -> AnalysisResult:
    found = [r for r in report.results if r.metric_id == metric_id]
    assert len(found) == 1, metric_id
    return found[0]


@pytest.fixture(scope="module")
def demo_request() -> AnalysisRequest:
    return build_request(bandwidth_hz=500e6)


@pytest.fixture(scope="module")
def demo(demo_request) -> AnalysisReport:
    return run_analysis(demo_request)


@pytest.fixture(scope="module")
def demo_100mhz(demo_request) -> AnalysisReport:
    settings = demo_request.settings.model_copy(update={"bandwidth_hz": 100e6})
    return run_analysis(demo_request.model_copy(update={"settings": settings}))


@pytest.fixture(scope="module")
def err_report() -> AnalysisReport:
    return run_analysis(build_request(scope=FILES["scope_err"]))


# ---- steps 3 + 5: spec verdicts -------------------------------------------------------------


@pytest.mark.parametrize("answer", DEMO["specs"], ids=[s["metric_id"] for s in DEMO["specs"]])
def test_step3_spec_verdicts(demo, answer):
    r = pick(demo, answer["metric_id"])
    assert r.verdict == Verdict(answer["verdict"])
    assert r.spec is not None and r.spec.metric_id == answer["metric_id"]
    assert r.margin_pct == pytest.approx(answer["margin_pct"], abs=answer["abs_tol_pp"])


def test_step3_tpd_and_rise_judged_on_worst(demo):
    for mid in ("tpd", "rise_time"):
        r = pick(demo, mid)
        assert r.value == r.stats.max  # worst = max
        assert r.margin_pct == pytest.approx((r.spec.max - r.value) / r.spec.max * 100.0)
        assert r.margin_pct < 25.0  # noise makes the worst a bit slower than the nominal edge


# ---- step 5: sim deviation ------------------------------------------------------------------


@pytest.mark.parametrize("metric_id", sorted(GOLDEN["answers"]["sim_deviation_pct"]))
def test_step5_sim_deviation(demo, metric_id):
    answer = GOLDEN["answers"]["sim_deviation_pct"][metric_id]
    r = pick(demo, metric_id)
    assert r.sim_value is not None
    assert r.deviation_pct == pytest.approx(answer["value"], abs=answer["abs_tol_pp"])
    assert (WarningCode.SIM_DEVIATION in r.warnings) == (metric_id in TIMING_SIM_WARNINGS)


def test_step5_sim_warnings_and_card3(demo):
    flagged = {r.metric_id for r in demo.results if WarningCode.SIM_DEVIATION in r.warnings}
    assert flagged == TIMING_SIM_WARNINGS
    notices = [n for n in demo.warnings if n.code == WarningCode.SIM_DEVIATION]
    assert {n.metric_id for n in notices} == TIMING_SIM_WARNINGS
    assert all(n.source == Source.MEASURED and "허용 ±20.0% 초과" in n.message for n in notices)
    card = demo.cards.sim_deviation
    assert card is not None and card.warning_count == 4 and card.tolerance_pct == 20.0
    # largest = rise; fall (same edge_rate family, |39| > |33|) is skipped -> tplh second
    assert [i.metric_id for i in card.top] == ["rise_time", "tplh"]
    assert card.top[0].deviation_pct == pytest.approx(50.0, abs=2.0)
    assert card.top[1].deviation_pct == pytest.approx(33.3, abs=2.0)
    assert card.top[1].path == "Buffer"


def test_step5_vol_sim_zero_has_no_deviation(demo):
    vol = pick(demo, "vol")
    assert vol.sim_value == 0.0  # sim VOL is exactly 0 V -> deviation undefined (D6)
    assert vol.deviation_pct is None and WarningCode.SIM_DEVIATION not in vol.warnings


# ---- cards 1, 2, 4 and summary lines --------------------------------------------------------


def test_cards_demo(demo):
    v = demo.cards.verdicts
    c = DEMO["card_verdicts"]
    assert (v.pass_count, v.marginal_count, v.fail_count) == (c["pass"], c["marginal"], c["fail"])
    assert v.no_spec_count == len(demo.results) - 5
    w = demo.cards.worst_margin
    assert w is not None and w.metric_id == "voh" and w.verdict == Verdict.MARGINAL
    assert w.margin_pct == pytest.approx(9.375, abs=2.0)
    f = demo.cards.functional
    assert f is not None and f.verdict == Verdict.PASS
    assert (f.match_rate_pct, f.matched_cycles, f.compared_cycles, f.first_mismatch) == (100.0, 40, 40, None)


def test_summary_lines_demo_500mhz(demo):
    assert demo.summary_lines == [
        "전체 판정: PASS 4 · MARGINAL 1 · FAIL 0 — 최악 마진 VOH 9.4% (CH3)",
        "CH3 VOH 1.75 V — 스펙 ≥ 1.60 V 대비 마진 9.4% (MARGINAL)",
        COMMON_DELAY,
    ]


# ---- step 6: DMM / IDDQ ---------------------------------------------------------------------


def test_step6_dmm_iddq(demo):
    r = pick(demo, "iddq")
    assert r.channel_id == SETUP["dmm"]["sweep_name"]
    assert r.value == pytest.approx(GOLDEN["answers"]["dmm"]["iddq"]["value"], rel=0.005)
    assert r.verdict == Verdict.PASS and r.margin_pct == pytest.approx(40.0, abs=2.0)


def test_card1_without_dmm_and_expected():
    report = run_analysis(build_request(dmm=False, expected=False))
    v = report.cards.verdicts
    assert (v.pass_count, v.marginal_count, v.fail_count) == (2, 1, 0)  # tpd, rise / voh
    assert report.cards.functional is None
    assert not any(r.metric_id in ("iddq", "match_rate") for r in report.results)


# ---- step 7: functional ---------------------------------------------------------------------


def test_step7_match_rate_normal(demo):
    r = pick(demo, "match_rate")
    assert r.value == 100.0 and r.verdict == Verdict.PASS and r.margin_pct is None
    assert demo.functional is not None and demo.functional.first_mismatch is None


def test_step7_error_file_first_mismatch_37(err_report):
    answer = GOLDEN["answers"]["scope_err"]["match_rate"]
    r = pick(err_report, "match_rate")
    assert r.value == answer["value"] and r.verdict == Verdict.FAIL
    f = err_report.cards.functional
    assert f is not None and f.first_mismatch == 37 and f.verdict == Verdict.FAIL
    assert (f.matched_cycles, f.compared_cycles) == (answer["matched_cycles"], answer["compared_cycles"])
    assert "37번째 사이클에서 첫 불일치 (기대 1, 측정 0)" in err_report.summary_lines
    assert err_report.summary_lines[0].startswith("전체 판정: PASS 3 · MARGINAL 1 · FAIL 1")
    assert not any("(FAIL)" in ln for ln in err_report.summary_lines)  # match_rate -> line 2 only


def test_step7_error_file_delays_unchanged(err_report):
    for mid in ("tplh", "tphl"):
        answer = GOLDEN["answers"]["scope_err"][mid]
        r = pick(err_report, mid)
        assert r.value == pytest.approx(answer["value"], rel=answer["rel_tol_pct"] / 100.0)
        assert r.stats.mean == pytest.approx(answer["value"], rel=answer["rel_tol_pct"] / 100.0)


# ---- step 8: bandwidth ----------------------------------------------------------------------


def test_step8_bandwidth_500mhz_no_warning(demo):
    assert GOLDEN["answers"]["bandwidth"]["500e6"]["warnings"] == []
    assert not any(WarningCode.BANDWIDTH_LIMIT in r.warnings for r in demo.results)
    assert not any(n.code == WarningCode.BANDWIDTH_LIMIT for n in demo.warnings)
    assert not any(BW_TAIL in ln for ln in demo.summary_lines)


def test_step8_bandwidth_100mhz_warns_rise_fall(demo_100mhz):
    expected = GOLDEN["answers"]["bandwidth"]["100e6"]["warnings"]
    flagged = [r.metric_id for r in demo_100mhz.results if WarningCode.BANDWIDTH_LIMIT in r.warnings]
    assert flagged == expected
    notices = [n for n in demo_100mhz.warnings if n.code == WarningCode.BANDWIDTH_LIMIT]
    assert sorted(n.metric_id for n in notices) == sorted(expected)
    rise, fall = pick(demo_100mhz, "rise_time"), pick(demo_100mhz, "fall_time")
    assert demo_100mhz.summary_lines[-2:] == [
        f"CH3 rise {format_metric_value('rise_time', rise.stats.mean)}{BW_TAIL}",
        f"CH3 fall {format_metric_value('fall_time', fall.stats.mean)}{BW_TAIL}",
    ]
    assert demo_100mhz.summary_lines[:3] == [
        "전체 판정: PASS 4 · MARGINAL 1 · FAIL 0 — 최악 마진 VOH 9.4% (CH3)",
        "CH3 VOH 1.75 V — 스펙 ≥ 1.60 V 대비 마진 9.4% (MARGINAL)",
        COMMON_DELAY,
    ]
    assert len(demo_100mhz.summary_lines) == 5


# ---- report structure -----------------------------------------------------------------------


def test_report_structure(demo, demo_request):
    assert demo.results == sorted(demo.results, key=result_sort_key)
    assert demo.sim_results == sorted(demo.sim_results, key=result_sort_key)
    assert demo.warnings == sorted(demo.warnings, key=notice_sort_key)
    assert all(r.source == Source.MEASURED for r in demo.results)
    assert all(r.source == Source.SIM for r in demo.sim_results)
    assert all(r.verdict is None and r.spec is None and r.margin_pct is None and r.sim_value is None
               and r.deviation_pct is None for r in demo.sim_results)
    assert demo.sim_session is not None and demo.sim_session.source == Source.SIM
    assert demo.specs == demo_request.specs and demo.paths == demo_request.measured.paths
    assert len(demo.summary_lines) <= 8
    # first CLK rise (50 % crossing): tau = 25.03 ns on each set's own time axis
    clk0 = GOLDEN["edges"]["scope"]["clk_rise_s"][0]
    sim_clk0 = GOLDEN["edges"]["sim"]["clk_rise_s"][0]
    assert demo.clk_t0_s == pytest.approx(clk0, abs=0.2e-9)
    assert demo.sim_clk_t0_s == pytest.approx(sim_clk0, abs=0.1e-9)


def test_without_sim():
    report = run_analysis(build_request(sim=False))
    assert report.sim_session is None and report.sim_results == [] and report.sim_clk_t0_s is None
    assert report.cards.sim_deviation is None
    assert all(r.sim_value is None and WarningCode.SIM_DEVIATION not in r.warnings for r in report.results)
    assert COMMON_DELAY not in report.summary_lines


# ---- determinism and speed ------------------------------------------------------------------


def test_determinism_byte_identical(demo_request, demo):
    a = run_analysis(demo_request).model_dump_json()
    b = run_analysis(demo_request).model_dump_json()
    assert a == b == demo.model_dump_json()
    # rebuilt from the file bytes again -> same bytes; and round-trips through the contract model
    assert run_analysis(build_request(bandwidth_hz=500e6)).model_dump_json() == a
    assert AnalysisReport.model_validate_json(a).model_dump_json() == a


def test_performance(demo_request):
    assert all(w.n_samples == 20_000 for w in demo_request.measured.waveforms)
    assert len(demo_request.measured.waveforms) == 4
    run_analysis(demo_request)  # warm-up
    best = float("inf")
    for _ in range(3):
        t0 = time.perf_counter()
        run_analysis(demo_request)
        best = min(best, time.perf_counter() - t0)
    t0 = time.perf_counter()
    run_analysis(build_request(bandwidth_hz=500e6))
    with_read = time.perf_counter() - t0
    print(f"\nrun_analysis (20k x 4ch + sim 40k x 3ch + DMM): {best * 1e3:.1f} ms; "
          f"including adapter reads: {with_read * 1e3:.1f} ms")
    assert best < PERF_LIMIT_S
