"""Pure Plotly figure builders (no streamlit import).

Inputs are contract objects only: ``MeasurementSet`` (normalized waveforms / DC sweeps the UI holds)
and ``AnalysisReport`` / ``AnalysisResult`` (evidence for markers). The report has no waveform arrays,
so waveform charts take the ``MeasurementSet`` and draw markers from ``AnalysisResult.evidence``.
No analysis happens here — levels, edges and intervals all come from the evidence.
"""

from __future__ import annotations

import math
import textwrap
from collections.abc import Sequence
from dataclasses import dataclass, field

import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from core.models import (
    METRIC_INDEX,
    METRICS,
    VERDICT_LABELS,
    VERDICT_SYMBOLS,
    AnalysisReport,
    AnalysisResult,
    ChannelMap,
    DCSweep,
    FunctionalDetail,
    MeasurementSet,
    Role,
    Verdict,
    Waveform,
    format_metric_value,
    format_number,
    format_pct,
    format_si,
    format_spec,
)

from .theme import MUTED, SHADE_ALPHA, SPEC_LINE, VERDICT_COLORS, channel_color, hex_to_rgba, palette

_SURFACE_LIGHT = "#ffffff"
_SURFACE_DARK = "#0e1117"
_TIME_HOVER = "%{x:.6~s}s"
GL_MIN_POINTS = 2000  # above this, waveform figures use WebGL (Scattergl) for every trace


def _scatter_cls(n_points: int):
    """go.Scattergl for long records (all traces of the figure, so markers stay above the lines), else go.Scatter."""
    return go.Scattergl if n_points > GL_MIN_POINTS else go.Scatter


# ------------------------------------------------------------------ small helpers


def _wrap(text: str, width: int = 44) -> str:
    return "<br>".join(textwrap.wrap(text, width=width)) if text else ""


def _empty_figure(message: str, height: int = 220) -> go.Figure:
    fig = go.Figure()
    fig.add_annotation(text=message, showarrow=False, x=0.5, y=0.5, xref="paper", yref="paper",
                       font=dict(size=14, color=MUTED))
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False)
    fig.update_layout(height=height, margin=dict(l=10, r=10, t=10, b=10))
    return fig


def _quantity_axis(fig: go.Figure, quantity: str, row: int | None = None) -> None:
    kw = dict(row=row, col=1) if row is not None else {}
    if quantity == "A":
        fig.update_yaxes(tickformat="~s", ticksuffix="A", **kw)
    else:
        fig.update_yaxes(ticksuffix=" V", **kw)


def _value_hover(quantity: str) -> str:
    return "%{y:.4~s}A" if quantity == "A" else "%{y:.4f} V"


def _channel_index(channel_map: ChannelMap, channel_id: str) -> int:
    for i, c in enumerate(channel_map.channels):
        if c.channel_id == channel_id:
            return i
    return -1


def _first_clk_with_waveform(mset: MeasurementSet) -> str | None:
    """"The CLK" (contract 0): first CLK channel in ChannelMap order that has a waveform."""
    for cid in mset.channel_map.ids_with_role(Role.CLK):
        if mset.waveform(cid) is not None:
            return cid
    return None


def _surface(dark: bool) -> str:
    return _SURFACE_DARK if dark else _SURFACE_LIGHT


# ------------------------------------------------------------------ evidence -> overlays


@dataclass
class _Point:
    channel_id: str
    t: float
    v: float
    kind: str  # legend group name
    symbol: str
    hover: str


@dataclass
class _Overlay:
    points: list[_Point] = field(default_factory=list)
    shades: list[tuple[str, float, float, bool]] = field(default_factory=list)  # (channel, t0, t1, worst)
    hlines: list[tuple[str, float, str, bool]] = field(default_factory=list)  # (channel, y, label, is_spec)
    worst: list[_Point] = field(default_factory=list)


def _edge_hover(title: str, t: float, v: float | None, quantity: str = "V") -> str:
    vt = "—" if v is None else (format_si(v, "A") if quantity == "A" else f"{format_number(v)} V")
    return f"{title}<br>t = {format_si(t, 's', sig=6)}<br>기준 {vt}"


