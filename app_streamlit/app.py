"""ChipLens Streamlit entry point: ``streamlit run app_streamlit/app.py``."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st  # noqa: E402

from app_streamlit import dashboard, input_flow, state  # noqa: E402

st.set_page_config(page_title="ChipLens", page_icon=":material/memory:", layout="wide")
state.init_state()

st.title("ChipLens", anchor=False)
st.caption("칩 측정 분석 — 타이밍 · DC·전력 · 기능 검증 · 시뮬 비교 (Phase 0 MVP)")

# Stateful top-level tabs. The input flow is rendered on every run (hidden while the dashboard tab is
# open) so its widgets keep their values across view switches; the dashboard is built only when open.
views = st.tabs([state.VIEW_INPUT, state.VIEW_DASH], key=state.VIEW_KEY, on_change="rerun")
with views[0]:
    input_flow.render_input_flow(visible=views[0].open is not False)
with views[1]:
    if views[1].open is not False:
        dashboard.render_from_state()
