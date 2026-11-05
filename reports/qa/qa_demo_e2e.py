"""QA: plan 4.2 demo scenario 1-8 end to end through the core PUBLIC API, in the UI's call order.

file bytes -> preview_file -> read_table -> to_waveforms / to_dc_sweep (+ suggest_sim_mapping for sim)
-> MeasurementSet / AnalysisRequest -> core.pipeline.run_analysis.

Expected values come only from plan 4.2 / 4.4 / Appendix A and decisions D9 / D11 (tolerances),
never from golden.json or from implementation tests. Expected bits are rebuilt from the D11 PRBS7 text.

Run: .venv/Scripts/python reports/qa/qa_demo_e2e.py
Writes: reports/qa/demo_e2e_table.md, reports/qa/golden_table.md, reports/qa/out/*.json
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from core.adapters import preview_file, read_table, suggest_sim_mapping, to_dc_sweep, to_waveforms  # noqa: E402
from core.models import (  # noqa: E402
    METRICS,
    AnalysisRequest,
    AnalysisSettings,
    ChannelConversion,
    ChannelInfo,
    ChannelMap,
    ExpectedPattern,
    MeasurementSet,
    Path as SigPath,
    Role,
    SessionInfo,
    Source,
    Spec,
    TimeAxisSpec,
    WarningCode,
)
from core.pipeline import run_analysis  # noqa: E402

DATA = ROOT / "synth" / "data"
OUT = Path(__file__).parent / "out"
OUT.mkdir(exist_ok=True)

ROWS: list[tuple[str, str, str, str, bool]] = []  # (step, check, expected, actual, ok)
GOLD: list[tuple[str, str, str, str, bool]] = []


def row(step: str, what: str, expected, actual, ok: bool, table=ROWS) -> bool:
    table.append((step, what, str(expected), str(actual), bool(ok)))
    return bool(ok)


def prbs7_bits(n: int, seed: int = 0x7F) -> str:
    state, out = seed, []
    for _ in range(n):
        newbit = ((state >> 6) ^ (state >> 5)) & 1
        state = ((state << 1) | newbit) & 0x7F
        out.append(str(newbit))
    return "".join(out)


# ---------------------------------------------------------------- UI-equivalent adapter steps

def load_waveform_file(name: str):
    """UI ①②③ for kind '파형': auto preview -> read_table(options) -> time axis + conversions -> to_waveforms."""
    data = (DATA / name).read_bytes()
    pv = preview_file(data, name)
    table = read_table(data, name, pv.options)
    numeric = [c.name for c in table.columns if c.numeric]
    tcol = next((c for c in pv.time_candidates if c in numeric), None)
    info = table.column(tcol)
    taxis = TimeAxisSpec(column=tcol, scale=float(info.scale) if info.si_unit == "s" else 1.0)
    convs = [ChannelConversion(column=c.name, channel_id=c.base_name or c.name,
                               quantity="A" if c.si_unit == "A" else "V", scale=float(c.scale), probe_factor=1.0)
             for c in table.columns if c.numeric and c.name != tcol and c.si_unit in (None, "V", "A")]
    res = to_waveforms(table, taxis, convs)
    return pv, table, taxis, res


def load_dc_file(name: str, sweep_name: str = "DMM"):
    """UI for kind 'DC 스윕': default x = first V column, y = first A column, scales from header units."""
    data = (DATA / name).read_bytes()
    pv = preview_file(data, name)
    table = read_table(data, name, pv.options)
    numeric = [c for c in table.columns if c.numeric]
    x = next((c for c in numeric if c.si_unit == "V"), numeric[0])
    y = next((c for c in numeric if c.si_unit == "A" and c.name != x.name), None)
    res = to_dc_sweep(table, x.name, y.name, x_scale=float(x.scale), y_scale=float(y.scale), name=sweep_name)
    return pv, table, x, y, res


def load_sim_file(name: str, channel_map: ChannelMap, measured_quantity: dict[str, str]):
    """UI for kind '시뮬 파형': preview -> read_table -> suggest_sim_mapping -> to_waveforms re-keyed (D3)."""
    data = (DATA / name).read_bytes()
    pv = preview_file(data, name)
    table = read_table(data, name, pv.options)
    numeric = [c.name for c in table.columns if c.numeric]
    tcol = next((c for c in pv.time_candidates if c in numeric), None)
    info = table.column(tcol)
    taxis = TimeAxisSpec(column=tcol, scale=float(info.scale) if info.si_unit == "s" else 1.0)
    sugg = suggest_sim_mapping(table.columns, channel_map)
    candidates = [c.channel_id for c in channel_map.channels if c.role != Role.UNUSED]
    convs = []
    for c in table.columns:
        if not c.numeric or c.si_unit == "s" or c.name == tcol:
            continue
        target = sugg.get(c.name)
        if target in candidates:
            convs.append(ChannelConversion(column=c.name, channel_id=target,
                                           quantity=measured_quantity.get(target, "V"), scale=float(c.scale)))
    res = to_waveforms(table, taxis, convs)
    return pv, table, sugg, res


def specs_from_display(rows) -> list[Spec]:
    """UI spec editor: display units -> SI via METRICS[id].display_scale."""
    out = []
    for mid, lo, hi in rows:
        sc = METRICS[mid].display_scale
        out.append(Spec(metric_id=mid, min=None if lo is None else lo / sc, max=None if hi is None else hi / sc))
    return out


def res_of(report, metric_id, path=None, channel_id=None):
    for r in report.results:
        if r.metric_id == metric_id and (path is None or r.path == path) and (channel_id is None or r.channel_id == channel_id):
            return r
    return None


def fmt(v, scale=1.0, nd=3):
    return "None" if v is None else f"{v * scale:.{nd}f}"


def main() -> int:
    ok_all = True
    # ================= step 1: upload synthetic scope CSV (4 ch)
    pv, table, taxis, wres = load_waveform_file("synth_scope.csv")
    wfs = wres.waveforms
    ok = row("1", "preview_file(synth_scope.csv): header row auto-detected, time column", "header row 4, time 'Time(s)'",
             f"header_row={pv.options.header_row}, time_candidates={pv.time_candidates[:2]}",
             pv.options.header_row == 4 and pv.time_candidates[:1] == ["Time(s)"])
    ok &= row("1", "columns/units from headers", "Time(s)[s], CH1-3 [V], CH4 [A]",
              ", ".join(f"{c.name}[{c.si_unit}]" for c in table.columns),
              [(c.base_name, c.si_unit) for c in table.columns] ==
              [("Time", "s"), ("CH1", "V"), ("CH2", "V"), ("CH3", "V"), ("CH4", "A")])
    ok &= row("1", "to_waveforms: 4 channels x 20,000 pts, dt 0.2 ns, no notices", "CH1..CH4, 20000 each, 0.2 ns, []",
              f"{[w.channel_id for w in wfs]}, {[w.n_samples for w in wfs]}, {wfs[0].sample_interval_s * 1e9:.4f} ns, "
              f"{[n.code.value for n in wres.notices]}",
              [w.channel_id for w in wfs] == ["CH1", "CH2", "CH3", "CH4"] and all(w.n_samples == 20000 for w in wfs)
              and abs(wfs[0].sample_interval_s - 0.2e-9) < 1e-15 and not wres.notices)
    ok &= row("1", "CH4 quantity = A (IDD)", "A", wfs[3].quantity.value, wfs[3].quantity.value == "A")
    ok_all &= ok

    # ================= step 2: roles, path, logic VDD, bandwidth
    cmap = ChannelMap(channels=[ChannelInfo(channel_id="CH1", role=Role.CLK), ChannelInfo(channel_id="CH2", role=Role.IN),
                                ChannelInfo(channel_id="CH3", role=Role.OUT), ChannelInfo(channel_id="CH4", role=Role.IDD)])
    paths = [SigPath(name="Buffer", input_channel="CH2", output_channel="CH3")]
    settings = AnalysisSettings(logic_vdd_v=1.8, bandwidth_hz=500e6)
    ok_all &= row("2", "ChannelMap/Path/AnalysisSettings accepted", "CLK/IN/OUT/IDD, Buffer CH2->CH3, 1.8 V, 500 MHz",
                  f"{[c.role.value for c in cmap.channels]}, {paths[0].name} {paths[0].input_channel}->{paths[0].output_channel},"
                  f" {settings.logic_vdd_v} V, {settings.bandwidth_hz / 1e6:g} MHz", True)

    # ================= step 3: specs (display units -> SI)
    specs = specs_from_display([("tpd", None, 8.0), ("rise_time", None, 4.0), ("voh", 1.6, None), ("iddq", None, 2.5)])
    ok_all &= row("3", "spec SI conversion", "tpd max 8e-9 s, rise max 4e-9 s, voh min 1.6 V, iddq max 2.5e-6 A",
                  ", ".join(f"{s.metric_id} {s.min if s.min is not None else ''}{'..' if s.min is not None else 'max '}"
                            f"{s.max if s.max is not None else ''}" for s in specs),
                  abs(specs[0].max - 8e-9) < 1e-21 and abs(specs[1].max - 4e-9) < 1e-21 and specs[2].min == 1.6
                  and abs(specs[3].max - 2.5e-6) < 1e-18)

    # ================= step 4: attach sim CSV (wrdata, repeated time columns)
    qty = {w.channel_id: w.quantity.value for w in wfs}
    spv, stable, sugg, sres = load_sim_file("synth_sim.csv", cmap, qty)
    ok = row("4", "preview_file(synth_sim.csv): whitespace delimiter, repeated time cols dropped",
             "delimiter ' ', columns time, v(clk), v(in), v(out)",
             f"delimiter={spv.options.delimiter!r}, columns={[c.name for c in stable.columns]}, "
             f"notices={[n.code.value for n in stable.notices]}",
             spv.options.delimiter == " " and [c.name for c in stable.columns] == ["time", "v(clk)", "v(in)", "v(out)"])
    ok &= row("4", "suggest_sim_mapping", "v(clk)->CH1, v(in)->CH2, v(out)->CH3", sugg,
              sugg == {"v(clk)": "CH1", "v(in)": "CH2", "v(out)": "CH3"})
    ok &= row("4", "sim to_waveforms re-keyed", "CH1, CH2, CH3 x 40001 pts, 0.1 ns",
              f"{[w.channel_id for w in sres.waveforms]} x {[w.n_samples for w in sres.waveforms]}, "
              f"{sres.waveforms[0].sample_interval_s * 1e9:.4f} ns",
              [w.channel_id for w in sres.waveforms] == ["CH1", "CH2", "CH3"]
              and all(w.n_samples == 40001 for w in sres.waveforms))
    ok_all &= ok
    sim_set = MeasurementSet(session=SessionInfo(source=Source.SIM, files=["synth_sim.csv"]), channel_map=cmap,
                             paths=paths, waveforms=sres.waveforms)

    def measured_set(waves, sweeps=(), files=("synth_scope.csv",)):
        return MeasurementSet(session=SessionInfo(source=Source.MEASURED, vdd_v=1.8, files=list(files)),
                              channel_map=cmap, paths=paths, waveforms=list(waves), dc_sweeps=list(sweeps))

    # ================= step 5: run analysis
    req5 = AnalysisRequest(measured=measured_set(wfs), sim=sim_set, specs=specs, settings=settings)
    rep5 = run_analysis(req5)
    (OUT / "step5_report.json").write_text(rep5.model_dump_json(indent=1), encoding="utf-8")
    tpd, rise, voh = res_of(rep5, "tpd", "Buffer"), res_of(rep5, "rise_time", channel_id="CH3"), res_of(rep5, "voh", channel_id="CH3")
    tplh, tphl, fall = res_of(rep5, "tplh", "Buffer"), res_of(rep5, "tphl", "Buffer"), res_of(rep5, "fall_time", channel_id="CH3")
    ok = row("5", "tpd verdict / margin (plan: PASS 25 %, D11: PASS ≈25 % ±2 %p)", "PASS, 23–27 %",
             f"{tpd.verdict}, {fmt(tpd.margin_pct, 1, 2)} % (worst {fmt(tpd.value, 1e9)} ns)",
             tpd.verdict == "PASS" and 23 <= tpd.margin_pct <= 27)
    ok &= row("5", "rise verdict / margin (plan: PASS 25 %)", "PASS, 23–27 %",
              f"{rise.verdict}, {fmt(rise.margin_pct, 1, 2)} % (worst {fmt(rise.value, 1e9)} ns)",
              rise.verdict == "PASS" and 23 <= rise.margin_pct <= 27)
    ok &= row("5", "VOH verdict / margin (plan: MARGINAL 9.4 %)", "MARGINAL, 7.4–11.4 % (9.4 ±2 %p)",
              f"{voh.verdict}, {fmt(voh.margin_pct, 1, 2)} % (VOH {fmt(voh.value, 1, 4)} V)",
              voh.verdict == "MARGINAL" and 7.4 <= voh.margin_pct <= 11.4)
    ok &= row("5", "tpLH sim deviation (plan: +33 % warning)", "+33.3 ±2 %p, SIM_DEVIATION",
              f"{fmt(tplh.deviation_pct, 1, 2)} %, {[w.value for w in tplh.warnings]}",
              abs(tplh.deviation_pct - 33.33) <= 2 and WarningCode.SIM_DEVIATION in tplh.warnings)
    ok &= row("5", "rise sim deviation (plan: +50 % warning)", "+50.0 ±2 %p, SIM_DEVIATION",
              f"{fmt(rise.deviation_pct, 1, 2)} %, {[w.value for w in rise.warnings]}",
              abs(rise.deviation_pct - 50.0) <= 2 and WarningCode.SIM_DEVIATION in rise.warnings)
    ok &= row("5", "tpHL / fall sim deviation (App. A: +31 / +39 %, warnings)", "+31.0 / +38.9 ±2 %p, both SIM_DEVIATION",
              f"{fmt(tphl.deviation_pct, 1, 2)} / {fmt(fall.deviation_pct, 1, 2)} %",
              abs(tphl.deviation_pct - 30.95) <= 2 and abs(fall.deviation_pct - 38.89) <= 2
              and WarningCode.SIM_DEVIATION in tphl.warnings and WarningCode.SIM_DEVIATION in fall.warnings)
    sim_warned = sorted(r.metric_id for r in rep5.results if WarningCode.SIM_DEVIATION in r.warnings)
    ok &= row("5", "SIM_DEVIATION set (App. A: timing 4 warnings)", "fall_time, rise_time, tphl, tplh", sim_warned,
              sim_warned == ["fall_time", "rise_time", "tphl", "tplh"])
    sd = rep5.cards.sim_deviation
    top = [(i.metric_id, round(i.deviation_pct, 1)) for i in sd.top] if sd else None
    ok &= row("5", "card 3 sim max deviation (D9: rise +50, tplh +33, 4 warnings)", "[rise_time +50.0, tplh +33.3], 4",
              f"{top}, {sd.warning_count if sd else None}",
              sd is not None and [i.metric_id for i in sd.top] == ["rise_time", "tplh"] and sd.warning_count == 4)
    bw5 = [r.metric_id for r in rep5.results if WarningCode.BANDWIDTH_LIMIT in r.warnings]
    ok &= row("5", "no bandwidth warning at 500 MHz (App. A)", "[]", bw5, bw5 == [])
    iddq5 = res_of(rep5, "iddq")
    ok &= row("5", "IDDQ spec has no target yet (DMM not uploaded)", "no iddq result", iddq5, iddq5 is None)
    vc = rep5.cards.verdicts
    ok &= row("5", "card 1 at step 5 (tpd, rise PASS; voh MARGINAL)", "PASS 2 · MARGINAL 1 · FAIL 0",
              f"PASS {vc.pass_count} · MARGINAL {vc.marginal_count} · FAIL {vc.fail_count}",
              (vc.pass_count, vc.marginal_count, vc.fail_count) == (2, 1, 0))
    wm = rep5.cards.worst_margin
    ok &= row("5", "card 2 worst margin = VOH 9.4 %", "voh, 9.4 %", f"{wm.metric_id}, {wm.margin_pct:.2f} %",
              wm.metric_id == "voh" and abs(wm.margin_pct - 9.375) <= 2)
    common = any("전 경로 공통 지연 증가" in s for s in rep5.summary_lines)
    ok &= row("5", "summary rule 3 (all timing slower by similar ratio)", "line '전 경로 공통 지연 증가 …' present",
              common, common)
    ok_all &= ok

    # ================= step 6: DMM xlsx
    dpv, dtable, xcol, ycol, dres = load_dc_file("synth_dmm.xlsx")
    sweep = dres.sweep
    ok = row("6", "preview_file(synth_dmm.xlsx): sheet DC측정, header row 2 (merged title row 0, blank row 1)",
             "sheet DC측정, header_row 2", f"sheet={dpv.options.sheet}, sheets={dpv.sheets}, header_row={dpv.options.header_row}",
             (dpv.options.sheet in (None, "DC측정")) and dpv.sheets[:1] == ["DC측정"] and dpv.options.header_row == 2)
    ok &= row("6", "Korean header unit extraction", "전압(V) -> V x1, 전류(µA) -> A x1e-6",
              f"{xcol.header} -> {xcol.si_unit} x{xcol.scale:g}, {ycol.header} -> {ycol.si_unit} x{ycol.scale:g}",
              xcol.header == "전압(V)" and xcol.si_unit == "V" and ycol.header == "전류(µA)" and ycol.si_unit == "A"
              and abs(ycol.scale - 1e-6) < 1e-18)
    ok &= row("6", "to_dc_sweep: 11 points V 1.0..2.0, I(1.8 V) = 1.5 µA (I–V curve data)", "11 pts, 1.0..2.0 V, 1.5e-6 A",
              f"{len(sweep.x)} pts, {sweep.x[0]:g}..{sweep.x[-1]:g} V, I(1.8)={sweep.y[8]:.4e} A, notices={[n.code.value for n in dres.notices]}",
              len(sweep.x) == 11 and abs(sweep.x[0] - 1.0) < 1e-12 and abs(sweep.x[-1] - 2.0) < 1e-12
              and abs(sweep.y[8] - 1.5e-6) < 1e-15)
    req6 = AnalysisRequest(measured=measured_set(wfs, [sweep], ("synth_scope.csv", "synth_dmm.xlsx")), sim=sim_set,
                           specs=specs, settings=settings)
    rep6 = run_analysis(req6)
    (OUT / "step6_report.json").write_text(rep6.model_dump_json(indent=1), encoding="utf-8")
    iddq = res_of(rep6, "iddq")
    ok &= row("6", "IDDQ verdict / margin (plan: PASS 40 %)", "PASS, 38–42 % (IDDQ 1.5 µA ±0.5 %)",
              f"{iddq.verdict}, {fmt(iddq.margin_pct, 1, 2)} % (IDDQ {fmt(iddq.value, 1e6, 4)} µA, channel {iddq.channel_id})",
              iddq.verdict == "PASS" and 38 <= iddq.margin_pct <= 42 and abs(iddq.value - 1.5e-6) <= 0.005 * 1.5e-6)
    ok_all &= ok

    # ================= step 7: expected bits -> 100 %; error file -> first mismatch 37
    bits = prbs7_bits(40)
    exp = ExpectedPattern(bits=" ".join(bits[i:i + 4] for i in range(0, 40, 4)))  # with spaces like a user would type
    req7 = AnalysisRequest(measured=measured_set(wfs, [sweep], ("synth_scope.csv", "synth_dmm.xlsx")), sim=sim_set,
                           specs=specs, expected=exp, settings=settings)
    rep7 = run_analysis(req7)
    (OUT / "step7_report.json").write_text(rep7.model_dump_json(indent=1), encoding="utf-8")
    mr = res_of(rep7, "match_rate")
    fc = rep7.cards.functional
    ok = row("7a", "match rate with expected bits (normal file)", "100 %, PASS, 40/40, no mismatch",
             f"{fmt(mr.value, 1, 1)} %, {mr.verdict}, {fc.matched_cycles}/{fc.compared_cycles}, first={fc.first_mismatch}",
             mr.value == 100.0 and mr.verdict == "PASS" and (fc.matched_cycles, fc.compared_cycles) == (40, 40)
             and fc.first_mismatch is None)
    vc = rep7.cards.verdicts
    ok &= row("7a", "card 1 full demo (D9/plan 9.1)", "PASS 4 · MARGINAL 1 · FAIL 0",
              f"PASS {vc.pass_count} · MARGINAL {vc.marginal_count} · FAIL {vc.fail_count}",
              (vc.pass_count, vc.marginal_count, vc.fail_count) == (4, 1, 0))
    passed = sorted(r.metric_id for r in rep7.results if r.verdict == "PASS")
    ok &= row("7a", "PASS set (D9)", "iddq, match_rate, rise_time, tpd", passed,
              passed == ["iddq", "match_rate", "rise_time", "tpd"])
    wm = rep7.cards.worst_margin
    ok &= row("7a", "card 2 (plan 9.1: ! VOH 1.75 V, 하한 1.6 V, 마진 9.4 %)", "voh MARGINAL 1.75 V 9.4 %",
              f"{wm.metric_id} {wm.verdict} {fmt(wm.value, 1, 3)} V {wm.margin_pct:.1f} %",
              wm.metric_id == "voh" and wm.verdict == "MARGINAL" and abs(wm.value - 1.75) <= 0.0175 and abs(wm.margin_pct - 9.4) <= 2)
    ok &= row("7a", "card 4 (plan 9.1: ✓ 100 % (40/40))", "100 %, 40/40, PASS",
              f"{fc.match_rate_pct} %, {fc.matched_cycles}/{fc.compared_cycles}, {fc.verdict}",
              fc.match_rate_pct == 100.0 and fc.verdict == "PASS")
    # error file swapped in as the measured waveform file (same channel ids, roles kept)
    _, _, _, eres = load_waveform_file("synth_scope_err.csv")
    req7b = AnalysisRequest(measured=measured_set(eres.waveforms, [sweep], ("synth_scope_err.csv", "synth_dmm.xlsx")),
                            sim=sim_set, specs=specs, expected=exp, settings=settings)
    rep7b = run_analysis(req7b)
    (OUT / "step7_err_report.json").write_text(rep7b.model_dump_json(indent=1), encoding="utf-8")
    mrb, fcb, fd = res_of(rep7b, "match_rate"), rep7b.cards.functional, rep7b.functional
    ok &= row("7b", "error file: first mismatch cycle 37, rate 97.5 %, FAIL", "37, [37], 97.5 %, FAIL",
              f"{fcb.first_mismatch}, {fd.mismatch_cycles}, {mrb.value} %, {mrb.verdict}",
              fcb.first_mismatch == 37 and fd.mismatch_cycles == [37] and mrb.value == 97.5 and mrb.verdict == "FAIL")
    line = next((s for s in rep7b.summary_lines if "번째 사이클에서 첫 불일치" in s), None)
    ok &= row("7b", "summary rule '{n}번째 사이클에서 첫 불일치 (기대 e, 측정 m)'", "37번째 사이클에서 첫 불일치 (기대 1, 측정 0)",
              line, line == "37번째 사이클에서 첫 불일치 (기대 1, 측정 0)")
    tplh_e, tphl_e = res_of(rep7b, "tplh", "Buffer"), res_of(rep7b, "tphl", "Buffer")
    ok &= row("7b", "error file tpLH/tpHL unaffected (no bogus ~100 ns pairing)", "worst 6.0 / 5.5 ns ±3 %",
              f"{fmt(tplh_e.value, 1e9)} / {fmt(tphl_e.value, 1e9)} ns, warnings {[w.value for w in tplh_e.warnings]}",
              abs(tplh_e.value - 6e-9) <= 0.18e-9 and abs(tphl_e.value - 5.5e-9) <= 0.165e-9)
    vcb = rep7b.cards.verdicts
    ok &= row("7b", "card 1 with error file", "PASS 3 · MARGINAL 1 · FAIL 1",
              f"PASS {vcb.pass_count} · MARGINAL {vcb.marginal_count} · FAIL {vcb.fail_count}",
              (vcb.pass_count, vcb.marginal_count, vcb.fail_count) == (3, 1, 1))
    ok_all &= ok

    # ================= step 8: bandwidth 100 MHz
    settings8 = settings.model_copy(update={"bandwidth_hz": 100e6})
    req8 = AnalysisRequest(measured=measured_set(wfs, [sweep], ("synth_scope.csv", "synth_dmm.xlsx")), sim=sim_set,
                           specs=specs, expected=exp, settings=settings8)
    rep8 = run_analysis(req8)
    (OUT / "step8_report.json").write_text(rep8.model_dump_json(indent=1), encoding="utf-8")
    bw8 = sorted(r.metric_id for r in rep8.results if WarningCode.BANDWIDTH_LIMIT in r.warnings)
    ok = row("8", "BANDWIDTH_LIMIT at 100 MHz (limit 7 ns; D8: rise·fall)", "fall_time, rise_time", bw8,
             bw8 == ["fall_time", "rise_time"])
    bw_lines = [s for s in rep8.summary_lines if "대역폭 한계" in s]
    ok &= row("8", "summary rule 5 for rise", "line '… rise …: 측정값이 오실로스코프 대역폭 한계에 가까움 → …'",
              bw_lines, any("rise" in s and "측정값이 오실로스코프 대역폭 한계에 가까움" in s for s in bw_lines))
    bw_notices = [n.message for n in rep8.warnings if n.code == WarningCode.BANDWIDTH_LIMIT]
    ok &= row("8", "BANDWIDTH_LIMIT notices", "2 notices (rise, fall)", bw_notices, len(bw_notices) == 2)
    same_verdicts = [(r.metric_id, r.verdict) for r in rep8.results] == [(r.metric_id, r.verdict) for r in rep7.results]
    ok &= row("8", "verdicts unchanged by bandwidth", "same as step 7", same_verdicts, same_verdicts)
    ok_all &= ok

    # ---------------- summary lines dump
    for tag, rep in (("step5", rep5), ("step7", rep7), ("step7_err", rep7b), ("step8", rep8)):
        (OUT / f"{tag}_summary.txt").write_text("\n".join(rep.summary_lines) + "\n", encoding="utf-8")

    # ================= golden checks (4.4 #2, D11 table)
    g = lambda *a, **k: row(*a, table=GOLD, **k)
    def rel(v, ref):
        return abs(v - ref) / abs(ref) * 100
    for mid, ref, tol, scale, unit in (("tplh", 6.0e-9, 3, 1e9, "ns"), ("tphl", 5.5e-9, 3, 1e9, "ns"),
                                       ("rise_time", 3.0e-9, 3, 1e9, "ns"), ("fall_time", 2.5e-9, 3, 1e9, "ns")):
        r = res_of(rep7, mid)
        g("golden", f"{mid} mean", f"{ref * scale:g} {unit} ±{tol} %", f"{r.stats.mean * scale:.4f} {unit} ({rel(r.stats.mean, ref):.2f} %)",
          rel(r.stats.mean, ref) <= tol)
        g("golden", f"{mid} worst (value)", f"{ref * scale:g} {unit} ±{tol} %", f"{r.value * scale:.4f} {unit} ({rel(r.value, ref):.2f} %)",
          rel(r.value, ref) <= tol)
    r = res_of(rep7, "tpd")
    g("golden", "tpd worst", "6.0 ns ±3 %", f"{r.value * 1e9:.4f} ns ({rel(r.value, 6e-9):.2f} %)", rel(r.value, 6e-9) <= 3)
    r = res_of(rep7, "voh")
    g("golden", "voh", "1.75 V ±1 %", f"{r.value:.5f} V ({rel(r.value, 1.75):.3f} %)", rel(r.value, 1.75) <= 1)
    r = res_of(rep7, "vol")
    g("golden", "vol", "0.05 V ±0.5 mV", f"{r.value:.5f} V ({(r.value - 0.05) * 1e3:+.3f} mV)", abs(r.value - 0.05) <= 0.5e-3)
    for mid, ref, scale, unit in (("period", 100e-9, 1e9, "ns"), ("frequency", 10e6, 1e-6, "MHz"), ("duty_cycle", 50.0, 1, "%")):
        r = res_of(rep7, mid)
        g("golden", mid, f"{ref * scale:g} {unit} ±1 %", f"{r.value * scale:.4f} {unit} ({rel(r.value, ref):.3f} %)", rel(r.value, ref) <= 1)
    for mid, ref in (("setup_slack", 44.0e-9), ("hold_slack", 55.5e-9)):
        r = res_of(rep7, mid, channel_id="CH3")
        g("golden", f"{mid} worst (CH3)", f"{ref * 1e9:g} ns ±3 %", f"{r.value * 1e9:.4f} ns ({rel(r.value, ref):.2f} %)", rel(r.value, ref) <= 3)
    for mid, ref, scale, unit in (("idd_avg", 120e-6, 1e6, "µA"), ("avg_power", 216e-6, 1e6, "µW")):
        r = res_of(rep7, mid)
        g("golden", mid, f"{ref * scale:g} {unit} ±1 %", f"{r.value * scale:.4f} {unit} ({rel(r.value, ref):.3f} %)", rel(r.value, ref) <= 1)
    r = res_of(rep7, "iddq")
    g("golden", "iddq (DMM, 1.8 V)", "1.5 µA ±0.5 %", f"{r.value * 1e6:.5f} µA ({rel(r.value, 1.5e-6):.3f} %)", rel(r.value, 1.5e-6) <= 0.5)
    g("golden", "match_rate normal", "100 % (40/40)", f"{res_of(rep7, 'match_rate').value} % ({fc.matched_cycles}/{fc.compared_cycles})",
      res_of(rep7, "match_rate").value == 100.0 and fc.compared_cycles == 40)
    g("golden", "match_rate error file / first mismatch", "97.5 %, 37", f"{mrb.value} %, {fcb.first_mismatch}",
      mrb.value == 97.5 and fcb.first_mismatch == 37)
    for mid, ref in (("tplh", 6e-9), ("tphl", 5.5e-9)):
        r = res_of(rep7b, mid)
        g("golden", f"error file {mid} mean/worst", f"{ref * 1e9:g} ns ±3 %",
          f"{r.stats.mean * 1e9:.4f} / {r.value * 1e9:.4f} ns", rel(r.stats.mean, ref) <= 3 and rel(r.value, ref) <= 3)
    for mid, ref, tol, scale, unit in (("tplh", 4.5e-9, 3, 1e9, "ns"), ("tphl", 4.2e-9, 3, 1e9, "ns"), ("rise_time", 2.0e-9, 3, 1e9, "ns"),
                                       ("fall_time", 1.8e-9, 3, 1e9, "ns"), ("voh", 1.80, 1, 1, "V")):
        r = res_of(rep7, mid)
        g("golden", f"sim {mid} (sim_value)", f"{ref * scale:g} {unit} ±{tol} %", f"{r.sim_value * scale:.4f} {unit} ({rel(r.sim_value, ref):.2f} %)",
          rel(r.sim_value, ref) <= tol)
    for mid, ref in (("tplh", 33.3), ("tphl", 31.0), ("rise_time", 50.0), ("fall_time", 38.9), ("voh", -2.8)):
        r = res_of(rep7, mid)
        g("golden", f"sim deviation {mid}", f"{ref:+.1f} % ±2 %p", f"{r.deviation_pct:+.2f} %", abs(r.deviation_pct - ref) <= 2)
    r = res_of(rep7, "vol")
    g("golden", "sim deviation vol (sim 0 V -> None)", "None", r.deviation_pct, r.deviation_pct is None)
    for mid, verdict, ref in (("tpd", "PASS", 25.0), ("rise_time", "PASS", 25.0), ("voh", "MARGINAL", 9.4), ("iddq", "PASS", 40.0)):
        r = res_of(rep7, mid)
        g("golden", f"demo verdict {mid}", f"{verdict} {ref} % ±2 %p", f"{r.verdict} {r.margin_pct:.2f} %",
          r.verdict == verdict and abs(r.margin_pct - ref) <= 2)

    # ---------------- write tables
    def table_md(rows, title):
        out = [f"| 단계 | 확인 항목 | 기대 | 실제 | 결과 |", "|---|---|---|---|---|"]
        for st, what, e, a, okk in rows:
            a = a.replace("|", "/").replace("\n", " ")
            a = a if len(a) <= 260 else a[:257] + "..."
            out.append(f"| {st} | {what} | {e.replace('|', '/')} | {a} | {'PASS' if okk else 'FAIL'} |")
        return "\n".join(out) + "\n"
    (Path(__file__).parent / "demo_e2e_table.md").write_text(table_md(ROWS, "demo"), encoding="utf-8")
    (Path(__file__).parent / "golden_table.md").write_text(table_md(GOLD, "golden"), encoding="utf-8")
    print(table_md(ROWS, "demo"))
    print(table_md(GOLD, "golden"))
    for tag, rep in (("step5", rep5), ("step7", rep7), ("step7_err", rep7b), ("step8", rep8)):
        print(f"--- {tag} summary_lines")
        print("\n".join(rep.summary_lines))
    nf = sum(not r[4] for r in ROWS) + sum(not r[4] for r in GOLD)
    print(f"\ndemo rows {len(ROWS)}, golden rows {len(GOLD)}, failed {nf}")
    return 1 if nf else 0


if __name__ == "__main__":
    sys.exit(main())
