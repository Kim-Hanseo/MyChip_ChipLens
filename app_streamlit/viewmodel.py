"""Pure text/table helpers for the dashboard (no streamlit / plotly import).

Everything here reads only ``AnalysisReport`` (+ optional normalized inputs) and formats it with the
contract helpers (``format_metric_value``, ``format_pct``, ``format_spec``). No analysis logic.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Sequence
from pathlib import Path as FsPath

import pandas as pd

from core.models import (
    METRICS,
    ROLE_LABELS,
    VERDICT_LABELS,
    VERDICT_SYMBOLS,
    AnalysisReport,
    AnalysisResult,
    AnalysisSettings,
    ChannelMap,
    DeviationItem,
    FunctionalCard,
    FunctionalDetail,
    MeasurementSet,
    SimDeviationCard,
    Spec,
    Verdict,
    VerdictCard,
    WorstMarginCard,
    format_metric_value,
    format_number,
    format_pct,
    format_si,
    format_spec,
)

from .theme import verdict_badge_text, verdict_md

REPO_ROOT = FsPath(__file__).resolve().parents[1]
MOCK_REPORT_PATH = REPO_ROOT / "tests" / "fixtures" / "mock_report.json"
SAMPLE_DIR = REPO_ROOT / "synth" / "data"
SAMPLE_SUFFIXES = (".csv", ".xlsx", ".xlsm", ".txt", ".dat")

DELAY_OFFSET_METRICS = ("tplh", "tphl")


# ---------------------------------------------------------------- loading


def load_mock_report(path: FsPath = MOCK_REPORT_PATH) -> AnalysisReport:
    """Mock report used before the pipeline exists (contract section 6)."""
    return AnalysisReport.model_validate_json(path.read_text(encoding="utf-8"))


def load_sample_bits(sample_dir: FsPath = SAMPLE_DIR) -> str | None:
    """Expected bits of the synthetic data (golden.json 'bits' — the normal pattern, also for the error file)."""
    path = sample_dir / "golden.json"
    try:
        bits = json.loads(path.read_text(encoding="utf-8")).get("bits")
    except (OSError, ValueError):
        return None
    return bits if isinstance(bits, str) and bits else None


def list_sample_files(sample_dir: FsPath = SAMPLE_DIR) -> list[FsPath]:
    """Sample data files under synth/data (sorted; golden.json and other non-tables excluded)."""
    if not sample_dir.is_dir():
        return []
    return sorted(p for p in sample_dir.iterdir() if p.is_file() and p.suffix.lower() in SAMPLE_SUFFIXES)


# ---------------------------------------------------------------- naming


def target_name(path: str | None, channel_id: str | None, channel_map: ChannelMap) -> str:
    """Display target: path name if set, else channel label/id (contract 4.5)."""
    if path:
        return path
    if channel_id:
        return channel_map.display_name(channel_id)
    return "—"


def result_target(r: AnalysisResult | DeviationItem | WorstMarginCard, channel_map: ChannelMap) -> str:
    return target_name(r.path, r.channel_id, channel_map)


def result_key(r: AnalysisResult) -> str:
    """Stable string key '(metric|path|channel)' for widgets."""
    return f"{r.metric_id}|{r.path or ''}|{r.channel_id or ''}"


def result_title(r: AnalysisResult, channel_map: ChannelMap) -> str:
    """'tpd · Buffer', 'rise · CH3'."""
    return f"{METRICS[r.metric_id].short_label} · {result_target(r, channel_map)}"


def metric_help(metric_id: str) -> str:
    """Tooltip text: label + definition (METRICS)."""
    m = METRICS[metric_id]
    return f"**{m.label}** ({m.display_unit}) — {m.definition}"


def verdict_text(r: AnalysisResult) -> str:
    return verdict_badge_text(r.verdict)


# ---------------------------------------------------------------- header


def header_lines(report: AnalysisReport) -> dict[str, str]:
    """Chip id, condition line, file list, settings line for the dashboard header."""
    s = report.session
    cond: list[str] = []
    vdd = s.vdd_v if s.vdd_v is not None else report.settings.logic_vdd_v
    cond.append(f"VDD {format_number(vdd)} V")
    if s.temperature_c is not None:
        cond.append(f"{s.temperature_c:g} °C")
    if s.frequency_hz is not None:
        cond.append(f"{format_si(s.frequency_hz, 'Hz')}")
    if s.instrument:
        cond.append(s.instrument)
    files = list(s.files)
    sim_files = list(report.sim_session.files) if report.sim_session else []
    st = report.settings
    set_parts = [f"논리 VDD {format_number(st.logic_vdd_v)} V"]
    set_parts.append(f"대역폭 {format_si(st.bandwidth_hz, 'Hz')}" if st.bandwidth_hz else "대역폭 미입력")
    set_parts.append(f"MARGINAL 임계 {st.marginal_threshold_pct:g}%")
    set_parts.append(f"시뮬 허용 ±{st.sim_tolerance_pct:g}%")
    if st.delay_offset_s:
        set_parts.append(f"지연 보정 {format_si(st.delay_offset_s, 's')}")
    return {
        "chip": s.chip_id or "칩 ID 미입력",
        "conditions": " · ".join(cond),
        "files": ", ".join(files) if files else "—",
        "sim_files": ", ".join(sim_files) if sim_files else "",
        "settings": " · ".join(set_parts),
    }


# ---------------------------------------------------------------- cards


def overall_verdict(card: VerdictCard) -> Verdict | None:
    """Worst verdict present (FAIL > MARGINAL > PASS); None if nothing was judged."""
    if card.fail_count:
        return Verdict.FAIL
    if card.marginal_count:
        return Verdict.MARGINAL
    if card.pass_count:
        return Verdict.PASS
    return None


def verdict_counts_text(card: VerdictCard) -> str:
    """'✓ PASS 4 · ! MARGINAL 1 · ✕ FAIL 0' (plain text)."""
    return " · ".join(
        f"{VERDICT_SYMBOLS[v]} {VERDICT_LABELS[v]} {n}"
        for v, n in ((Verdict.PASS, card.pass_count), (Verdict.MARGINAL, card.marginal_count),
                     (Verdict.FAIL, card.fail_count))
    )


def verdict_counts_md(card: VerdictCard) -> str:
    """Colored markdown version of ``verdict_counts_text`` (color + symbol + label)."""
    return " · ".join(
        verdict_md(v, f"{VERDICT_SYMBOLS[v]} {VERDICT_LABELS[v]} {n}")
        for v, n in ((Verdict.PASS, card.pass_count), (Verdict.MARGINAL, card.marginal_count),
                     (Verdict.FAIL, card.fail_count))
    )


def worst_margin_texts(card: WorstMarginCard | None, channel_map: ChannelMap) -> tuple[str, str]:
    """('! VOH 1.75 V', 'CH3 · 스펙 ≥ 1.60 V · 마진 9.4%')."""
    if card is None:
        return ("– 마진 없음", "스펙이 있는 지표가 없습니다")
    m = METRICS[card.metric_id]
    head = f"{VERDICT_SYMBOLS[card.verdict]} {m.short_label} {format_metric_value(card.metric_id, card.value)}"
    detail = (f"{target_name(card.path, card.channel_id, channel_map)} · 스펙 {format_spec(card.spec)}"
              f" · 마진 {format_pct(card.margin_pct)}")
    return head, detail


def deviation_item_text(item: DeviationItem, channel_map: ChannelMap) -> str:
    """'rise(CH3) +50.0%'."""
    m = METRICS[item.metric_id]
    return f"{m.short_label}({target_name(item.path, item.channel_id, channel_map)}) {format_pct(item.deviation_pct, signed=True)}"


def sim_deviation_texts(card: SimDeviationCard | None, channel_map: ChannelMap) -> tuple[str, str]:
    """('rise(CH3) +50.0% · tpLH(Buffer) +33.3%', '허용 ±20.0% 초과 경고 4건')."""
    if card is None:
        return ("– 시뮬 없음", "시뮬 파일을 첨부하면 지표별 편차를 비교합니다")
    head = " · ".join(deviation_item_text(i, channel_map) for i in card.top) or "편차 계산 불가"
    if card.warning_count:
        detail = f"! 허용 ±{card.tolerance_pct:.1f}% 초과 경고 {card.warning_count}건"
    else:
        detail = f"✓ 모두 허용 ±{card.tolerance_pct:.1f}% 이내"
    return head, detail


def functional_texts(card: FunctionalCard | None, detail: FunctionalDetail | None) -> tuple[str, str, Verdict | None]:
    """(headline, detail, verdict) for card 4."""
    if card is None:
        if detail is not None:
            return ("– 기대 비트열 없음", f"측정 비트 {len(detail.measured_bits)}개 (기능 탭에서 확인)", None)
        return ("– 기대 비트열 없음", "기대 비트열을 입력하면 일치율을 판정합니다", None)
    head = (f"{VERDICT_SYMBOLS[card.verdict]} {format_number(card.match_rate_pct)}% "
            f"({card.matched_cycles}/{card.compared_cycles} 사이클)")
    tail = f"첫 불일치: {card.first_mismatch}번째 사이클" if card.first_mismatch else "불일치 없음"
    return head, tail, card.verdict


# ---------------------------------------------------------------- tables


def _fmt(metric_id: str, v: float | None) -> str:
    return format_metric_value(metric_id, v)


def measured_for_deviation(r: AnalysisResult, settings: AnalysisSettings) -> float | None:
    """Measured representative after delay offset (tplh/tphl only) — display of judge's D6 input."""
    rep = r.representative()
    if rep is None:
        return None
    return rep - settings.delay_offset_s if r.metric_id in DELAY_OFFSET_METRICS else rep


