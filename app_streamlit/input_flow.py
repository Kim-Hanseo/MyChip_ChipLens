"""Input flow (plan 7 ①–⑦) in the contract section-6 call order.

① upload / sample files + data kind → ② preview_file (auto, then with edited ReadOptions) → read_table
→ ③ units/probe (to_waveforms) or DC columns (to_dc_sweep) → ④ roles + logic VDD/bandwidth
→ ⑤ paths → ⑥ specs (display units → SI), sim mapping (suggest_sim_mapping → to_waveforms re-keyed),
expected bits, settings → ⑦ AnalysisRequest → core.pipeline.run_analysis.
When core.adapters / core.pipeline are missing, a Korean st.error says so and the run button is disabled;
an exception from run_analysis is shown as st.error (never replaced by the mock report — that one lives
only in the collapsed "개발용" expander).
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field

import pandas as pd
import streamlit as st
from pydantic import ValidationError

from core.models import (
    ROLE_LABELS,
    ChannelConversion,
    ChannelMap,
    DCSweep,
    FileKind,
    Notice,
    RawTable,
    ReadOptions,
    Role,
    TablePreview,
    TimeAxisSpec,
    Waveform,
    format_spec,
    format_si,
)

from . import figures as F
from . import request_builder as rb
from . import viewmodel as vm
from .core_bridge import (
    cached_preview,
    cached_read_table,
    cached_to_dc_sweep,
    cached_to_waveforms,
    conversions_json,
    get_adapters,
    get_run_analysis,
)
from .dashboard import is_dark
from .state import (
    BANDWIDTH_KEY,
    EXPECTED_BITS_KEY,
    EXPECTED_CH_FORCED_KEY,
    EXPECTED_CH_KEY,
    EXPECTED_CH_MEMORY_KEY,
    LABEL_MEMORY_KEY,
    REPORT_IS_MOCK_KEY,
    REPORT_KEY,
    ROLE_MEMORY_KEY,
    LOGIC_VDD_KEY,
    PATH_COLUMNS,
    PATHS_BASE_KEY,
    PATHS_VER_KEY,
    SPEC_COLUMNS,
    SPECS_BASE_KEY,
    SPECS_VER_KEY,
    VIEW_DASH,
    apply_demo_defaults,
    fill_sample_bits,
    goto_after_rerun,
    init_key,
    label_key,
    role_key,
    set_report,
    show_mock_report,
)

KIND_WAVE, KIND_DC, KIND_SIM = "파형", "DC 스윕", "시뮬 파형"
KINDS = [KIND_WAVE, KIND_DC, KIND_SIM]
NO_TIME = "(시간 열 없음: 시작·간격 입력)"
UNMAPPED = "(사용 안 함)"
FIRST_OUT = "(첫 OUT 채널)"
ENCODINGS = ["utf-8-sig", "cp949"]
DELIMITERS = [",", "\t", ";", " "]
DELIM_LABELS = {",": "쉼표 ,", "\t": "탭", ";": "세미콜론 ;", " ": "공백"}


@dataclass
class FileEntry:
    fid: str  # stable widget-key prefix
    name: str
    data: bytes
    origin: str  # "업로드" / "샘플"


@dataclass
class FileOutcome:
    entry: FileEntry
    kind: str
    options_json: str | None = None
    table: RawTable | None = None
    time_axis: TimeAxisSpec | None = None
    waveforms: list[Waveform] = field(default_factory=list)
    sweep: DCSweep | None = None
    error: str | None = None


def _fid(origin: str, name: str, taken: set[str]) -> str:
    base = "f" + hashlib.md5(f"{origin}:{name}".encode()).hexdigest()[:8]
    fid, i = base, 2
    while fid in taken:
        fid, i = f"{base}_{i}", i + 1
    taken.add(fid)
    return fid


def guess_kind(name: str) -> str:
    """Default data kind from the file name (user can change it)."""
    low = name.lower()
    if any(t in low for t in ("sim", "spice", "wrdata", "ngspice")):
        return KIND_SIM
    if low.endswith((".xlsx", ".xlsm")) or any(t in low for t in ("dmm", "sweep", "_dc", "iv")):
        return KIND_DC
    return KIND_WAVE


def _notices(notices: list[Notice]) -> None:
    seen: set[tuple[str, str]] = set()
    for n in notices:
        k = (n.code.value, n.message)
        if k in seen:
            continue
        seen.add(k)
        st.warning(f"! `{n.code.value}` {n.message}")


# ======================================================================= entry


def render_input_flow(visible: bool = True) -> None:
    """Render steps ①–⑦. Always rendered (even while the dashboard tab is shown) so every input keeps
    its state; ``visible`` only gates heavy non-widget previews (thumbnails, I–V, preview tables)."""
    ad, ad_msg = get_adapters()
    run_fn, pipe_msg = get_run_analysis()
    dark = is_dark()

    if ad is None:
        st.error(f"파서(core.adapters)를 불러올 수 없습니다 — {ad_msg}")
    if run_fn is None:
        st.error(f"분석 파이프라인(core.pipeline)을 불러올 수 없습니다 — {pipe_msg}")
    b1, _ = st.columns([1, 3])
    b1.button("데모 기본값 채우기", key="btn_demo_defaults", on_click=apply_demo_defaults,
              args=(rb.metric_option_of(),), width="stretch",
              help="역할 CH1 CLK · CH2 IN · CH3 OUT · CH4 IDD, 경로 Buffer: CH2 → CH3, 논리 VDD 1.8 V, "
                   "대역폭 500 MHz, 스펙 4개(tpd ≤ 8 ns · rise ≤ 4 ns · VOH ≥ 1.6 V · IDDQ ≤ 2.5 µA)를 채웁니다. "
                   "누를 때만 적용됩니다.")
    if st.session_state.pop("_demo_applied", False):
        st.success("데모 기본값을 채웠습니다 — 역할·경로·논리 VDD·대역폭·스펙 4개. 파일은 직접 고르세요.")

    # ① files
    st.subheader("① 측정 파일", anchor=False)
    entries = _collect_entries()
    kinds = _kind_selectors(entries)

    # ② ③ per file
    outcomes: list[FileOutcome] = []
    if entries and ad is not None:
        st.subheader("② 형식 확인 · ③ 단위·배율", anchor=False)
        n_dc = 0
        for e in entries:
            kind = kinds[e.fid]
            dc_name = "DMM" if n_dc == 0 else f"DMM{n_dc + 1}"
            n_dc += kind == KIND_DC
            outcomes.append(_file_panel(e, kind, dark, dc_name, visible))

    errors: list[str] = []
    waveforms: list[Waveform] = [w for o in outcomes if o.kind == KIND_WAVE for w in o.waveforms]
    ids = [w.channel_id for w in waveforms]
    dup = sorted({i for i in ids if ids.count(i) > 1})
    if dup:
        errors.append(f"채널 ID가 여러 파일에서 겹칩니다: {', '.join(dup)} — ③에서 채널 ID를 바꾸세요")
        seen: set[str] = set()
        waveforms = [w for w in waveforms if not (w.channel_id in seen or seen.add(w.channel_id))]
    sweeps = [o.sweep for o in outcomes if o.kind == KIND_DC and o.sweep is not None]
    sweep_names = [s.name for s in sweeps]
    if len(sweep_names) != len(set(sweep_names)):
        errors.append("DC 스윕 이름이 겹칩니다 — ③에서 이름을 바꾸세요")

    # ④ roles
    st.subheader("④ 채널 역할 · 조건", anchor=False)
    channel_map = _roles_section(waveforms)
    channel_ids = [c.channel_id for c in channel_map.channels]

    # ⑤ paths
    st.subheader("⑤ 경로(모듈) 정의", anchor=False)
    paths, errs = _paths_section(channel_ids)
    errors += errs

    # ⑥ optional inputs
    st.subheader("⑥ 선택 입력", anchor=False)
    specs, errs = _specs_section([p.name for p in paths], channel_ids + sweep_names)
    errors += errs
    sim_waveforms, sim_files, errs = _sim_section(outcomes, channel_map, ad, waveforms)
    errors += errs
    if sweeps:
        st.caption(f"DC 스윕 {len(sweeps)}개: {', '.join(sweep_names)} (①에서 종류 'DC 스윕'으로 지정한 파일)")
    sample_mode = any(e.origin == "샘플" for e in entries)
    expected, err = _expected_section(channel_ids, sample_mode)
    errors += [err] if err else []
    settings, err = _settings_section()
    errors += [err] if err else []

    # ⑦ run
    st.subheader("⑦ 분석 실행", anchor=False)
    for e in errors:
        st.error(e)
    clicked = st.button("분석 실행", key="btn_run", type="primary",
                        disabled=bool(errors) or ad is None or run_fn is None)
    if st.session_state.get(REPORT_KEY) is not None and not st.session_state.get(REPORT_IS_MOCK_KEY):
        st.caption("입력을 바꾼 뒤 다시 실행하면 대시보드가 새 결과로 바뀝니다. 입력값은 그대로 유지됩니다.")
    if clicked and settings is not None and run_fn is not None:
        _run(run_fn, outcomes, channel_map, paths, waveforms, sweeps, sim_waveforms, sim_files, specs, expected,
             settings)

    _dev_tools()


def _run(run_fn, outcomes, channel_map, paths, waveforms, sweeps, sim_waveforms, sim_files, specs, expected,
         settings) -> None:
    """Build the AnalysisRequest, call core.pipeline.run_analysis, store the report and open the dashboard."""
    t0 = time.perf_counter()
    request, req_errors = rb.build_request(
        channel_map=channel_map, paths=paths, waveforms=waveforms, dc_sweeps=sweeps, sim_waveforms=sim_waveforms,
        specs=specs, expected=expected, settings=settings,
        chip_id=st.session_state.get("in_chip_id"), temperature_c=st.session_state.get("in_temp_c"),
        measured_files=[o.entry.name for o in outcomes if o.kind in (KIND_WAVE, KIND_DC) and not o.error],
        sim_files=sim_files,
    )
    if request is None:
        for e in req_errors:
            st.error(e)
        return
    try:
        with st.spinner("분석 중…"):
            t1 = time.perf_counter()
            report = run_fn(request)
            run_s = time.perf_counter() - t1
    except Exception as e:  # noqa: BLE001 - shown to the user, never replaced by a mock
        st.error(f"분석 중 오류가 발생했습니다: {e}")
        return
    raw = {o.entry.name: o.table for o in outcomes if o.table is not None}
    set_report(report, is_mock=False, measured=request.measured, sim=request.sim, raw_tables=raw,
               timing={"run_s": run_s, "total_s": time.perf_counter() - t0})
    goto_after_rerun(VIEW_DASH)
    st.rerun()


def _dev_tools() -> None:
    with st.expander("개발용", expanded=False):
        st.caption("QA·개발용 도구입니다. 실제 분석 흐름에는 영향을 주지 않습니다.")
        st.button("목업 보고서로 대시보드 보기", key="btn_mock", on_click=show_mock_report,
                  help="tests/fixtures/mock_report.json을 파형 없이 대시보드에 표시합니다.")


# ======================================================================= ① files


def _collect_entries() -> list[FileEntry]:
    uploads = st.file_uploader("파일 업로드 (오실로 CSV · 엑셀 · 멀티미터 · SPICE 텍스트, 여러 개 가능)",
                               accept_multiple_files=True, key="in_uploads")
    samples = vm.list_sample_files()
    chosen: list[str] = []
    if samples:
        chosen = st.multiselect("또는 샘플 데이터 사용 (synth/data)", [p.name for p in samples], key="in_samples",
                                help="업로드 대신 합성 데이터를 고릅니다. 업로드와 같은 처리 경로를 탑니다.")
    else:
        st.caption("샘플 데이터 없음 — `.venv/Scripts/python -m synth.generate`로 synth/data/를 만들면 여기서 고를 수 있습니다.")
    taken: set[str] = set()
    entries = [FileEntry(_fid("u", u.name, taken), u.name, u.getvalue(), "업로드") for u in (uploads or [])]
    by_name = {p.name: p for p in samples}
    for name in chosen:
        p = by_name.get(name)
        if p is not None and p.is_file():
            entries.append(FileEntry(_fid("s", name, taken), name, p.read_bytes(), "샘플"))
    if not entries:
        st.info("파일을 올리거나 샘플 데이터를 고르세요. 파일마다 종류(파형 / DC 스윕 / 시뮬 파형)를 지정합니다.")
    return entries


def _kind_selectors(entries: list[FileEntry]) -> dict[str, str]:
    kinds: dict[str, str] = {}
    for e in entries:
        c1, c2 = st.columns([2, 3], vertical_alignment="center")
        c1.markdown(f"**{e.name}**  \n:gray[{e.origin} · {len(e.data):,} 바이트]")
        key = f"kind::{e.fid}"
        init_key(key, guess_kind(e.name))
        with c2:
            kinds[e.fid] = st.segmented_control(f"{e.name} 데이터 종류", KINDS, key=key, required=True,
                                                label_visibility="collapsed")
    return kinds


# ======================================================================= ② ③ per file


def _file_panel(e: FileEntry, kind: str, dark: bool, dc_name: str, visible: bool) -> FileOutcome:
    out = FileOutcome(entry=e, kind=kind)
    with st.expander(f"{e.name} · {kind}", expanded=True):
        try:
            auto = cached_preview(e.data, e.name, None)
        except Exception as ex:  # noqa: BLE001
            st.error(f"미리보기 실패: {ex}")
            out.error = str(ex)
            return out
        st.markdown("**② 형식 확인** — 자동 추정값을 기본으로, 필요하면 고치세요")
        options = _options_widgets(e.fid, auto)
        out.options_json = options.model_dump_json()
        try:
            preview = auto if options == auto.options else cached_preview(e.data, e.name, out.options_json)
            table = cached_read_table(e.data, e.name, out.options_json)
        except Exception as ex:  # noqa: BLE001
            st.error(f"표 읽기 실패: {ex}")
            out.error = str(ex)
            return out
        out.table = table
        if visible:
            _preview_tabs(e.fid, preview)
        _notices(preview.notices + table.notices)

        st.markdown("**③ 단위·배율**")
        if kind == KIND_DC:
            out.sweep = _dc_widgets(e, out.options_json, table, dc_name, dark, visible)
            return out
        out.time_axis = _time_axis_widgets(e.fid, table, preview)
        if out.time_axis is None:
            return out
        if kind == KIND_SIM:
            st.caption("시뮬 열 → 측정 채널 매핑은 ⑥ 선택 입력에서 합니다(측정 channel_id로 다시 키를 붙임).")
            return out
        out.waveforms = _conversion_section(e, out.options_json, table, out.time_axis, dark, visible)
    return out


def _options_widgets(fid: str, auto: TablePreview) -> ReadOptions:
    o = auto.options
    c1, c2, c3, c4 = st.columns(4)
    enc, delim, sheet = o.encoding, o.delimiter, o.sheet
    if auto.kind == FileKind.XLSX:
        if auto.sheets:
            init_key(f"{fid}::sheet", o.sheet or auto.sheets[0])
            sheet = c1.selectbox("시트", auto.sheets, key=f"{fid}::sheet")
    else:
        encs = list(dict.fromkeys([o.encoding or ENCODINGS[0], *ENCODINGS]))
        init_key(f"{fid}::enc", encs[0])
        enc = c1.selectbox("인코딩", encs, key=f"{fid}::enc")
        dels = list(dict.fromkeys([o.delimiter or ",", *DELIMITERS]))
        init_key(f"{fid}::delim", dels[0])
        delim = c2.selectbox("구분자", dels, key=f"{fid}::delim", format_func=lambda d: DELIM_LABELS.get(d, repr(d)))
    init_key(f"{fid}::nohdr", o.header_row is None)
    no_header = c3.checkbox("헤더 행 없음", key=f"{fid}::nohdr")
    init_key(f"{fid}::hdr", o.header_row if o.header_row is not None else 0)
    hdr = c3.number_input("헤더 행 (0부터)", min_value=0, step=1, key=f"{fid}::hdr", disabled=no_header)
    init_key(f"{fid}::start", o.data_start_row)
    start = c4.number_input("데이터 시작 행 (비우면 자동)", min_value=0, step=1, value=None, key=f"{fid}::start")
    return ReadOptions(encoding=enc, delimiter=delim, sheet=sheet,
                       header_row=None if no_header else int(hdr),
                       data_start_row=None if start is None else int(start))


def _preview_tabs(fid: str, p: TablePreview) -> None:
    t1, t2, t3 = st.tabs(["열·단위", "데이터 앞 10행", "원본 앞 30행 (헤더 처리 전)"], key=f"{fid}::pvtabs")
    with t1:
        st.dataframe(pd.DataFrame([{"열": c.name, "헤더": c.header, "기본 channel_id": c.base_name,
                                    "단위": c.unit_text or "", "SI": c.si_unit or "", "배율": c.scale,
                                    "숫자": c.numeric} for c in p.columns]),
                     key=f"{fid}::pv_cols", hide_index=True, width="stretch")
        if p.time_candidates:
            st.caption(f"시간 열 후보: {', '.join(p.time_candidates)}")
    with t2:
        names = [c.name for c in p.columns]
        rows = [r + [""] * (len(names) - len(r)) if len(r) < len(names) else r[:len(names)] for r in p.head_rows]
        st.dataframe(pd.DataFrame(rows, columns=names), key=f"{fid}::pv_head", width="stretch")
    with t3:
        width = max((len(r) for r in p.raw_rows), default=0)
        raw = [r + [""] * (width - len(r)) for r in p.raw_rows]
        st.dataframe(pd.DataFrame(raw, columns=[f"c{i}" for i in range(width)]), key=f"{fid}::pv_raw",
                     width="stretch", height=260)
        st.caption("왼쪽 번호 = 행 번호(0부터). 헤더 행·데이터 시작 행을 이 번호로 지정합니다.")


def _time_axis_widgets(fid: str, table: RawTable, preview: TablePreview) -> TimeAxisSpec | None:
    numeric = [c.name for c in table.columns if c.numeric]
    choices = numeric + [NO_TIME]
    default = next((c for c in preview.time_candidates if c in numeric), NO_TIME)
    key = f"{fid}::time"
    init_key(key, default)
    if st.session_state[key] not in choices:
        st.session_state[key] = default
    c1, c2, c3 = st.columns(3)
    col = c1.selectbox("시간 열", choices, key=key)
    if col != NO_TIME:
        info = table.column(col)
        skey = f"{fid}::tscale::{col}"
        init_key(skey, float(info.scale) if info is not None and info.si_unit == "s" else 1.0)
        unit = (info.unit_text if info is not None else None) or "없음"
        scale = c2.number_input(f"시간 배율 (원시 × 배율 = 초, 열 단위: {unit})", key=skey, format="%g",
                                min_value=0.0)
        if scale <= 0:
            st.error("시간 배율은 0보다 커야 합니다")
            return None
        return TimeAxisSpec(column=col, scale=scale)
    init_key(f"{fid}::t0_ns", 0.0)
    init_key(f"{fid}::dt_ns", 1.0)
    t0 = c2.number_input("시작 시각 (ns)", key=f"{fid}::t0_ns", format="%g")
    dt = c3.number_input("샘플 간격 (ns)", key=f"{fid}::dt_ns", format="%g", min_value=0.0)
    if dt <= 0:
        st.error("샘플 간격은 0보다 커야 합니다")
        return None
    return TimeAxisSpec(column=None, start_s=t0 * 1e-9, interval_s=dt * 1e-9)


def _conversion_section(e: FileEntry, options_json: str, table: RawTable, time_axis: TimeAxisSpec, dark: bool,
                        visible: bool) -> list[Waveform]:
    fid = e.fid
    rows = [
        {"사용": c.si_unit in (None, "V", "A"), "열": c.name, "채널 ID": c.base_name or c.name,
         "물리량": "A" if c.si_unit == "A" else "V", "원래 단위": c.unit_text or "",
         "단위 배율": float(c.scale), "프로브 배율": 1.0}
        for c in table.columns if c.numeric and c.name != time_axis.column
    ]
    if not rows:
        st.error("시간 열 외에 숫자 열이 없습니다")
        return []
    df = pd.DataFrame(rows)
    edited = st.data_editor(
        df, key=f"{fid}::conv::{time_axis.column}", hide_index=True, width="stretch", num_rows="fixed",
        disabled=["열", "원래 단위"],
        column_config={
            "사용": st.column_config.CheckboxColumn("사용", help="분석에 쓸 채널만 체크"),
            "채널 ID": st.column_config.TextColumn("채널 ID", help="정식 키. 기본값 = 열 이름에서 단위를 뺀 것", required=True),
            "물리량": st.column_config.SelectboxColumn("물리량", options=["V", "A"], required=True),
            "단위 배율": st.column_config.NumberColumn("단위 배율", help="원시 × 배율 = SI (mV → 0.001)", format="%g"),
            "프로브 배율": st.column_config.NumberColumn("프로브 배율", help="×10 프로브 → 10", format="%g"),
        },
    )
    convs: list[ChannelConversion] = []
    for r in edited.to_dict("records"):
        if not r.get("사용"):
            continue
        try:
            convs.append(ChannelConversion(column=str(r["열"]), channel_id=str(r["채널 ID"]).strip(),
                                           quantity=r["물리량"], scale=float(r["단위 배율"]),
                                           probe_factor=float(r["프로브 배율"])))
        except (ValidationError, TypeError, ValueError):
            st.error(f"열 {r.get('열')}: 채널 ID·물리량·배율을 확인하세요")
            return []
    if not convs:
        st.caption("사용할 채널을 체크하세요")
        return []
    cids = [c.channel_id for c in convs]
    if len(cids) != len(set(cids)):
        st.error("이 파일 안에서 채널 ID가 겹칩니다")
        return []
    try:
        res = cached_to_waveforms(e.data, e.name, options_json, time_axis.model_dump_json(), conversions_json(convs))
    except Exception as ex:  # noqa: BLE001
        st.error(f"파형 변환 실패: {ex}")
        return []
    _notices(res.notices)
    if res.waveforms and visible:
        w = res.waveforms[0]
        st.caption(f"{len(res.waveforms)}채널 · {w.n_samples:,}점 · 간격 {format_si(w.sample_interval_s, 's')} · "
                   f"{format_si(float(w.time_s[0]), 's')} ~ {format_si(float(w.time_s[-1]), 's')}")
        st.plotly_chart(F.thumbnails_figure(res.waveforms, dark=dark), key=f"{fid}::thumbs", width="stretch")
    return list(res.waveforms)


def _dc_widgets(e: FileEntry, options_json: str, table: RawTable, default_name: str, dark: bool,
               visible: bool) -> DCSweep | None:
    fid = e.fid
    numeric = [c for c in table.columns if c.numeric]
    if len(numeric) < 2:
        st.error("DC 스윕에는 숫자 열이 2개 이상 필요합니다")
        return None
    names = [c.name for c in numeric]
    xdef = next((c.name for c in numeric if c.si_unit == "V"), names[0])
    ydef = next((c.name for c in numeric if c.si_unit == "A" and c.name != xdef),
                next(n for n in names if n != xdef))
    c1, c2, c3, c4, c5 = st.columns(5)
    init_key(f"{fid}::dcx", xdef)
    init_key(f"{fid}::dcy", ydef)
    x = c1.selectbox("전압 열 (x)", names, key=f"{fid}::dcx")
    y = c2.selectbox("전류 열 (y)", names, key=f"{fid}::dcy")
    xi, yi = table.column(x), table.column(y)
    init_key(f"{fid}::dcxs::{x}", float(xi.scale) if xi else 1.0)
    init_key(f"{fid}::dcys::{y}", float(yi.scale) if yi else 1.0)
    xs = c3.number_input(f"x 배율 ({(xi.unit_text if xi else None) or '단위 없음'} → V)", key=f"{fid}::dcxs::{x}", format="%g")
    ys = c4.number_input(f"y 배율 ({(yi.unit_text if yi else None) or '단위 없음'} → A)", key=f"{fid}::dcys::{y}", format="%g")
    init_key(f"{fid}::dcname", default_name)
    name = c5.text_input("스윕 이름", key=f"{fid}::dcname", help="IDDQ 결과의 대상 이름으로 쓰입니다")
    if x == y:
        st.error("전압 열과 전류 열이 같습니다")
        return None
    try:
        res = cached_to_dc_sweep(e.data, e.name, options_json, x, y, float(xs), float(ys),
                                 (name or default_name).strip())
    except Exception as ex:  # noqa: BLE001
        st.error(f"DC 스윕 변환 실패: {ex}")
        return None
    _notices(res.notices)
    if res.sweep is None:
        st.error("유효한 스윕 점이 없습니다")
        return None
    if visible:
        fig = F.iv_figure([res.sweep], logic_vdd_v=st.session_state.get(LOGIC_VDD_KEY), dark=dark)
        fig.update_layout(height=260)
        st.plotly_chart(fig, key=f"{fid}::iv", width="stretch")
    return res.sweep


# ======================================================================= ④ roles


def _roles_section(waveforms: list[Waveform]) -> ChannelMap:
    rows: list[tuple[str, Role, str | None]] = []
    if not waveforms:
        st.caption("측정 파형 파일(종류 '파형')을 불러오면 채널이 여기에 나타납니다.")
    for w in waveforms:
        cid = w.channel_id
        role_mem, label_mem = st.session_state[ROLE_MEMORY_KEY], st.session_state[LABEL_MEMORY_KEY]
        init_key(role_key(cid), role_mem.get(cid, Role.IDD if w.quantity.value == "A" else Role.UNUSED))
        init_key(label_key(cid), label_mem.get(cid, ""))
        c1, c2, c3 = st.columns([2, 3, 3], vertical_alignment="center")
        c1.markdown(f"**{cid}**  \n:gray[{w.quantity.value} · {w.source_column or ''}]")
        role = c2.selectbox(f"{cid} 역할", list(Role), key=role_key(cid), format_func=lambda r: ROLE_LABELS[Role(r)],
                            label_visibility="collapsed")
        label = c3.text_input(f"{cid} 라벨", key=label_key(cid), placeholder="라벨 (선택, 예: WL0)",
                              label_visibility="collapsed")
        role_mem[cid], label_mem[cid] = Role(role), label or ""
        rows.append((cid, Role(role), label))
    c1, c2, c3, c4 = st.columns(4)
    init_key(LOGIC_VDD_KEY, 1.8)
    init_key(BANDWIDTH_KEY, None)
    init_key("in_chip_id", "")
    init_key("in_temp_c", None)
    c1.number_input("논리 VDD (V)", min_value=0.1, step=0.1, format="%.2f", key=LOGIC_VDD_KEY,
                    help="기능 샘플링 임계(VDD/2), IDDQ 보간 전압, 평균 전력 계산에 사용")
    c2.number_input("오실로 대역폭 (MHz)", min_value=0.0, step=50.0, value=None, key=BANDWIDTH_KEY,
                    help="입력하면 rise/fall 평균 < 2 × 0.35 / BW일 때 장비 한계 경고 (비우면 생략)")
    c3.text_input("칩 ID (선택)", key="in_chip_id")
    c4.number_input("온도 °C (선택)", value=None, step=1.0, key="in_temp_c")
    return rb.build_channel_map(rows)


# ======================================================================= ⑤ paths


def _paths_section(channel_ids: list[str]) -> tuple[list, list[str]]:
    base = st.session_state.get(PATHS_BASE_KEY) or []
    df = pd.DataFrame(base, columns=PATH_COLUMNS).astype(object)
    chan_col = (st.column_config.SelectboxColumn(options=channel_ids, required=True) if channel_ids
                else st.column_config.TextColumn())
    edited = st.data_editor(
        df, key=f"paths_editor::{st.session_state.get(PATHS_VER_KEY, 0)}", num_rows="dynamic", hide_index=True,
        width="stretch", placeholder="",
        column_config={
            "이름": st.column_config.TextColumn("이름", help="예: Buffer, Decoder", required=True),
            "입력 채널": chan_col, "출력 채널": chan_col,
            "극성": st.column_config.SelectboxColumn("극성", options=list(rb.POLARITY_OF), default="비반전",
                                                    help="비반전: 입력 상승 → 출력 상승"),
        },
    )
    st.caption("행 추가로 여러 경로를 정의합니다. tpLH·tpHL·tpd는 경로마다 계산됩니다.")
    _commit_editor(edited, PATHS_BASE_KEY, PATHS_VER_KEY, PATH_COLUMNS)
    rows = edited.to_dict("records")
    if channel_ids:
        return rb.paths_from_rows(rows, channel_ids)
    # no measured waveform yet (e.g. demo defaults pressed first): channels can't be checked, so no red error
    paths, errors = rb.paths_from_rows(rows, channel_ids, check_channels=False)
    if paths:
        st.info("측정 파일을 고르면 채널이 연결됩니다 — 경로의 입력·출력 채널은 그때 확인합니다.")
    return paths, errors


def _norm_rows(rows, columns: list[str]) -> list[dict]:
    def norm(v):
        if v is None or (isinstance(v, float) and v != v):
            return None
        return v.item() if hasattr(v, "item") else v
    return [{c: norm(r.get(c)) for c in columns} for r in rows]


def _commit_editor(edited: pd.DataFrame, base_key: str, ver_key: str, columns: list[str]) -> None:
    """Fold data_editor edits into the base rows under a fresh key.

    A dynamic data_editor's identity includes its data and column options, so its pending edits would be
    dropped when the channel list changes (DC file added, measured file swapped). Committing every edit to
    the non-widget base rows keeps them across those changes."""
    rows = _norm_rows(edited.to_dict("records"), columns)
    if rows != _norm_rows(st.session_state.get(base_key) or [], columns):
        st.session_state[base_key] = rows
        st.session_state[ver_key] = st.session_state.get(ver_key, 0) + 1
        st.rerun()


# ======================================================================= ⑥ optional


def _specs_section(path_names: list[str], target_ids: list[str]) -> tuple[list, list[str]]:
    st.markdown("**스펙 표** — 표시 단위(지표 이름의 [단위])로 입력, SI로 변환해 판정")
    base = st.session_state.get(SPECS_BASE_KEY) or []
    df = pd.DataFrame(base, columns=SPEC_COLUMNS)
    df[["지표", "경로", "채널"]] = df[["지표", "경로", "채널"]].astype(object)
    df[["최소", "최대"]] = df[["최소", "최대"]].apply(pd.to_numeric, errors="coerce").astype(float)
    edited = st.data_editor(
        df, key=f"specs_editor::{st.session_state.get(SPECS_VER_KEY, 0)}", num_rows="dynamic", hide_index=True,
        width="stretch", placeholder="",
        column_config={
            "지표": st.column_config.SelectboxColumn("지표", options=list(rb.metric_options()), required=True,
                                                    width="large"),
            "경로": st.column_config.SelectboxColumn("경로", options=[rb.ALL, *path_names], default=rb.ALL,
                                                    help="비우거나 (전체) = 모든 경로"),
            "채널": st.column_config.SelectboxColumn("채널", options=[rb.ALL, *target_ids], default=rb.ALL,
                                                    help="비우거나 (전체) = 모든 채널·스윕"),
            "최소": st.column_config.NumberColumn("최소", format="%g"),
            "최대": st.column_config.NumberColumn("최대", format="%g"),
        },
    )
    _commit_editor(edited, SPECS_BASE_KEY, SPECS_VER_KEY, SPEC_COLUMNS)
    specs, errors = rb.specs_from_rows(edited.to_dict("records"))
    if specs:
        st.caption("SI 변환 확인: " + " · ".join(
            f"{s.metric_id}{'(' + (s.path or s.channel_id) + ')' if (s.path or s.channel_id) else ''} {format_spec(s)}"
            for s in specs))
    return specs, errors


def _sim_section(outcomes: list[FileOutcome], channel_map: ChannelMap, ad,
                 measured: list[Waveform]) -> tuple[list[Waveform], list[str], list[str]]:
    st.markdown("**시뮬 비교** — 시뮬 열 → 측정 채널 매핑(자동 제안)")
    sims = [o for o in outcomes if o.kind == KIND_SIM and o.table is not None and o.time_axis is not None]
    if not sims:
        st.caption("시뮬 파일 없음 (선택) — ①에서 종류 '시뮬 파형'으로 지정하면 여기서 매핑합니다.")
        return [], [], []
    if len(sims) > 1:
        st.warning(f"시뮬 파일은 1개만 사용합니다 — '{sims[0].entry.name}' 사용")
    o = sims[0]
    table, time_axis = o.table, o.time_axis
    assert table is not None and time_axis is not None
    candidates = [c.channel_id for c in channel_map.channels if c.role != Role.UNUSED]
    if not candidates:
        st.caption("④에서 채널 역할을 먼저 지정하세요")
        return [], [o.entry.name], []
    try:
        suggested = ad.suggest_sim_mapping(table.columns, channel_map)
    except Exception as ex:  # noqa: BLE001
        st.warning(f"자동 제안 실패: {ex}")
        suggested = {}
    quantity_of = {w.channel_id: w.quantity.value for w in measured}
    cols = [c for c in table.columns if c.numeric and c.si_unit != "s" and c.name != time_axis.column]
    rows = []
    for c in cols:
        target = suggested.get(c.name)
        target = target if target in candidates else None
        rows.append({"시뮬 열": c.name, "측정 채널": target or UNMAPPED,
                     "물리량": quantity_of.get(target or "", "A" if c.si_unit == "A" else "V"),
                     "단위 배율": float(c.scale)})
    sig = hashlib.md5(channel_map.model_dump_json().encode()).hexdigest()[:8]
    edited = st.data_editor(
        pd.DataFrame(rows), key=f"{o.entry.fid}::simmap::{sig}", hide_index=True, width="stretch",
        num_rows="fixed", disabled=["시뮬 열"],
        column_config={
            "측정 채널": st.column_config.SelectboxColumn("측정 채널", options=[UNMAPPED, *candidates], required=True),
            "물리량": st.column_config.SelectboxColumn("물리량", options=["V", "A"], required=True),
            "단위 배율": st.column_config.NumberColumn("단위 배율", format="%g"),
        },
    )
    convs = []
    for r in edited.to_dict("records"):
        if r.get("측정 채널") in (None, UNMAPPED):
            continue
        convs.append(ChannelConversion(column=str(r["시뮬 열"]), channel_id=str(r["측정 채널"]),
                                       quantity=r["물리량"], scale=float(r["단위 배율"])))
    targets = [c.channel_id for c in convs]
    if len(targets) != len(set(targets)):
        return [], [o.entry.name], ["시뮬 매핑: 측정 채널 하나에 시뮬 열 하나만 연결하세요"]
    if not convs:
        st.caption("매핑된 시뮬 열이 없습니다")
        return [], [o.entry.name], []
    try:
        res = cached_to_waveforms(o.entry.data, o.entry.name, o.options_json or "", time_axis.model_dump_json(),
                                  conversions_json(convs))
    except Exception as ex:  # noqa: BLE001
        return [], [o.entry.name], [f"시뮬 파형 변환 실패: {ex}"]
    _notices(res.notices)
    st.caption("매핑: " + " · ".join(f"{c.column} → {c.channel_id}" for c in convs))
    return list(res.waveforms), [o.entry.name], []


def _expected_section(channel_ids: list[str], sample_mode: bool):
    st.markdown("**기대 비트열 (선택)**")
    c1, c2 = st.columns([3, 1])
    init_key(EXPECTED_BITS_KEY, "")
    sample_bits = vm.load_sample_bits() if sample_mode else None
    if sample_bits:
        c1.button("샘플 기대 비트열 넣기", key="btn_sample_bits", on_click=fill_sample_bits, args=(sample_bits,),
                  type="tertiary", help="synth/data/golden.json의 정상 비트열을 넣습니다(오류 파일을 골라도 같은 정상 비트열). "
                                        "누를 때만 적용됩니다.")
    text = c1.text_area("기대 출력 비트열 (공백·_·, 무시)", key=EXPECTED_BITS_KEY, height=80,
                        placeholder="예: 0000 0010 0000 1100 ...")
    opts = [FIRST_OUT, *channel_ids]
    ss = st.session_state
    mem = ss.get(EXPECTED_CH_MEMORY_KEY, FIRST_OUT)
    if ss.get(EXPECTED_CH_KEY) not in opts or (ss.get(EXPECTED_CH_FORCED_KEY) and mem in opts):
        # widget value missing or its channel temporarily gone (file swapped): fall back, remember the choice
        ss[EXPECTED_CH_KEY] = mem if mem in opts else FIRST_OUT
        ss[EXPECTED_CH_FORCED_KEY] = mem not in opts
    ch = c2.selectbox("비교할 출력 채널", opts, key=EXPECTED_CH_KEY)
    if ch != FIRST_OUT:  # an explicit pick ends the fallback
        ss[EXPECTED_CH_FORCED_KEY] = False
    if not ss.get(EXPECTED_CH_FORCED_KEY):
        ss[EXPECTED_CH_MEMORY_KEY] = ch
    pattern, err = rb.expected_from_text(text, None if ch == FIRST_OUT else ch)
    if pattern is not None:
        c1.caption(f"{len(pattern.bits)}비트 · CLK 상승마다 1비트 비교 (사이클 1부터)")
    return pattern, err


def _settings_section():
    st.markdown("**판정·보정 설정**")
    defaults = {"in_delay_ns": 0.0, "in_marginal_pct": 10.0, "in_sim_tol_pct": 20.0,
                "in_hyst_pct": 10.0, "in_min_pulse_ns": 0.0, "in_smooth": 0}
    for k, v in defaults.items():
        init_key(k, v)
    c1, c2, c3 = st.columns(3)
    c1.number_input("지연 보정 오프셋 (ns)", key="in_delay_ns", step=0.1, format="%g",
                    help="PCB·프로브 지연. 측정 tpLH/tpHL 평균에서 빼고 시뮬과 비교")
    c2.number_input("MARGINAL 임계 (%)", min_value=0.0, key="in_marginal_pct", step=1.0, format="%g",
                    help="마진 ≥ 임계 PASS, 0 ≤ 마진 < 임계 MARGINAL, < 0 FAIL")
    c3.number_input("시뮬 허용 편차 (±%)", min_value=0.0, key="in_sim_tol_pct", step=1.0, format="%g")
    with st.expander("고급: 엣지 검출"):
        a1, a2, a3 = st.columns(3)
        a1.number_input("히스테리시스 (% of swing)", min_value=0.5, max_value=49.5, key="in_hyst_pct", step=1.0,
                        format="%g", help="임계 = 50 % ± 이 값")
        a2.number_input("최소 펄스폭 (ns, 0 = 끔)", min_value=0.0, key="in_min_pulse_ns", step=0.5, format="%g")
        a3.number_input("평활화 점 수 (0 = 끔)", min_value=0, step=1, key="in_smooth")
    ss = st.session_state
    try:
        settings = rb.build_settings(
            logic_vdd_v=float(ss[LOGIC_VDD_KEY]), bandwidth_mhz=ss.get(BANDWIDTH_KEY),
            marginal_threshold_pct=float(ss["in_marginal_pct"]), sim_tolerance_pct=float(ss["in_sim_tol_pct"]),
            delay_offset_ns=float(ss["in_delay_ns"]), edge_hysteresis_pct=float(ss["in_hyst_pct"]),
            min_pulse_width_ns=float(ss["in_min_pulse_ns"]), smoothing_points=int(ss["in_smooth"]),
        )
    except (ValidationError, TypeError, ValueError) as e:
        return None, f"설정 값을 확인하세요: {e}"
    return settings, None