def evidence_overlay(result: AnalysisResult, mset: MeasurementSet) -> _Overlay:
    """Translate ``result.evidence`` into markers/shades per channel row (docs/metrics.md section 3)."""
    ov = _Overlay()
    mid = result.metric_id
    ev = result.evidence
    ref = ev.ref_levels_v
    m = METRICS[mid]
    ch = result.channel_id
    worst_t = ev.worst_time_s
    short = m.short_label

    def val_txt(v: float) -> str:
        return f"{short} = {format_metric_value(mid, v)}"

    if mid in ("rise_time", "fall_time") and ch:
        low, high = ref.get("low"), ref.get("high")
        v50 = (low + high) / 2 if low is not None and high is not None else None
        v10, v90 = ref.get("v10"), ref.get("v90")
        rise = mid == "rise_time"
        start_v, end_v = (v10, v90) if rise else (v90, v10)
        start_lbl, end_lbl = ("10 % 교차", "90 % 교차") if rise else ("90 % 교차", "10 % 교차")
        for e in ev.edges:
            is_worst = worst_t is not None and e.t_s == worst_t
            if v50 is not None:
                p = _Point(ch, e.t_s, v50, "50 % 교차", "circle",
                           _edge_hover(f"{ch} 50 % 교차", e.t_s, v50) + f"<br>{val_txt(e.value)}")
                ov.points.append(p)
                if is_worst:
                    ov.worst.append(p)
            if e.t_start_s is not None and start_v is not None:
                ov.points.append(_Point(ch, e.t_start_s, start_v, "10/90 % 점", "diamond",
                                        _edge_hover(f"{ch} {start_lbl}", e.t_start_s, start_v)))
            if e.t_end_s is not None and end_v is not None:
                ov.points.append(_Point(ch, e.t_end_s, end_v, "10/90 % 점", "diamond",
                                        _edge_hover(f"{ch} {end_lbl}", e.t_end_s, end_v)))
            if e.t_start_s is not None and e.t_end_s is not None:
                ov.shades.append((ch, e.t_start_s, e.t_end_s, is_worst))
        if v10 is not None:
            ov.hlines.append((ch, v10, "10 %", False))
        if v90 is not None:
            ov.hlines.append((ch, v90, "90 %", False))

    elif mid in ("tplh", "tphl", "tpd") and ch:
        path = next((p for p in mset.paths if p.name == result.path), None)
        in_ch = path.input_channel if path else None
        in_v50, out_v50 = ref.get("in_v50"), ref.get("out_v50")
        for e in ev.edges:
            is_worst = worst_t is not None and e.t_s == worst_t
            if out_v50 is not None:
                p = _Point(ch, e.t_s, out_v50, "출력 50 %", "circle",
                           _edge_hover(f"{ch} 출력 50 %", e.t_s, out_v50) + f"<br>{val_txt(e.value)}")
                ov.points.append(p)
                if is_worst:
                    ov.worst.append(p)
            if in_ch and e.t_start_s is not None and in_v50 is not None:
                ov.points.append(_Point(in_ch, e.t_start_s, in_v50, "입력 50 %", "circle-open",
                                        _edge_hover(f"{in_ch} 입력 50 %", e.t_start_s, in_v50)))
            if e.t_start_s is not None and e.t_end_s is not None:
                ov.shades.append((ch, e.t_start_s, e.t_end_s, is_worst))
                if in_ch:
                    ov.shades.append((in_ch, e.t_start_s, e.t_end_s, is_worst))

    elif mid in ("period", "duty_cycle", "frequency") and ch:
        v50 = ref.get("v50")
        for i, e in enumerate(ev.edges):
            if v50 is not None:
                ov.points.append(_Point(ch, e.t_s, v50, "CLK 상승 50 %", "square",
                                        _edge_hover(f"{ch} 상승 50 % (사이클 {i + 1})", e.t_s, v50)
                                        + f"<br>{val_txt(e.value)}"))
            # mean metrics: intervals tile the record, so shade only the first one
            if i == 0 and e.t_start_s is not None and e.t_end_s is not None:
                ov.shades.append((ch, e.t_start_s, e.t_end_s, False))
        if v50 is not None:
            ov.hlines.append((ch, v50, "50 %", False))

    elif mid in ("setup_slack", "hold_slack") and ch:
        clk = _first_clk_with_waveform(mset)
        clk_v50, data_v50 = ref.get("clk_v50"), ref.get("data_v50")
        setup = mid == "setup_slack"
        for e in ev.edges:
            is_worst = worst_t is not None and e.t_s == worst_t
            if data_v50 is not None:
                p = _Point(ch, e.t_s, data_v50, "데이터 전이 50 %", "circle",
                           _edge_hover(f"{ch} 데이터 전이 50 %", e.t_s, data_v50) + f"<br>{val_txt(e.value)}")
                ov.points.append(p)
                if is_worst:
                    ov.worst.append(p)
            t_clk = e.t_end_s if setup else e.t_start_s
            if clk and t_clk is not None and clk_v50 is not None:
                ov.points.append(_Point(clk, t_clk, clk_v50, "CLK 상승 50 %", "square",
                                        _edge_hover(f"{clk} CLK 상승 50 %", t_clk, clk_v50)))
            if e.t_start_s is not None and e.t_end_s is not None:
                ov.shades.append((ch, e.t_start_s, e.t_end_s, is_worst))
                if clk:
                    ov.shades.append((clk, e.t_start_s, e.t_end_s, is_worst))

    elif mid in ("voh", "vol") and ch and result.value is not None:
        ov.hlines.append((ch, result.value, f"{short} {format_metric_value(mid, result.value)}", False))
    elif mid == "idd_avg" and ch and result.value is not None:
        ov.hlines.append((ch, result.value, f"평균 {format_metric_value(mid, result.value)}", False))
    elif mid == "match_rate" and ch and "threshold_v" in ref:
        ov.hlines.append((ch, ref["threshold_v"], f"임계 {format_number(ref['threshold_v'])} V", False))

    # spec bound lines for level metrics drawn on the waveform itself
    if result.spec is not None and mid in ("voh", "vol", "idd_avg") and ch:
        for bound, lbl in ((result.spec.min, "스펙 하한"), (result.spec.max, "스펙 상한")):
            if bound is not None:
                ov.hlines.append((ch, bound, f"{lbl} {format_metric_value(mid, bound)}", True))
    return ov


