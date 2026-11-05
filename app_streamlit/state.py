"""Session-state keys, navigation callbacks and the demo-defaults button (streamlit only, no logic)."""

from __future__ import annotations

from typing import Any

import streamlit as st

from core.models import AnalysisReport, MeasurementSet, Role

from .request_builder import ALL
from .viewmodel import load_mock_report

# ---- keys
VIEW_KEY = "view"
VIEW_INPUT = "입력·분석"
VIEW_DASH = "대시보드"
PENDING_VIEW_KEY = "_pending_view"

DASH_TAB_KEY = "dash_tab"
DASH_WF_KEY = "dash_wf_metric"
TAB_LABELS = ["파형", "타이밍", "DC·전력", "기능", "시뮬 비교", "원본 데이터"]

REPORT_KEY = "report"
REPORT_IS_MOCK_KEY = "report_is_mock"
REPORT_NOTE_KEY = "report_note"
MEASURED_KEY = "measured_set"
SIM_KEY = "sim_set"
RAW_TABLES_KEY = "raw_tables"
TIMING_KEY = "report_timing"  # {"run_s": run_analysis seconds, "total_s": click -> report seconds}

# Non-widget memories: survive a widget disappearing for a rerun (e.g. measured file swapped, demo step 7)
ROLE_MEMORY_KEY = "role_memory"
LABEL_MEMORY_KEY = "label_memory"
EXPECTED_BITS_KEY = "in_expected_bits"
EXPECTED_CH_KEY = "in_expected_channel"
EXPECTED_CH_MEMORY_KEY = "expected_channel_memory"
EXPECTED_CH_FORCED_KEY = "_expected_channel_forced"

PATHS_BASE_KEY = "paths_base"
PATHS_VER_KEY = "paths_ver"
SPECS_BASE_KEY = "specs_base"
SPECS_VER_KEY = "specs_ver"

LOGIC_VDD_KEY = "in_logic_vdd"
BANDWIDTH_KEY = "in_bandwidth_mhz"

PATH_COLUMNS = ["이름", "입력 채널", "출력 채널", "극성"]
SPEC_COLUMNS = ["지표", "경로", "채널", "최소", "최대"]
POLARITY_LABELS = {"비반전": "non_inverting", "반전": "inverting"}


def role_key(channel_id: str) -> str:
    return f"role::{channel_id}"


def label_key(channel_id: str) -> str:
    return f"label::{channel_id}"


def init_state() -> None:
    """Set non-widget defaults once per session."""
    defaults: dict[str, Any] = {
        VIEW_KEY: VIEW_INPUT,
        REPORT_KEY: None,
        REPORT_IS_MOCK_KEY: False,
        REPORT_NOTE_KEY: None,
        MEASURED_KEY: None,
        SIM_KEY: None,
        RAW_TABLES_KEY: {},
        PATHS_BASE_KEY: [],
        PATHS_VER_KEY: 0,
        SPECS_BASE_KEY: [],
        SPECS_VER_KEY: 0,
        TIMING_KEY: None,
        ROLE_MEMORY_KEY: {},
        LABEL_MEMORY_KEY: {},
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v
    pending = st.session_state.pop(PENDING_VIEW_KEY, None)
    if pending is not None:
        st.session_state[VIEW_KEY] = pending


def init_key(key: str, value: Any) -> None:
    """Initialize a widget key once (widgets are then created with `key=` only)."""
    if key not in st.session_state:
        st.session_state[key] = value


# ---- navigation (safe inside callbacks)


def goto(view: str) -> None:
    st.session_state[VIEW_KEY] = view


def goto_after_rerun(view: str) -> None:
    """Use from inline code after the view widget was already created this run."""
    st.session_state[PENDING_VIEW_KEY] = view


def open_tab(tab: str, wf_metric_key: str | None = None) -> None:
    """Card button callback: switch the dashboard tab (and highlight a metric on the waveform tab)."""
    st.session_state[DASH_TAB_KEY] = tab
    if wf_metric_key is not None:
        st.session_state[DASH_WF_KEY] = wf_metric_key


def set_report(
    report: AnalysisReport,
    *,
    is_mock: bool,
    note: str | None = None,
    measured: MeasurementSet | None = None,
    sim: MeasurementSet | None = None,
    raw_tables: dict | None = None,
    timing: dict | None = None,
) -> None:
    st.session_state[REPORT_KEY] = report
    st.session_state[REPORT_IS_MOCK_KEY] = is_mock
    st.session_state[REPORT_NOTE_KEY] = note
    st.session_state[MEASURED_KEY] = measured
    st.session_state[SIM_KEY] = sim
    st.session_state[RAW_TABLES_KEY] = raw_tables or {}
    st.session_state[TIMING_KEY] = timing
    st.session_state.pop(DASH_WF_KEY, None)  # re-pick the default highlight for the new report


def show_mock_report() -> None:
    """Dev-only callback: show tests/fixtures/mock_report.json on the dashboard (no waveforms)."""
    set_report(load_mock_report(), is_mock=True,
               note="목업 보고서(tests/fixtures/mock_report.json)입니다. 엣지 값은 결정적 가짜 지터이고 파형 배열이 없습니다.")
    goto(VIEW_DASH)


# ---- demo defaults (plan 4.2) — applied only when the user presses the button

DEMO_ROLES = {"CH1": Role.CLK, "CH2": Role.IN, "CH3": Role.OUT, "CH4": Role.IDD}
DEMO_PATHS = [{"이름": "Buffer", "입력 채널": "CH2", "출력 채널": "CH3", "극성": "비반전"}]
DEMO_SPECS = [  # display units (ns, V, µA); converted to SI when the request is built
    {"metric_id": "tpd", "min": None, "max": 8.0},
    {"metric_id": "rise_time", "min": None, "max": 4.0},
    {"metric_id": "voh", "min": 1.6, "max": None},
    {"metric_id": "iddq", "min": None, "max": 2.5},
]
DEMO_LOGIC_VDD = 1.8
DEMO_BANDWIDTH_MHZ = 500.0


def apply_demo_defaults(metric_option_of: dict[str, str]) -> None:
    """Callback: fill roles CH1 CLK · CH2 IN · CH3 OUT · CH4 IDD, path Buffer CH2→CH3,
    logic VDD 1.8 V, bandwidth 500 MHz and the 4 demo specs."""
    for cid, role in DEMO_ROLES.items():
        st.session_state[role_key(cid)] = role
        st.session_state[ROLE_MEMORY_KEY][cid] = role
    st.session_state[PATHS_BASE_KEY] = [dict(r) for r in DEMO_PATHS]
    st.session_state[PATHS_VER_KEY] = st.session_state.get(PATHS_VER_KEY, 0) + 1
    st.session_state[SPECS_BASE_KEY] = [
        {"지표": metric_option_of[s["metric_id"]], "경로": ALL, "채널": ALL, "최소": s["min"], "최대": s["max"]}
        for s in DEMO_SPECS
    ]
    st.session_state[SPECS_VER_KEY] = st.session_state.get(SPECS_VER_KEY, 0) + 1
    st.session_state[LOGIC_VDD_KEY] = DEMO_LOGIC_VDD
    st.session_state[BANDWIDTH_KEY] = DEMO_BANDWIDTH_MHZ
    st.session_state["_demo_applied"] = True


def fill_sample_bits(bits: str) -> None:
    """Callback: put the sample expected bit string (synth/data/golden.json 'bits') in the text area."""
    st.session_state[EXPECTED_BITS_KEY] = bits
