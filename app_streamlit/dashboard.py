"""Dashboard (plan 9.1): header -> 4 cards -> margin bars -> 6 tabs -> summary lines.

Reads only ``AnalysisReport`` + the normalized inputs the UI holds (``MeasurementSet`` for waveforms,
``RawTable`` for the raw-data tab). Every widget has a fixed key (AppTest-friendly).
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from core.models import (
    METRICS,
    VERDICT_SYMBOLS,
    AnalysisReport,
    AnalysisResult,
    Category,
    MeasurementSet,
    Role,
    Verdict,
    format_metric_value,
    format_pct,
    format_si,
    format_spec,
)

from . import figures as F
from . import viewmodel as vm
from .state import (
    DASH_TAB_KEY,
    DASH_WF_KEY,
    MEASURED_KEY,
    RAW_TABLES_KEY,
    REPORT_IS_MOCK_KEY,
    REPORT_KEY,
    REPORT_NOTE_KEY,
    SIM_KEY,
    TIMING_KEY,
    TAB_LABELS,
    VIEW_INPUT,
    goto,
    open_tab,
)
from .theme import verdict_md

_DEF_COL = st.column_config.TextColumn("정의", help="지표 정의 (METRICS.definition)", width="large")


def is_dark() -> bool:
    """Active Streamlit theme is dark (None in bare/AppTest runs -> light)."""
    try:
        return st.context.theme.type == "dark"
    except Exception:  # noqa: BLE001
        return False


def _chart(fig, key: str) -> None:
    st.plotly_chart(fig, key=key, width="stretch", config={"displaylogo": False})


def _table(df: pd.DataFrame, key: str, **kw) -> None:
    if df.empty:
        st.caption("표시할 행이 없습니다")
        return
    cfg = {"정의": _DEF_COL} if "정의" in df.columns else None
    st.dataframe(df, key=key, hide_index=True, width="stretch", column_config=cfg, **kw)


# ======================================================================= entry


def render_from_state() -> None:
    """Dashboard view: the report in session state, or a prompt to load one."""
    report: AnalysisReport | None = st.session_state.get(REPORT_KEY)
    if report is None:
        st.info("아직 분석 결과가 없습니다. '입력·분석' 탭에서 파일을 불러오고 분석을 실행하세요.")
        st.button("입력·분석으로", key="dash_goto_input", on_click=goto, args=(VIEW_INPUT,))
        return
    render_dashboard(
        report,
        measured=st.session_state.get(MEASURED_KEY),
        sim=st.session_state.get(SIM_KEY),
        raw_tables=st.session_state.get(RAW_TABLES_KEY) or {},
        is_mock=bool(st.session_state.get(REPORT_IS_MOCK_KEY)),
        note=st.session_state.get(REPORT_NOTE_KEY),
        timing=st.session_state.get(TIMING_KEY),
    )


def render_dashboard(
    report: AnalysisReport,
    *,
    measured: MeasurementSet | None = None,
    sim: MeasurementSet | None = None,
    raw_tables: dict | None = None,
    is_mock: bool = False,
    note: str | None = None,
    timing: dict | None = None,
) -> None:
    dark = is_dark()
    _header(report, is_mock, note, timing)
    _cards(report)
    _margin_section(report)
    _tabs(report, measured, sim, raw_tables or {}, dark)
    _summary(report)


# ======================================================================= header


def _header(report: AnalysisReport, is_mock: bool, note: str | None, timing: dict | None = None) -> None:
    h = vm.header_lines(report)
    with st.container(border=True):
        left, right = st.columns([5, 1], vertical_alignment="center")
        with left:
            title = f"#### {h['chip']}"
            if is_mock:
                title += "  :orange-badge[목업]"
            st.markdown(title, anchors=False)
            st.markdown(f"**조건** {h['conditions']}  \n**측정 파일** {h['files']}"
                        + (f"  \n**시뮬 파일** {h['sim_files']}" if h["sim_files"] else ""))
            extra = ""
            if timing:
                extra = f" · 분석 {timing['run_s']:.2f} s (요청 구성 포함 {timing['total_s']:.2f} s)"
            st.caption(h["settings"] + extra)
        with right:
            st.button("매핑 수정", key="dash_edit_mapping", on_click=goto, args=(VIEW_INPUT,),
                      help="입력·분석 화면으로 돌아가 역할·단위·경로를 고칩니다", width="stretch")
    if note:
        st.info(note)


# ======================================================================= cards


def _card_label(text: str, help_text: str | None = None) -> None:
    st.markdown(f"**{text}**", help=help_text)


def _cards(report: AnalysisReport) -> None:
    cards = report.cards
    cmap = report.channel_map
    c1, c2, c3, c4 = st.columns(4)

    with c1, st.container(border=True, height="stretch"):
        _card_label("전체 판정", "스펙 판정 + 기능 일치율 결과의 등급 개수 (D9)")
        overall = vm.overall_verdict(cards.verdicts)
        st.markdown(f"#### {verdict_md(overall)}", anchors=False)
        st.markdown(vm.verdict_counts_md(cards.verdicts))
        st.caption(f"– 스펙 없음 {cards.verdicts.no_spec_count}개 지표")

    with c2, st.container(border=True, height="stretch"):
        wm = cards.worst_margin
        _card_label("최악 마진", vm.metric_help(wm.metric_id) if wm else None)
        head, detail = vm.worst_margin_texts(wm, cmap)
        st.markdown(f"#### {verdict_md(wm.verdict if wm else None, head)}", anchors=False)
        st.caption(detail)
        if wm is not None:
            key = f"{wm.metric_id}|{wm.path or ''}|{wm.channel_id or ''}"
            st.button("파형에서 보기", key="dash_card_worst", on_click=open_tab, args=("파형", key),
                      type="tertiary")

    with c3, st.container(border=True, height="stretch"):
        sd = cards.sim_deviation
        _card_label("시뮬 최대 편차", "(측정 평균 − 지연 보정 − 시뮬 평균) / |시뮬| × 100. 같은 계열 지표는 1개만 (D9)")
        head, detail = vm.sim_deviation_texts(sd, cmap)
        warn = sd is not None and sd.warning_count > 0
        st.markdown(f"#### {verdict_md(Verdict.MARGINAL, head) if warn else head}", anchors=False)
        st.caption(detail)
        if sd is not None:
            st.button("시뮬 비교 보기", key="dash_card_sim", on_click=open_tab, args=("시뮬 비교",), type="tertiary")

    with c4, st.container(border=True, height="stretch"):
        _card_label("기능 일치율", vm.metric_help("match_rate"))
        head, detail, verdict = vm.functional_texts(cards.functional, report.functional)
        st.markdown(f"#### {verdict_md(verdict, head)}", anchors=False)
        st.caption(detail)
        if report.functional is not None:
            st.button("기능 탭 보기", key="dash_card_func", on_click=open_tab, args=("기능",), type="tertiary")


# ======================================================================= margin bars


def _margin_section(report: AnalysisReport) -> None:
    st.markdown("##### 지표별 마진", anchors=False,
                help="막대 색 = 등급 (✓ PASS 초록 · ! MARGINAL 주황 · ✕ FAIL 빨강 · – 스펙 없음 회색). "
                     "막대 끝에 기호·등급·마진을 함께 적습니다. 막대에 마우스를 올리면 지표 정의가 보입니다.")
    show_all = st.toggle("스펙 없는 지표도 표시", key="dash_show_nospec")
    _chart(F.margin_bar_figure(report, include_no_spec=show_all), "dash_margin_chart")


# ======================================================================= tabs


def _tabs(report: AnalysisReport, measured: MeasurementSet | None, sim: MeasurementSet | None,
          raw_tables: dict, dark: bool) -> None:
    if st.session_state.get(DASH_TAB_KEY) not in TAB_LABELS:
        st.session_state[DASH_TAB_KEY] = TAB_LABELS[0]
    tabs = st.tabs(TAB_LABELS, key=DASH_TAB_KEY, on_change="rerun")
    renderers = [
        lambda: _tab_waveform(report, measured, dark),
        lambda: _tab_timing(report, dark),
        lambda: _tab_dc(report, measured, dark),
        lambda: _tab_functional(report, dark),
        lambda: _tab_sim(report, measured, sim, dark),
        lambda: _tab_raw(report, measured, sim, raw_tables),
    ]
    for tab, render in zip(tabs, renderers):
        with tab:
            if tab.open is False:  # lazy: only the selected tab runs (None = no state tracking -> run all)
                continue
            render()


def _has_waves(mset: MeasurementSet | None) -> bool:
    return mset is not None and bool(mset.waveforms)


def _no_wave_info(what: str) -> None:
    st.info(f"파형 데이터 없음 — 측정 파형 파일을 불러와 분석을 실행하면 이 자리에 {what}이(가) 그려집니다.")


def _result_option(r: AnalysisResult, report: AnalysisReport) -> str:
    v = f"{VERDICT_SYMBOLS[r.verdict]} " if r.verdict is not None else ""
    return f"{v}{vm.result_title(r, report.channel_map)} — {format_metric_value(r.metric_id, r.value)}"


def _tab_waveform(report: AnalysisReport, measured: MeasurementSet | None, dark: bool) -> None:
    cands = vm.highlight_candidates(report)
    if not cands:
        st.caption("강조할 지표가 없습니다")
        return
    by_key = {vm.result_key(r): r for r in cands}
    if st.session_state.get(DASH_WF_KEY) not in by_key:
        d = vm.default_highlight(report)
        st.session_state[DASH_WF_KEY] = vm.result_key(d) if d else next(iter(by_key))
    sel = st.selectbox("강조할 지표 (근거 마커 표시)", list(by_key), key=DASH_WF_KEY,
                       format_func=lambda k: _result_option(by_key[k], report),
                       help="카드의 '파형에서 보기'로도 선택됩니다. 마커에 마우스를 올리면 엣지 시각·기준 전압이 보입니다.")
    r = by_key[sel]
    st.caption(f"{METRICS[r.metric_id].label}: {METRICS[r.metric_id].definition}")
    if _has_waves(measured):
        zoom = st.toggle("최악 엣지 주변 확대", value=True, key="dash_wf_zoom",
                         help="끄면 전체 기록을 보여줍니다. 차트에서 드래그로 확대, 더블클릭으로 복귀.")
        _chart(F.waveform_figure(measured, r, zoom_to_highlight=zoom, dark=dark), "dash_wf_chart")
    else:
        _no_wave_info("공유 시간축 다채널 파형과 근거 마커(50 % 교차점, 10/90 % 점, tpd 구간 음영)")
    if r.evidence.edges or r.evidence.ref_levels_v:
        with st.expander(f"근거(Evidence) — 엣지 {len(r.evidence.edges)}개", expanded=not _has_waves(measured)):
            if r.evidence.ref_levels_v:
                st.caption("기준 레벨: " + " · ".join(f"{k} {v:.4g}" for k, v in r.evidence.ref_levels_v.items()))
            if r.evidence.edges:
                _table(vm.evidence_table(r), "dash_wf_evidence")


def _tab_timing(report: AnalysisReport, dark: bool) -> None:
    timing = [r for r in report.results if r.category == Category.TIMING]
    st.markdown("##### 경로·채널별 타이밍 지표", anchors=False)
    _table(vm.results_table(timing, report.channel_map), "dash_timing_table")
    st.markdown("##### 엣지별 분포", anchors=False,
                help="상자 = 사분위, 점 = 엣지 하나. 점선 = 스펙, ◆ = 시뮬 평균. 지표마다 축이 따로입니다.")
    _chart(F.edge_distribution_figure(timing, report.channel_map, dark=dark), "dash_timing_dist")


def _metric_tile(r: AnalysisResult, report: AnalysisReport) -> None:
    m = METRICS[r.metric_id]
    with st.container(border=True):
        st.metric(f"{m.label} · {vm.result_target(r, report.channel_map)}",
                  format_metric_value(r.metric_id, r.value), help=vm.metric_help(r.metric_id))
        parts = [verdict_md(r.verdict)]
        if r.spec is not None:
            parts.append(f"스펙 {format_spec(r.spec)}")
        if r.margin_pct is not None:
            parts.append(f"마진 {format_pct(r.margin_pct)}")
        st.markdown(" · ".join(parts))


def _tab_dc(report: AnalysisReport, measured: MeasurementSet | None, dark: bool) -> None:
    dc = [r for r in report.results if r.category == Category.DC]
    if dc:
        cols = st.columns(min(len(dc), 5))
        for i, r in enumerate(dc):
            with cols[i % len(cols)]:
                _metric_tile(r, report)
    st.markdown("##### I–V 곡선", anchors=False, help=vm.metric_help("iddq"))
    if measured is not None and measured.dc_sweeps:
        log_y = st.toggle("전류 로그 축 (누설 영역)", key="dash_iv_log")
        _chart(F.iv_figure(measured.dc_sweeps, logic_vdd_v=report.settings.logic_vdd_v,
                           iddq_results=[r for r in dc if r.metric_id == "iddq"], log_y=log_y, dark=dark),
               "dash_iv_chart")
    else:
        st.info("DC 스윕 데이터 없음 — 멀티미터 xlsx를 'DC 스윕'으로 불러오면 I–V 곡선과 IDDQ 점이 그려집니다.")
    st.markdown("##### IDD 시간 파형", anchors=False, help=vm.metric_help("idd_avg"))
    idd_ids = report.channel_map.ids_with_role(Role.IDD)
    if _has_waves(measured) and any(measured.waveform(c) for c in idd_ids):
        idd_res = next((r for r in dc if r.metric_id == "idd_avg"), None)
        _chart(F.waveform_figure(measured, idd_res, channels=idd_ids, zoom_to_highlight=False, dark=dark),
               "dash_idd_chart")
    else:
        _no_wave_info("IDD 시간 파형")
    _table(vm.results_table(dc, report.channel_map), "dash_dc_table")


def _tab_functional(report: AnalysisReport, dark: bool) -> None:
    d = report.functional
    if d is None:
        st.info("기능 검증 데이터가 없습니다 — CLK와 OUT 채널 파형이 필요합니다.")
        return
    head, detail, verdict = vm.functional_texts(report.cards.functional, d)
    st.markdown(f"**{verdict_md(verdict, head)}** · {detail} · 대상 {report.channel_map.display_name(d.channel_id)}, "
                f"클럭 {report.channel_map.display_name(d.clk_channel_id)}, 임계 {d.threshold_v:g} V",
                help=vm.metric_help("match_rate"))
    st.markdown(f"측정 비트 ({len(d.measured_bits)}): {vm.bits_markdown(d, 'measured')}")
    if d.expected_bits is not None:
        st.markdown(f"기대 비트 ({len(d.expected_bits)}): {vm.bits_markdown(d, 'expected')}")
        if d.mismatch_cycles:
            st.markdown(verdict_md(Verdict.FAIL, f"✕ 불일치 사이클: {', '.join(map(str, d.mismatch_cycles))}"))
    _chart(F.functional_figure(d, dark=dark), "dash_func_chart")


def _tab_sim(report: AnalysisReport, measured: MeasurementSet | None, sim: MeasurementSet | None,
             dark: bool) -> None:
    if report.sim_session is None and not any(r.sim_value is not None for r in report.results):
        st.info("시뮬 파일이 없습니다 — ①에서 '시뮬 파형'으로 파일을 추가하세요.")
        return
    st.markdown("##### 지표별 편차", anchors=False,
                help=f"회색 띠 = 허용 ±{report.settings.sim_tolerance_pct:g}%. 초과 막대는 주황 + '!' 표시.")
    _chart(F.deviation_figure(report), "dash_dev_chart")
    _table(vm.deviation_table(report), "dash_dev_table")
    st.markdown("##### 파형 겹쳐 보기", anchors=False,
                help="각 세트의 첫 CLK 상승 50 % 시각을 0으로 맞춘 표시 전용 정렬 (D6)")
    t0 = format_si(report.clk_t0_s, "s", sig=6)
    st0 = format_si(report.sim_clk_t0_s, "s", sig=6)
    st.caption(f"정렬 기준: 측정 첫 CLK 상승 {t0} · 시뮬 첫 CLK 상승 {st0}")
    if _has_waves(measured) and _has_waves(sim):
        full = st.toggle("전체 기록 보기", key="dash_sim_full")
        _chart(F.sim_overlay_figure(measured, sim, clk_t0_s=report.clk_t0_s, sim_clk_t0_s=report.sim_clk_t0_s,
                                    window=None if full else vm.sim_overlay_window(report), dark=dark), "dash_sim_overlay")
    else:
        _no_wave_info("측정·시뮬 겹쳐 보기")


def _tab_raw(report: AnalysisReport, measured: MeasurementSet | None, sim: MeasurementSet | None,
             raw_tables: dict) -> None:
    st.markdown("##### 채널 매핑·단위", anchors=False)
    _table(vm.channel_rows(report.channel_map, measured), "dash_raw_channels")
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("##### 경로", anchors=False)
        _table(pd.DataFrame([{"이름": p.name, "입력": p.input_channel, "출력": p.output_channel,
                              "극성": "비반전" if p.polarity.value == "non_inverting" else "반전"}
                             for p in report.paths]), "dash_raw_paths")
    with c2:
        st.markdown("##### 스펙 (표시 단위 · SI)", anchors=False)
        _table(vm.spec_rows(report.specs), "dash_raw_specs")
    st.markdown("##### 분석 설정 · 세션", anchors=False)
    s = report.settings
    settings_rows = [
        ("논리 VDD", f"{s.logic_vdd_v:g} V"),
        ("오실로 대역폭", format_si(s.bandwidth_hz, "Hz") if s.bandwidth_hz else "미입력"),
        ("MARGINAL 임계", f"{s.marginal_threshold_pct:g}%"),
        ("시뮬 허용 편차", f"±{s.sim_tolerance_pct:g}%"),
        ("지연 보정 오프셋", format_si(s.delay_offset_s, "s")),
        ("엣지 히스테리시스", f"{s.edge_hysteresis_pct:g}%"),
        ("최소 펄스폭", format_si(s.min_pulse_width_s, "s")),
        ("평활화 점 수", str(s.smoothing_points)),
        ("측정 샘플 간격", format_si(report.session.sample_interval_s, "s")),
        ("시뮬 샘플 간격", format_si(report.sim_session.sample_interval_s, "s") if report.sim_session else "—"),
    ]
    _table(pd.DataFrame(settings_rows, columns=["항목", "값"]), "dash_raw_settings")
    st.markdown("##### 정규화 표", anchors=False)
    if raw_tables:
        name = st.selectbox("파일", list(raw_tables), key="dash_raw_file")
        table = raw_tables[name]
        st.caption("값은 원시값(단위 변환 전)입니다. 열 단위·배율:")
        _table(pd.DataFrame([{"열": c.name, "헤더": c.header, "기본 이름": c.base_name, "단위": c.unit_text or "",
                              "SI": c.si_unit or "", "배율": c.scale, "숫자": c.numeric} for c in table.columns]),
               "dash_raw_cols")
        st.dataframe(table.data, key="dash_raw_data", width="stretch", height=320)
    else:
        st.info("원본 표 없음 — 파일을 불러와 분석하면 정규화된 표가 여기에 표시됩니다.")
    st.download_button("보고서 JSON 내려받기", report.model_dump_json(indent=2), file_name="chiplens_report.json",
                       mime="application/json", key="dash_download_json")


# ======================================================================= summary


def _summary(report: AnalysisReport) -> None:
    st.divider()
    st.markdown("##### 요약", anchors=False, help="규칙 기반 요약 문구 (D9, 최대 8줄)")
    if report.summary_lines:
        lines = [f"- **{report.summary_lines[0]}**"] + [f"- {s}" for s in report.summary_lines[1:]]
        st.markdown("\n".join(lines))
    else:
        st.caption("요약 문구가 없습니다")
    notes = vm.notice_rows(report)
    if notes:
        with st.expander(f"경고 {len(notes)}건", expanded=True):
            st.markdown("\n".join(f"- {n}" for n in notes))