def default_window(result: AnalysisResult | None, t_min: float, t_max: float) -> tuple[float, float] | None:
    """Zoom window around the worst edge (or the first edge); None = full record."""
    if result is None or not result.evidence.edges:
        return None
    ev = result.evidence
    target = next((e for e in ev.edges if ev.worst_time_s is not None and e.t_s == ev.worst_time_s), ev.edges[0])
    ts = [t for t in (target.t_start_s, target.t_s, target.t_end_s) if t is not None]
    t0, t1 = min(ts), max(ts)
    width = max(t1 - t0, 1e-12)
    pad = max(4 * width, 0.01 * (t_max - t_min))
    return (max(t_min, t0 - pad), min(t_max, t1 + pad))


# ------------------------------------------------------------------ waveforms


def waveform_figure(
    mset: MeasurementSet,
    highlight: AnalysisResult | None = None,
    *,
    channels: Sequence[str] | None = None,
    window: tuple[float, float] | None = None,
    zoom_to_highlight: bool = True,
    dark: bool = False,
    row_height: int = 150,
) -> go.Figure:
    """Multi-channel waveform chart on a shared time axis + evidence markers of ``highlight``.

    Rows = channels in ChannelMap order (UNUSED skipped) that have a waveform, or ``channels``.
    Markers: 50 % crossings, 10/90 % points, input/output 50 % for paths, interval shading,
    worst edge as a star in the verdict color. Hover on markers shows edge time + reference level.
    """
    cmap = mset.channel_map
    if channels is None:
        ids = [c.channel_id for c in cmap.channels if c.role != Role.UNUSED and mset.waveform(c.channel_id)]
    else:
        ids = [c for c in channels if mset.waveform(c) is not None]
    if not ids:
        return _empty_figure("표시할 파형이 없습니다")

    n = len(ids)
    titles = []
    for cid in ids:
        role = cmap.role_of(cid)
        titles.append(f"{cmap.display_name(cid)} · {role.value if role else '?'}")
    fig = make_subplots(rows=n, cols=1, shared_xaxes=True, vertical_spacing=min(0.06, 0.25 / n))
    row_of = {cid: i + 1 for i, cid in enumerate(ids)}
    surface = _surface(dark)
    Trace = _scatter_cls(max(mset.waveform(cid).n_samples for cid in ids))  # noqa: N806

    t_min = math.inf
    t_max = -math.inf
    for cid in ids:
        wf = mset.waveform(cid)
        assert wf is not None
        row = row_of[cid]
        color = channel_color(_channel_index(cmap, cid), dark)
        t_min, t_max = min(t_min, float(wf.time_s[0])), max(t_max, float(wf.time_s[-1]))
        fig.add_trace(
            Trace(
                x=wf.time_s, y=wf.values, mode="lines", name=titles[row - 1],
                line=dict(width=1.5, color=color),
                hovertemplate=f"{_TIME_HOVER}<br>{_value_hover(wf.quantity.value)}<extra>{titles[row - 1]}</extra>",
                legendgroup=cid,
            ),
            row=row, col=1,
        )
        fig.update_yaxes(title_text=titles[row - 1], row=row, col=1)
        _quantity_axis(fig, wf.quantity.value, row)

    if highlight is not None:
        ov = evidence_overlay(highlight, mset)
        vcolor = VERDICT_COLORS[highlight.verdict] if highlight.verdict is not None else MUTED
        for cid, t0, t1, worst in ov.shades:
            if cid not in row_of:
                continue
            base = channel_color(_channel_index(cmap, cid), dark)
            fig.add_vrect(x0=t0, x1=t1, row=row_of[cid], col=1, line_width=0, layer="below",
                          fillcolor=hex_to_rgba(vcolor if worst else base, 0.24 if worst else SHADE_ALPHA))
        for cid, y, label, is_spec in ov.hlines:
            if cid not in row_of:
                continue
            fig.add_hline(y=y, row=row_of[cid], col=1, line_width=1,
                          line_dash="dash" if is_spec else "dot", line_color=SPEC_LINE,
                          annotation_text=label, annotation_position="top left",
                          annotation_font_size=11)
        # marker traces grouped by kind (one legend entry each)
        kinds: dict[tuple[str, str], list[_Point]] = {}
        for p in ov.points:
            if p.channel_id in row_of:
                kinds.setdefault((p.kind, p.channel_id), []).append(p)
        seen_kind: set[str] = set()
        for (kind, cid), pts in kinds.items():
            color = channel_color(_channel_index(cmap, cid), dark)
            fig.add_trace(
                Trace(
                    x=[p.t for p in pts], y=[p.v for p in pts], mode="markers", name=kind,
                    legendgroup=f"mk-{kind}", showlegend=kind not in seen_kind,
                    marker=dict(size=9, symbol=pts[0].symbol, color=color, line=dict(width=2, color=surface)),
                    hovertext=[p.hover for p in pts], hovertemplate="%{hovertext}<extra></extra>",
                ),
                row=row_of[cid], col=1,
            )
            seen_kind.add(kind)
        for p in ov.worst:
            fig.add_trace(
                Trace(
                    x=[p.t], y=[p.v], mode="markers+text", name="최악 엣지", showlegend=True,
                    marker=dict(size=15, symbol="star", color=vcolor, line=dict(width=2, color=surface)),
                    text=[f"{VERDICT_SYMBOLS[highlight.verdict]} 최악"], textposition="middle left",
                    hovertext=[p.hover + "<br><b>최악 엣지</b>"], hovertemplate="%{hovertext}<extra></extra>",
                ),
                row=row_of[p.channel_id], col=1,
            )

    win = window
    if win is None and zoom_to_highlight and math.isfinite(t_min):
        win = default_window(highlight, t_min, t_max)
    fig.update_xaxes(tickformat="~s", ticksuffix="s", showspikes=True, spikemode="across", spikethickness=1)
    fig.update_xaxes(title_text="시간", row=n, col=1)
    if win is not None:
        fig.update_xaxes(range=list(win))
    fig.update_layout(
        height=row_height * n + 90, margin=dict(l=10, r=10, t=40, b=10), hovermode="closest",
        legend=dict(orientation="h", yanchor="bottom", y=1.01, x=0, font=dict(size=11)),
    )
    return fig