def results_table(
    results: Sequence[AnalysisResult],
    channel_map: ChannelMap,
    *,
    metric_ids: Iterable[str] | None = None,
) -> pd.DataFrame:
    """One row per result: target, metric, worst value, stats, spec, verdict, margin, sim, warnings."""
    keep = set(metric_ids) if metric_ids is not None else None
    rows = []
    for r in results:
        if keep is not None and r.metric_id not in keep:
            continue
        m = METRICS[r.metric_id]
        st = r.stats
        rows.append({
            "대상": result_target(r, channel_map),
            "지표": m.label,
            "값 (판정)": _fmt(r.metric_id, r.value),
            "평균": _fmt(r.metric_id, st.mean) if st else "",
            "최소": _fmt(r.metric_id, st.min) if st else "",
            "최대": _fmt(r.metric_id, st.max) if st else "",
            "σ": _fmt(r.metric_id, st.std) if st else "",
            "n": str(st.n) if st else "",
            "스펙": format_spec(r.spec) if r.spec else "",
            "판정": verdict_badge_text(r.verdict),
            "마진": format_pct(r.margin_pct) if r.margin_pct is not None else "",
            "시뮬": _fmt(r.metric_id, r.sim_value) if r.sim_value is not None else "",
            "편차": format_pct(r.deviation_pct, signed=True) if r.deviation_pct is not None else "",
            "경고": ", ".join(w.value for w in r.warnings),
            "정의": m.definition,
        })
    return pd.DataFrame(rows)


