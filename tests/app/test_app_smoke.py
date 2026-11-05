"""AppTest smoke tests for the Streamlit app (dashboard-agent).

Default run, mock-report dashboard (cards PASS 4 · MARGINAL 1), every tab, card -> tab navigation,
demo-defaults button, and (when core.adapters + synth/data exist) the sample-data input flow.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "app_streamlit" / "app.py"
SAMPLES = ROOT / "synth" / "data"
TABS = ["파형", "타이밍", "DC·전력", "기능", "시뮬 비교", "원본 데이터"]
MOCK_BITS = "0000001000001100001010001111001000101100"  # same PRBS as tests/fixtures/mock_report.json


def _app() -> AppTest:
    at = AppTest.from_file(str(APP), default_timeout=120)
    at.run()
    return at


def _plain(md: str) -> str:
    """Strip Streamlit color directives ':green[...]', ':orange-badge[...]'."""
    return re.sub(r":[a-z]+(?:-[a-z]+)?\[([^\]]*)\]", r"\1", md)


def _open_mock(at: AppTest) -> AppTest:
    at.button(key="btn_mock").click().run()
    assert not at.exception
    return at


def test_app_default_run_has_no_exception():
    at = _app()
    assert not at.exception
    assert at.session_state["view"] == "입력·분석"
    assert at.button(key="btn_demo_defaults") is not None


def test_mock_button_only_in_collapsed_dev_expander():
    at = _app()
    dev = [x for x in at.expander if x.label == "개발용"]
    assert len(dev) == 1 and dev[0].proto.expanded is False
    assert [b.key for b in dev[0].button] == ["btn_mock"]
    # the main flow has no mock buttons and no "준비 중" notice
    assert [b.key for b in at.button].count("btn_mock") == 1
    assert "btn_mock_dash" not in [b.key for b in at.button]
    assert not any("준비 중" in str(e.value) for e in [*at.info, *at.warning, *at.error, *at.caption])


def test_empty_dashboard_has_no_mock_fallback():
    at = _app()
    at.session_state["view"] = "대시보드"
    at.run()
    assert not at.exception
    assert any("아직 분석 결과가 없습니다" in i.value for i in at.info)
    assert "btn_mock_dash" not in [b.key for b in at.button]
    at.button(key="dash_goto_input").click().run()
    assert at.session_state["view"] == "입력·분석"


def test_mock_report_cards_render():
    at = _open_mock(_app())
    assert at.session_state["view"] == "대시보드"
    md = [m.value for m in at.markdown]
    plain = [_plain(m) for m in md]
    # card 1: counts with symbols (color + symbol + label)
    assert any("✓ PASS 4 · ! MARGINAL 1 · ✕ FAIL 0" in m for m in plain)
    # card 2 / 3 / 4 headlines
    assert any("! VOH 1.75 V" in m for m in plain)
    assert any("rise(CH3) +50.0% · tpLH(Buffer) +33.3%" in m for m in plain)
    assert any("✓ 100% (40/40 사이클)" in m for m in plain)
    # summary line from the report
    assert any("전체 판정: PASS 4 · MARGINAL 1 · FAIL 0" in m for m in md)


def test_mock_dashboard_every_tab_renders():
    at = _open_mock(_app())
    for tab in TABS:
        at.session_state["dash_tab"] = tab
        at.run()
        assert not at.exception, tab
    at.session_state["dash_tab"] = "파형"
    at.run()
    assert any(i.value.startswith("파형 데이터 없음 —") for i in at.info)
    assert not any("(목업)" in i.value for i in at.info)


def test_card_button_opens_tab_and_highlights_metric():
    at = _open_mock(_app())
    at.button(key="dash_card_worst").click().run()
    assert not at.exception
    assert at.session_state["dash_tab"] == "파형"
    assert at.session_state["dash_wf_metric"] == "voh||CH3"
    at.button(key="dash_card_sim").click().run()
    assert at.session_state["dash_tab"] == "시뮬 비교"
    at.button(key="dash_edit_mapping").click().run()
    assert not at.exception
    assert at.session_state["view"] == "입력·분석"


def test_demo_defaults_apply_only_on_click():
    at = _app()
    assert at.session_state["in_logic_vdd"] == 1.8
    assert at.session_state["in_bandwidth_mhz"] is None
    assert at.session_state["specs_base"] == []
    at.button(key="btn_demo_defaults").click().run()
    assert not at.exception
    assert at.session_state["in_bandwidth_mhz"] == 500.0
    assert [at.session_state[f"role::CH{i}"] for i in range(1, 5)] == ["CLK", "IN", "OUT", "IDD"]
    assert at.session_state["paths_base"] == [
        {"이름": "Buffer", "입력 채널": "CH2", "출력 채널": "CH3", "극성": "비반전"}]
    assert [r["지표"].split(" · ")[0] for r in at.session_state["specs_base"]] == ["tpd", "rise_time", "voh", "iddq"]


def test_demo_defaults_before_any_file_shows_no_error():
    """QA-01: demo defaults pressed before choosing a file -> neutral info, no red 'unknown channel' error."""
    at = _app()
    at.button(key="btn_demo_defaults").click().run()
    assert not at.exception
    assert [e.value for e in at.error] == []
    assert any("측정 파일을 고르면 채널이 연결됩니다" in i.value for i in at.info)


@pytest.mark.skipif(not (SAMPLES / "synth_scope.csv").exists(), reason="synth/data not generated")
def test_path_to_missing_channel_is_still_an_error_once_files_exist():
    pytest.importorskip("core.adapters")
    at = _app()
    at.session_state["paths_base"] = [{"이름": "Buffer", "입력 채널": "CH2", "출력 채널": "CH9", "극성": "비반전"}]
    at.multiselect(key="in_samples").set_value(["synth_scope.csv"]).run()
    assert not at.exception
    assert any("경로 'Buffer': 알 수 없는 채널 CH9" in e.value for e in at.error)
    assert not any("측정 파일을 고르면 채널이 연결됩니다" in i.value for i in at.info)


@pytest.mark.skipif(not (SAMPLES / "synth_scope.csv").exists(), reason="synth/data not generated")
def test_sample_data_flow_reaches_dashboard():
    pytest.importorskip("core.adapters")
    at = _app()
    at.multiselect(key="in_samples").set_value(["synth_scope.csv", "synth_sim.csv", "synth_dmm.xlsx"]).run()
    assert not at.exception
    at.button(key="btn_demo_defaults").click().run()
    at.text_area(key="in_expected_bits").input(MOCK_BITS).run()
    assert not at.exception
    assert [e.value for e in at.error] == []
    at.button(key="btn_run").click().run()
    assert not at.exception
    assert at.session_state["view"] == "대시보드"
    measured = at.session_state["measured_set"]
    assert [w.channel_id for w in measured.waveforms] == ["CH1", "CH2", "CH3", "CH4"]
    assert len(measured.dc_sweeps) == 1
    sim = at.session_state["sim_set"]
    assert sim is not None and [w.channel_id for w in sim.waveforms] == ["CH1", "CH2", "CH3"]  # re-keyed (D3)
    for tab in TABS:
        at.session_state["dash_tab"] = tab
        at.run()
        assert not at.exception, tab