def thumbnails_figure(waveforms: Sequence[Waveform], *, dark: bool = False, row_height: int = 70) -> go.Figure:
    """Small per-channel previews (input flow step ③). Order = given order."""
    if not waveforms:
        return _empty_figure("변환된 파형이 없습니다", height=120)
    n = len(waveforms)
    Trace = _scatter_cls(max(w.n_samples for w in waveforms))  # noqa: N806
    fig = make_subplots(rows=n, cols=1, shared_xaxes=True, vertical_spacing=min(0.08, 0.3 / n))
    for i, wf in enumerate(waveforms):
        fig.add_trace(
            Trace(x=wf.time_s, y=wf.values, mode="lines", name=wf.channel_id,
                       line=dict(width=1, color=channel_color(i, dark)),
                       hovertemplate=f"{_TIME_HOVER}<br>{_value_hover(wf.quantity.value)}<extra>{wf.channel_id}</extra>"),
            row=i + 1, col=1,
        )
        fig.update_yaxes(title_text=wf.channel_id, row=i + 1, col=1)
        _quantity_axis(fig, wf.quantity.value, i + 1)
    fig.update_xaxes(tickformat="~s", ticksuffix="s")
    fig.update_layout(height=row_height * n + 50, margin=dict(l=10, r=10, t=10, b=10), showlegend=False)
    return fig


# ------------------------------------------------------------------ margin bars