def deviation_table(report: AnalysisReport) -> pd.DataFrame:
    """Sim comparison rows (only results that have a sim value)."""
    rows = []
    for r in report.results:
        if r.sim_value is None:
            continue
        m = METRICS[r.metric_id]
        meas = measured_for_deviation(r, report.settings)
        exceeded = r.deviation_pct is not None and abs(r.deviation_pct) > report.settings.sim_tolerance_pct
        rows.append({
            "대상": result_target(r, report.channel_map),
            "지표": m.label,
            "측정 (평균)": _fmt(r.metric_id, meas),
            "시뮬": _fmt(r.metric_id, r.sim_value),
            "편차": format_pct(r.deviation_pct, signed=True) if r.deviation_pct is not None else "계산 안 함",
            "상태": ("! 허용 초과" if exceeded else ("✓ 허용 이내" if r.deviation_pct is not None else "–")),
        })
    return pd.DataFrame(rows)


def evidence_table(r: AnalysisResult) -> pd.DataFrame:
    """Per-edge evidence rows (marker time, value, interval)."""
    rows = []
    worst = r.evidence.worst_time_s
    for i, e in enumerate(r.evidence.edges, start=1):
        rows.append({
            "#": i,
            "시각 t": format_si(e.t_s, "s", sig=6),
            "값": _fmt(r.metric_id, e.value),
            "구간 시작": format_si(e.t_start_s, "s", sig=6) if e.t_start_s is not None else "",
            "구간 끝": format_si(e.t_end_s, "s", sig=6) if e.t_end_s is not None else "",
            "최악": "★" if worst is not None and e.t_s == worst else "",
        })
    return pd.DataFrame(rows)


