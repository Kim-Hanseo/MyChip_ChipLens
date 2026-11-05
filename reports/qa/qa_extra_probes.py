"""QA: extra probes around the demo path (not 4.4 gates; findings are reported as observations).

A. AppTest, alternate order: press "데모 기본값 채우기" BEFORE choosing any file, then pick all 3 files at once.
B. DC tab really draws the I–V curve (no "DC 스윕 데이터 없음" info).
C. Plan 1.3 explainability: every result with a value carries evidence (edges or reference levels).
D. Plan 2.2 / B9 input quirks through the public adapter API: cp949 Korean header, mV unit, probe x10, no time column.

Run: .venv/Scripts/python reports/qa/qa_extra_probes.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).parent))

ROWS = []


def row(probe, what, expected, actual, ok):
    ROWS.append((probe, what, str(expected), str(actual), bool(ok)))


def texts(at) -> str:
    parts = []
    for coll in (at.markdown, at.caption, at.warning, at.info, at.success, at.error):
        parts += [str(e.value) for e in coll]
    parts += [f"{m.label} {m.value}" for m in at.metric]
    return "\n".join(parts)


def errs(at):
    return [str(e.value) for e in at.error] + [str(e.value) for e in at.exception]


def probe_a_b():
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file(str(ROOT / "app_streamlit" / "app.py"), default_timeout=180)
    at.run()
    at.button(key="btn_demo_defaults").click().run()
    row("A", "demo defaults before any file", "no error", errs(at), not errs(at))
    at.multiselect(key="in_samples").set_value(["synth_dmm.xlsx", "synth_scope.csv", "synth_sim.csv"]).run()
    roles = [str(at.session_state[f"role::CH{i}"]) for i in range(1, 5)]
    row("A", "roles applied to channels that appear later", "CLK IN OUT IDD", roles, roles == ["CLK", "IN", "OUT", "IDD"])
    at.button(key="btn_sample_bits").click().run()
    at.button(key="btn_run").click().run()
    t = texts(at)
    ok = "✓ PASS 4" in t and "! MARGINAL 1" in t and "✕ FAIL 0" in t and "✓ 100% (40/40 사이클)" in t
    row("A", "full demo cards in alternate order", "✓ PASS 4 · ! MARGINAL 1 · ✕ FAIL 0, ✓ 100% (40/40)", ok, ok and not errs(at))
    at.session_state["dash_tab"] = "DC·전력"
    at.run()
    t = texts(at)
    row("B", "DC tab: I–V curve drawn (no 'DC 스윕 데이터 없음' info)", "I–V chart present",
        f"no-data info shown={'DC 스윕 데이터 없음' in t}, charts={len(at.get('plotly_chart'))}",
        "DC 스윕 데이터 없음" not in t and len(at.get("plotly_chart")) >= 2)
    at.session_state["dash_tab"] = "파형"
    at.run()
    t = texts(at)
    row("B", "waveform tab: default highlight = worst-margin metric with markers", "selectbox present, no error",
        f"selected={at.session_state['dash_wf_metric'] if 'dash_wf_metric' in at.session_state else None}",
        "dash_wf_metric" in at.session_state and not errs(at))
    # plan 9.3: card click -> tab + highlight (card 2 '파형에서 보기' -> VOH on the waveform tab)
    at.button(key="dash_card_worst").click().run()
    sel = at.session_state["dash_wf_metric"] if "dash_wf_metric" in at.session_state else None
    row("B", "card 2 '파형에서 보기' -> waveform tab, VOH highlighted", "파형, voh||CH3",
        f"{at.session_state['dash_tab']}, {sel}", at.session_state["dash_tab"] == "파형" and sel == "voh||CH3" and not errs(at))
    # E. UI-level determinism: press run twice with the same inputs
    j1 = at.session_state["report"].model_dump_json()
    at.button(key="btn_run").click().run()
    j2 = at.session_state["report"].model_dump_json()
    row("E", "UI: same inputs, run twice -> report JSON bytes", "identical", j1 == j2, j1 == j2)


def probe_c():
    from core.pipeline import run_analysis
    from qa_det_purity_perf import build_full_request
    rep = run_analysis(build_full_request())
    # docs/metrics.md section 3: (has edges, ref_levels_v keys, worst_time_s set, params keys)
    spec = {
        "rise_time": (True, {"low", "high", "v10", "v90"}, True, set()),
        "fall_time": (True, {"low", "high", "v10", "v90"}, True, set()),
        "tplh": (True, {"in_v50", "out_v50"}, True, set()), "tphl": (True, {"in_v50", "out_v50"}, True, set()),
        "tpd": (True, {"in_v50", "out_v50"}, True, set()),
        "period": (True, {"v50"}, False, set()), "frequency": (False, {"v50"}, False, set()),
        "duty_cycle": (True, {"v50"}, False, set()),
        "setup_slack": (True, {"clk_v50", "data_v50"}, True, set()),
        "hold_slack": (True, {"clk_v50", "data_v50"}, True, set()),
        "voh": (False, {"low", "high"}, False, set()), "vol": (False, {"low", "high"}, False, set()),
        "idd_avg": (False, set(), False, set()), "avg_power": (False, set(), False, {"vdd_v", "idd_avg_a"}),
        "iddq": (False, set(), False, {"vdd_v"}), "match_rate": (False, {"threshold_v"}, False, set()),
    }
    bad = []
    for r in rep.results:
        e = r.evidence
        got = (bool(e.edges), set(e.ref_levels_v), e.worst_time_s is not None, set(e.params))
        if got != spec[r.metric_id]:
            bad.append(f"{r.metric_id}: {got}")
    row("C", "evidence per metric == docs/metrics.md §3 (edges, ref keys, worst, params)", "all 16 match",
        bad or "all match", not bad)
    no_marker = [r.metric_id for r in rep.results if r.value is not None and not (e := r.evidence).edges
                 and not e.ref_levels_v and not e.params]
    row("C", "(observation) valued results with no evidence at all", "info", no_marker or "none", True)
    tplh = next(r for r in rep.results if r.metric_id == "tplh")
    row("C", "tpLH evidence: ref levels + interval per edge", "keys present, t_start/t_end set",
        f"ref={sorted(tplh.evidence.ref_levels_v)}, edges={len(tplh.evidence.edges)}, "
        f"interval={tplh.evidence.edges[0].t_start_s is not None and tplh.evidence.edges[0].t_end_s is not None}",
        bool(tplh.evidence.ref_levels_v) and tplh.evidence.edges[0].t_start_s is not None)


def probe_d():
    import numpy as np
    from core.adapters import preview_file, read_table, to_waveforms
    from core.models import ChannelConversion, TimeAxisSpec
    t = np.arange(200) * 1e-9
    v = np.where((np.arange(200) // 50) % 2 == 1, 180.0, 0.0)  # mV at the probe tip / 10
    lines = ["장비,테스트", "시간(ns),출력(mV)"] + [f"{ti * 1e9:.1f},{vi:.1f}" for ti, vi in zip(t, v)]
    data = ("\r\n".join(lines) + "\r\n").encode("cp949")
    pv = preview_file(data, "kor.csv")
    codes = [n.code.value for n in pv.notices]
    row("D", "cp949 CSV: UTF-8 fails -> cp949 + ENCODING_FALLBACK", "encoding cp949, ENCODING_FALLBACK",
        f"{pv.options.encoding}, {codes}", pv.options.encoding == "cp949" and "ENCODING_FALLBACK" in codes)
    tab = read_table(data, "kor.csv", pv.options)
    cols = {c.name: (c.base_name, c.unit_text, c.si_unit, c.scale) for c in tab.columns}
    row("D", "Korean headers with units: 시간(ns) -> s x1e-9, 출력(mV) -> V x1e-3", "as stated", cols,
        cols.get("시간(ns)", (None,) * 4)[2:] == ("s", 1e-9) and cols.get("출력(mV)", (None,) * 4)[2] == "V"
        and abs(cols["출력(mV)"][3] - 1e-3) < 1e-15)
    res = to_waveforms(tab, TimeAxisSpec(column="시간(ns)", scale=1e-9),
                       [ChannelConversion(column="출력(mV)", channel_id="OUT", quantity="V", scale=1e-3, probe_factor=10.0)])
    w = res.waveforms[0]
    row("D", "probe x10 + mV: max value = 180 mV x 10 = 1.8 V, dt = 1 ns", "1.8 V, 1 ns",
        f"{w.values.max():.4f} V, {w.sample_interval_s * 1e9:.4f} ns", abs(w.values.max() - 1.8) < 1e-9
        and abs(w.sample_interval_s - 1e-9) < 1e-15)
    res2 = to_waveforms(tab, TimeAxisSpec(column=None, start_s=-1e-6, interval_s=2e-10),
                        [ChannelConversion(column="출력(mV)", channel_id="OUT", quantity="V", scale=1e-3)])
    w2 = res2.waveforms[0]
    row("D", "no time column: start + n*interval", "-1 us, 0.2 ns", f"{w2.time_s[0]:.3e}, {w2.sample_interval_s:.3e}",
        abs(w2.time_s[0] + 1e-6) < 1e-18 and abs(w2.sample_interval_s - 2e-10) < 1e-20)
    big = to_waveforms(tab, TimeAxisSpec(column="시간(ns)", scale=1e-9),
                       [ChannelConversion(column="출력(mV)", channel_id="OUT", quantity="V", scale=1.0)])  # forgot mV
    row("D", "B9: unit forgotten (mV read as V, 180 V) -> SUSPICIOUS_RANGE", "SUSPICIOUS_RANGE",
        [n.code.value for n in big.notices], any(n.code.value == "SUSPICIOUS_RANGE" for n in big.notices))


def main() -> int:
    probe_a_b()
    probe_c()
    probe_d()
    out = ["| 프로브 | 확인 항목 | 기대 | 실제 | 결과 |", "|---|---|---|---|---|"]
    for p, w, e, a, ok in ROWS:
        out.append(f"| {p} | {w} | {e} | {a.replace('|', '/')[:240]} | {'PASS' if ok else 'FAIL'} |")
    (Path(__file__).parent / "extra_probes_table.md").write_text("\n".join(out) + "\n", encoding="utf-8")
    print("\n".join(out))
    nf = sum(not r[4] for r in ROWS)
    print(f"\n{len(ROWS)} rows, {nf} failed")
    return 1 if nf else 0


if __name__ == "__main__":
    sys.exit(main())