def margin_bar_figure(report: AnalysisReport, *, include_no_spec: bool = False) -> go.Figure:
    """Per-metric margin bars grouped by path/channel; verdict color + symbol text on every bar."""
    cmap = report.channel_map
    entries = [r for r in report.results if r.verdict is not None or (include_no_spec and r.value is not None)]
    if not entries:
        return _empty_figure("판정할 스펙이 없습니다 — 스펙 표나 기대 비트열을 입력하세요", height=160)

    def group_of(r: AnalysisResult) -> str:
        return r.path or cmap.display_name(r.channel_id or "—")

    order: list[str] = []
    for r in entries:
        g = group_of(r)
        if g not in order:
            order.append(g)
    entries.sort(key=lambda r: (order.index(group_of(r)), METRIC_INDEX[r.metric_id]))

    T = report.settings.marginal_threshold_pct
    xs, texts, colors, custom = [], [], [], []
    for r in entries:
        m = METRICS[r.metric_id]
        sym = VERDICT_SYMBOLS[r.verdict]
        lab = VERDICT_LABELS[r.verdict]
        if r.margin_pct is not None:
            xs.append(r.margin_pct)
            texts.append(f"{sym} {lab} {format_pct(r.margin_pct)}")
        elif r.verdict is not None:
            xs.append(0.0)
            texts.append(f"{sym} {lab} · 마진 없음 ({format_metric_value(r.metric_id, r.value)})")
        else:
            xs.append(0.0)
            texts.append(f"{sym} {lab} · {format_metric_value(r.metric_id, r.value)}")
        colors.append(VERDICT_COLORS[r.verdict])
        custom.append([
            m.label, group_of(r), format_metric_value(r.metric_id, r.value),
            format_spec(r.spec) if r.spec else "없음",
            format_pct(r.margin_pct) if r.margin_pct is not None else "—",
            f"{sym} {lab}", _wrap(m.definition),
        ])

    y = [[group_of(r) for r in entries], [METRICS[r.metric_id].short_label for r in entries]]
    fig = go.Figure(go.Bar(
        x=xs, y=y, orientation="h", marker=dict(color=colors, line=dict(width=0)), width=0.55,
        text=texts, textposition="outside", cliponaxis=False, customdata=custom,
        hovertemplate=("<b>%{customdata[0]}</b> · %{customdata[1]}<br>값 %{customdata[2]} · 스펙 %{customdata[3]}"
                       "<br>마진 %{customdata[4]} · %{customdata[5]}<br><i>%{customdata[6]}</i><extra></extra>"),
        showlegend=False,
    ))
    lo = min([0.0] + xs)
    hi = max([T] + xs)
    fig.add_vline(x=0, line_width=1, line_color=MUTED)
    fig.add_vline(x=T, line_width=1, line_dash="dot", line_color=VERDICT_COLORS[Verdict.MARGINAL],
                  annotation_text=f"MARGINAL 임계 {T:g}%", annotation_position="top",
                  annotation_font_size=11)
    fig.update_xaxes(title_text="마진 (%) — 0 미만 FAIL · 0~임계 MARGINAL · 임계 이상 PASS", ticksuffix="%",
                     range=[lo - max(8.0, abs(lo) * 0.25), hi + max(30.0, hi * 0.6)], zeroline=False)
    fig.update_yaxes(autorange="reversed")
    fig.update_layout(height=40 * len(entries) + 110, margin=dict(l=10, r=10, t=30, b=10), bargap=0.35)
    return fig


# ------------------------------------------------------------------ timing distribution


def edge_distribution_figure(
    results: Sequence[AnalysisResult],
    channel_map: ChannelMap,
    *,
    metric_ids: Sequence[str] | None = None,
    dark: bool = False,
    max_cols: int = 4,
) -> go.Figure:
    """Per-edge distribution (box + strip) per metric — small multiples, each with its own y axis.

    Spec bound = dashed line, sim mean = diamond marker (if judged/compared).
    """
    pal = palette(dark)
    wanted = [r for r in results if r.evidence.edges and (metric_ids is None or r.metric_id in metric_ids)]
    if not wanted:
        return _empty_figure("엣지별 값이 있는 타이밍 지표가 없습니다")
    mids: list[str] = []
    for r in wanted:
        if r.metric_id not in mids:
            mids.append(r.metric_id)
    mids.sort(key=lambda x: METRIC_INDEX[x])
    k = len(mids)
    cols = min(k, max_cols)
    rows = math.ceil(k / cols)
    fig = make_subplots(rows=rows, cols=cols, horizontal_spacing=0.08, vertical_spacing=0.18,
                        subplot_titles=[f"{METRICS[m].short_label} ({METRICS[m].display_unit})" for m in mids])
    for idx, mid in enumerate(mids):
        row, col = idx // cols + 1, idx % cols + 1
        md = METRICS[mid]
        sc = md.display_scale
        for r in (x for x in wanted if x.metric_id == mid):
            target = r.path or channel_map.display_name(r.channel_id or "—")
            vals = [e.value * sc for e in r.evidence.edges]
            hov = [f"t = {format_si(e.t_s, 's', sig=6)}<br>{format_metric_value(mid, e.value)}" for e in r.evidence.edges]
            fig.add_trace(go.Box(
                y=vals, name=target, boxpoints="all", jitter=0.45, pointpos=0,
                marker=dict(size=6, color=pal.measured, opacity=0.85), line=dict(width=1.5, color=pal.measured),
                fillcolor=hex_to_rgba(pal.measured, 0.12), hovertext=hov, hoverinfo="text+name",
                showlegend=False,
            ), row=row, col=col)
            if r.sim_value is not None:
                fig.add_trace(go.Scatter(
                    x=[target], y=[r.sim_value * sc], mode="markers", name="시뮬 평균",
                    marker=dict(size=11, symbol="diamond", color=pal.sim, line=dict(width=2, color=_surface(dark))),
                    hovertemplate=f"시뮬 평균 {format_metric_value(mid, r.sim_value)}<extra></extra>",
                    showlegend=False,
                ), row=row, col=col)
            if r.spec is not None:
                for bound in (r.spec.min, r.spec.max):
                    if bound is not None:
                        fig.add_hline(y=bound * sc, row=row, col=col, line_dash="dash", line_width=1,
                                      line_color=SPEC_LINE, annotation_text=f"스펙 {format_spec(r.spec)}",
                                      annotation_font_size=10, annotation_position="top left")
    fig.update_layout(height=290 * rows + 40, margin=dict(l=10, r=10, t=40, b=10), showlegend=False)
    return fig