def spec_rows(specs: Sequence[Spec]) -> pd.DataFrame:
    rows = []
    for s in specs:
        m = METRICS[s.metric_id]
        rows.append({
            "지표": f"{m.label} ({s.metric_id})",
            "경로": s.path or "(전체)",
            "채널": s.channel_id or "(전체)",
            "스펙": format_spec(s),
            "SI 최소": s.min,
            "SI 최대": s.max,
        })
    return pd.DataFrame(rows)


def channel_rows(channel_map: ChannelMap, mset: MeasurementSet | None = None) -> pd.DataFrame:
    """Mapping + unit info per channel (raw-data tab)."""
    rows = []
    for c in channel_map.channels:
        wf = mset.waveform(c.channel_id) if mset is not None else None
        rows.append({
            "channel_id": c.channel_id,
            "역할": ROLE_LABELS[c.role],
            "라벨": c.label or "",
            "원본 열": wf.source_column if wf else "",
            "원래 단위": (wf.source_unit or "") if wf else "",
            "프로브 배율": wf.probe_factor if wf else None,
            "물리량 (SI)": wf.quantity.value if wf else "",
            "샘플 수": wf.n_samples if wf else None,
            "샘플 간격": format_si(wf.sample_interval_s, "s") if wf else "",
        })
    return pd.DataFrame(rows)


def notice_rows(report: AnalysisReport) -> list[str]:
    """'! [SIM_DEVIATION] CH3 rise 시뮬 대비 +50.0% ...' lines (sim-source notices are tagged)."""
    out = []
    for n in report.warnings:
        src = " (시뮬)" if n.source.value == "sim" else ""
        out.append(f"! `{n.code.value}`{src} {n.message}")
    return out


# ---------------------------------------------------------------- functional


def bit_groups(bits: str, size: int = 8) -> list[str]:
    return [bits[i:i + size] for i in range(0, len(bits), size)]


def bits_markdown(detail: FunctionalDetail, which: str = "measured", group: int = 8) -> str:
    """Bit string in groups of 8; mismatching bits as bold red with a ✕-free inline highlight."""
    bits = detail.measured_bits if which == "measured" else (detail.expected_bits or "")
    bad = set(detail.mismatch_cycles)
    parts: list[str] = []
    for gi in range(0, len(bits), group):
        chunk = []
        for j, b in enumerate(bits[gi:gi + group]):
            cycle = gi + j + 1
            chunk.append(f":red[**{b}**]" if cycle in bad else b)
        parts.append("".join(chunk))
    return " ".join(parts) if parts else "—"


# ---------------------------------------------------------------- waveform selection


def highlight_candidates(report: AnalysisReport) -> list[AnalysisResult]:
    """Results that can be highlighted on the waveform tab (have edges or a level to draw)."""
    drawable = {"voh", "vol", "idd_avg", "frequency", "match_rate"}
    return [r for r in report.results if r.evidence.edges or r.metric_id in drawable]


def default_highlight(report: AnalysisReport) -> AnalysisResult | None:
    """Worst-margin result if it is drawable with edges, else the first spec'd result with edges."""
    cands = highlight_candidates(report)
    if not cands:
        return None
    wm = report.cards.worst_margin
    if wm is not None:
        for r in cands:
            if (r.metric_id, r.path, r.channel_id) == (wm.metric_id, wm.path, wm.channel_id) and r.evidence.edges:
                return r
    for r in cands:
        if r.verdict is not None and r.evidence.edges:
            return r
    return next((r for r in cands if r.evidence.edges), cands[0])


# ---------------------------------------------------------------- sim overlay window


def sim_overlay_window(report: AnalysisReport) -> tuple[float, float] | None:
    """Default window of the sim overlay, on the CLK-aligned time axis (t − clk_t0_s).

    Five clock periods starting half a period before the cycle that holds the first path edge
    (earliest input crossing among tpLH/tpHL/tpd evidence), so IN and OUT really switch inside the
    window even when the pattern starts with a run of zeros. Without path edges: [−0.5P, 4.5P].
    None when there is no period result (caller shows the full record)."""
    period = next((r.value for r in report.results if r.metric_id == "period" and r.value), None)
    if not period:
        return None
    k = 0
    t0 = report.clk_t0_s
    starts = [e.t_start_s for r in report.results if r.metric_id in ("tplh", "tphl", "tpd")
              for e in r.evidence.edges if e.t_start_s is not None]
    if starts and t0 is not None:
        k = max(0, int((min(starts) - t0) // period))
    return ((k - 0.5) * period, (k + 4.5) * period)