# ------------------------------------------------------------------ DC


def iv_figure(
    sweeps: Sequence[DCSweep],
    *,
    logic_vdd_v: float | None = None,
    iddq_results: Sequence[AnalysisResult] = (),
    log_y: bool = False,
    dark: bool = False,
) -> go.Figure:
    """I–V curve(s) from DC sweeps; IDDQ point at logic VDD (verdict color + symbol) and spec line."""
    if not sweeps:
        return _empty_figure("DC 스윕 데이터가 없습니다")
    fig = go.Figure()
    for i, s in enumerate(sweeps):
        y = np.abs(s.y) if log_y else s.y
        x = s.x
        if log_y:
            keep = y > 0
            x, y = x[keep], y[keep]
        yq = s.y_quantity.value
        fig.add_trace(go.Scatter(
            x=x, y=y, mode="lines+markers", name=s.name, line=dict(width=2, color=channel_color(i, dark)),
            marker=dict(size=8, line=dict(width=2, color=_surface(dark))),
            hovertemplate=f"%{{x:.4~s}}{s.x_quantity.value}<br>%{{y:.4~s}}{yq}<extra>{s.name}</extra>",
        ))
    for r in iddq_results:
        if r.value is None:
            continue
        vdd = r.evidence.params.get("vdd_v", logic_vdd_v)
        if vdd is None:
            continue
        sym = VERDICT_SYMBOLS[r.verdict]
        fig.add_trace(go.Scatter(
            x=[vdd], y=[abs(r.value) if log_y else r.value], mode="markers+text", name=f"IDDQ ({r.channel_id})",
            marker=dict(size=15, symbol="star", color=VERDICT_COLORS[r.verdict], line=dict(width=2, color=_surface(dark))),
            text=[f"{sym} IDDQ {format_metric_value('iddq', r.value)}"], textposition="middle left",
            hovertemplate=(f"IDDQ {format_metric_value('iddq', r.value)} @ {format_number(vdd)} V"
                           f"<br>{sym} {VERDICT_LABELS[r.verdict]}<extra></extra>"),
        ))
        if r.spec is not None and r.spec.max is not None:
            fig.add_hline(y=r.spec.max, line_dash="dash", line_width=1, line_color=SPEC_LINE,
                          annotation_text=f"IDDQ 스펙 {format_spec(r.spec)}", annotation_position="top left")
    if logic_vdd_v is not None:
        fig.add_vline(x=logic_vdd_v, line_dash="dot", line_width=1, line_color=MUTED,
                      annotation_text=f"논리 VDD {format_number(logic_vdd_v)} V", annotation_position="top")
    yq = sweeps[0].y_quantity.value
    fig.update_xaxes(title_text="전압", ticksuffix=f" {sweeps[0].x_quantity.value}")
    fig.update_yaxes(title_text="전류 (|I|, 로그)" if log_y else "전류", tickformat="~s", ticksuffix=yq,
                     type="log" if log_y else "linear")
    fig.update_layout(height=380, margin=dict(l=10, r=10, t=30, b=10), hovermode="closest",
                      legend=dict(orientation="h", yanchor="bottom", y=1.01, x=0))
    return fig


# ------------------------------------------------------------------ functional


def _lane_xy(bits: str) -> tuple[list[float], list[int]]:
    """Digital lane: cycle c occupies [c-0.5, c+0.5]; step 'hv'."""
    xs = [c + 0.5 for c in range(len(bits))] + [len(bits) + 0.5]
    ys = [int(b) for b in bits] + ([int(bits[-1])] if bits else [])
    return xs, ys


def functional_figure(detail: FunctionalDetail, *, dark: bool = False) -> go.Figure:
    """0/1 lanes (expected, measured) + sampled voltage vs threshold; mismatching cycles in red ✕."""
    pal = palette(dark)
    fail = VERDICT_COLORS[Verdict.FAIL]
    has_exp = detail.expected_bits is not None
    lanes = (["기대"] if has_exp else []) + ["측정", "샘플 전압"]
    n_rows = len(lanes)
    fig = make_subplots(rows=n_rows, cols=1, shared_xaxes=True, vertical_spacing=0.07,
                        row_heights=[0.22] * (n_rows - 1) + [0.56 if n_rows == 3 else 0.6])
    bad = detail.mismatch_cycles
    row = 1
    if has_exp:
        xs, ys = _lane_xy(detail.expected_bits or "")
        fig.add_trace(go.Scatter(x=xs, y=ys, mode="lines", line=dict(shape="hv", width=2, color=MUTED),
                                 fill="tozeroy", fillcolor=hex_to_rgba(MUTED, 0.12), name="기대 비트",
                                 hoverinfo="skip"), row=row, col=1)
        fig.update_yaxes(title_text="기대", row=row, col=1)
        row += 1
    xs, ys = _lane_xy(detail.measured_bits)
    fig.add_trace(go.Scatter(x=xs, y=ys, mode="lines", line=dict(shape="hv", width=2, color=pal.measured),
                             fill="tozeroy", fillcolor=hex_to_rgba(pal.measured, 0.12), name="측정 비트",
                             hoverinfo="skip"), row=row, col=1)
    fig.update_yaxes(title_text="측정", row=row, col=1)
    meas_row = row
    for r in range(1, meas_row + 1):
        fig.update_yaxes(range=[-0.25, 1.35], tickvals=[0, 1], row=r, col=1)

    # sampled voltage
    cycles = list(range(1, len(detail.sample_times_s) + 1))
    hov = [f"사이클 {c}<br>t = {format_si(t, 's', sig=6)}<br>{format_number(v)} V → {b}"
           for c, t, v, b in zip(cycles, detail.sample_times_s, detail.sample_values_v, detail.measured_bits)]
    fig.add_trace(go.Scatter(x=cycles, y=detail.sample_values_v, mode="markers", name="샘플 전압",
                             marker=dict(size=7, color=pal.measured), hovertext=hov,
                             hovertemplate="%{hovertext}<extra></extra>"), row=n_rows, col=1)
    fig.add_hline(y=detail.threshold_v, row=n_rows, col=1, line_dash="dash", line_width=1, line_color=SPEC_LINE,
                  annotation_text=f"임계 {format_number(detail.threshold_v)} V (논리 VDD/2)",
                  annotation_position="top left", annotation_font_size=11)
    fig.update_yaxes(title_text="샘플 (V)", row=n_rows, col=1)

    if bad:
        exp = detail.expected_bits or ""
        mx, my, mh = [], [], []
        for c in bad:
            for r in range(1, n_rows + 1):
                fig.add_vrect(x0=c - 0.5, x1=c + 0.5, row=r, col=1, fillcolor=hex_to_rgba(fail, 0.18),
                              line_width=0, layer="below")
            mb = detail.measured_bits[c - 1] if c <= len(detail.measured_bits) else "?"
            eb = exp[c - 1] if c <= len(exp) else "?"
            mx.append(c)
            my.append(int(mb) if mb in "01" else 0)
            mh.append(f"✕ 사이클 {c}: 기대 {eb}, 측정 {mb}")
        fig.add_trace(go.Scatter(x=mx, y=my, mode="markers+text", name="불일치",
                                 marker=dict(size=13, symbol="x", color=fail, line=dict(width=1, color=fail)),
                                 text=[f"✕ {c}" for c in mx], textposition="top center",
                                 textfont=dict(color=fail), hovertext=mh,
                                 hovertemplate="%{hovertext}<extra></extra>"), row=meas_row, col=1)
        sv = [detail.sample_values_v[c - 1] for c in bad if c <= len(detail.sample_values_v)]
        fig.add_trace(go.Scatter(x=[c for c in bad if c <= len(detail.sample_values_v)], y=sv, mode="markers",
                                 name="불일치 샘플", showlegend=False,
                                 marker=dict(size=12, symbol="x", color=fail)), row=n_rows, col=1)

    n = max(len(detail.measured_bits), len(detail.expected_bits or ""))
    fig.update_xaxes(range=[0.5, n + 0.5], dtick=1 if n <= 40 else None, row=n_rows, col=1, title_text="사이클 (1부터)")
    fig.update_layout(height=150 * (n_rows - 1) + 280, margin=dict(l=10, r=10, t=40, b=10), hovermode="closest",
                      legend=dict(orientation="h", yanchor="bottom", y=1.01, x=0))
    return fig


# ------------------------------------------------------------------ sim comparison


def deviation_figure(report: AnalysisReport) -> go.Figure:
    """Deviation bars vs sim (%), tolerance band ±tol; bars over tolerance get warning color + '!'."""
    pal = palette(False)
    cmap = report.channel_map
    tol = report.settings.sim_tolerance_pct
    entries = [r for r in report.results if r.sim_value is not None]
    if not entries:
        return _empty_figure("시뮬 비교 결과가 없습니다 — 시뮬 파일을 첨부하세요", height=160)
    warn = VERDICT_COLORS[Verdict.MARGINAL]
    xs, texts, colors, custom = [], [], [], []
    for r in entries:
        d = r.deviation_pct
        if d is None:
            xs.append(0.0)
            texts.append("– 편차 계산 안 함 (시뮬값 0)")
            colors.append(MUTED)
        elif abs(d) > tol:
            xs.append(d)
            texts.append(f"! {format_pct(d, signed=True)} 허용 초과")
            colors.append(warn)
        else:
            xs.append(d)
            texts.append(format_pct(d, signed=True))
            colors.append(pal.neutral_bar)
        custom.append([METRICS[r.metric_id].label, r.path or cmap.display_name(r.channel_id or "—"),
                       format_metric_value(r.metric_id, r.representative()),
                       format_metric_value(r.metric_id, r.sim_value)])
    y = [[r.path or cmap.display_name(r.channel_id or "—") for r in entries],
         [METRICS[r.metric_id].short_label for r in entries]]
    fig = go.Figure()
    fig.add_vrect(x0=-tol, x1=tol, fillcolor=pal.band, line_width=0, layer="below",
                  annotation_text=f"허용 ±{tol:g}%", annotation_position="top left", annotation_font_size=11)
    fig.add_trace(go.Bar(
        x=xs, y=y, orientation="h", marker=dict(color=colors, line=dict(width=0)), width=0.55,
        text=texts, textposition="outside", cliponaxis=False, customdata=custom, showlegend=False,
        hovertemplate=("<b>%{customdata[0]}</b> · %{customdata[1]}<br>측정 평균 %{customdata[2]} · 시뮬 %{customdata[3]}"
                       "<br>편차 %{x:+.1f}%<extra></extra>"),
    ))
    fig.add_vline(x=0, line_width=1, line_color=MUTED)
    lo, hi = min([0.0, -tol] + xs), max([0.0, tol] + xs)
    span = hi - lo
    fig.update_xaxes(title_text="시뮬 대비 편차 (%) = (측정 평균 − 오프셋 − 시뮬) / |시뮬|", ticksuffix="%",
                     range=[lo - 0.15 * span, hi + 0.45 * span], zeroline=False)
    fig.update_yaxes(autorange="reversed")
    fig.update_layout(height=38 * len(entries) + 110, margin=dict(l=10, r=10, t=30, b=10), bargap=0.35)
    return fig


def sim_overlay_figure(
    measured: MeasurementSet,
    sim: MeasurementSet,
    *,
    clk_t0_s: float | None,
    sim_clk_t0_s: float | None,
    channels: Sequence[str] | None = None,
    window: tuple[float, float] | None = None,
    dark: bool = False,
    row_height: int = 150,
) -> go.Figure:
    """Measured vs sim overlay per channel; each set's time minus its first CLK rising edge (D6, display only)."""
    pal = palette(dark)
    cmap = measured.channel_map
    if channels is None:
        ids = [c.channel_id for c in cmap.channels
               if c.role != Role.UNUSED and measured.waveform(c.channel_id) and sim.waveform(c.channel_id)]
    else:
        ids = [c for c in channels if measured.waveform(c) and sim.waveform(c)]
    if not ids:
        return _empty_figure("측정·시뮬 양쪽에 있는 채널이 없습니다")
    m0 = clk_t0_s or 0.0
    s0 = sim_clk_t0_s or 0.0
    n = len(ids)
    Trace = _scatter_cls(max(max(measured.waveform(c).n_samples, sim.waveform(c).n_samples) for c in ids))  # noqa: N806
    fig = make_subplots(rows=n, cols=1, shared_xaxes=True, vertical_spacing=min(0.06, 0.25 / n))
    for i, cid in enumerate(ids):
        mw, sw = measured.waveform(cid), sim.waveform(cid)
        assert mw is not None and sw is not None
        role = cmap.role_of(cid)
        name = f"{cmap.display_name(cid)} · {role.value if role else '?'}"
        fig.add_trace(Trace(x=mw.time_s - m0, y=mw.values, mode="lines", name="측정",
                            legendgroup="measured", showlegend=i == 0, line=dict(width=1.5, color=pal.measured),
                            hovertemplate=f"측정 {name}<br>{_TIME_HOVER}<br>{_value_hover(mw.quantity.value)}<extra></extra>"),
                      row=i + 1, col=1)
        fig.add_trace(Trace(x=sw.time_s - s0, y=sw.values, mode="lines", name="시뮬",
                            legendgroup="sim", showlegend=i == 0,
                            line=dict(width=1.5, color=pal.sim, dash="dash"),
                            hovertemplate=f"시뮬 {name}<br>{_TIME_HOVER}<br>{_value_hover(sw.quantity.value)}<extra></extra>"),
                      row=i + 1, col=1)
        fig.update_yaxes(title_text=name, row=i + 1, col=1)
        _quantity_axis(fig, mw.quantity.value, i + 1)
    title = "시간 (첫 CLK 상승 기준)" if clk_t0_s is not None and sim_clk_t0_s is not None else "시간 (정렬 기준 없음)"
    fig.update_xaxes(tickformat="~s", ticksuffix="s", showspikes=True, spikemode="across", spikethickness=1)
    fig.update_xaxes(title_text=title, row=n, col=1)
    if window is not None:
        fig.update_xaxes(range=list(window))
    fig.update_layout(height=row_height * n + 90, margin=dict(l=10, r=10, t=40, b=10), hovermode="closest",
                      legend=dict(orientation="h", yanchor="bottom", y=1.01, x=0))
    return fig
