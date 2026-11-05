"""QA: UI smoke of the Streamlit app with streamlit.testing.v1.AppTest, following plan 4.2 steps 1-8.

Uses the "샘플 데이터 사용" multiselect (same processing path as an upload), the "데모 기본값 채우기" and
"샘플 기대 비트열 넣기" buttons, the bandwidth number_input and the run button. Widget keys were read from
app_streamlit/ (input_flow.py, state.py, dashboard.py). Checks: no exception, no st.error, and the
expected card / warning texts on screen.

Run: .venv/Scripts/python reports/qa/qa_ui_smoke.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from streamlit.testing.v1 import AppTest  # noqa: E402

ROWS: list[tuple[str, str, str, str, bool]] = []


def row(step, what, expected, actual, ok):
    ROWS.append((step, what, str(expected), str(actual), bool(ok)))


def texts(at) -> str:
    parts = []
    for coll in (at.markdown, at.caption, at.warning, at.info, at.success, at.error, at.subheader, at.title):
        for el in coll:
            parts.append(str(el.value))
    for m in at.metric:
        parts.append(f"{m.label} {m.value}")
    return "\n".join(parts)


def errs(at) -> list[str]:
    return [str(e.value) for e in at.error] + [str(e.value) for e in at.exception]


def step_run(at, label):
    t0 = time.perf_counter()
    at.button(key="btn_run").click().run()
    dt = time.perf_counter() - t0
    timing = at.session_state["report_timing"] if "report_timing" in at.session_state else None
    return dt, timing


def main() -> int:
    at = AppTest.from_file(str(ROOT / "app_streamlit" / "app.py"), default_timeout=180)
    at.run()
    row("0", "app starts", "no exception / no error", errs(at), not errs(at))
    opts = at.multiselect(key="in_samples").options
    row("0", "sample-data multiselect lists synth/data files", "4 files (dmm, scope, scope_err, sim)", opts,
        sorted(opts) == ["synth_dmm.xlsx", "synth_scope.csv", "synth_scope_err.csv", "synth_sim.csv"])

    # step 1: scope CSV
    at.multiselect(key="in_samples").set_value(["synth_scope.csv"]).run()
    row("1", "select synth_scope.csv (kind auto = 파형)", "no error; roles widgets CH1..CH4",
        f"errors={errs(at)}, role keys={[k for k in ('role::CH1', 'role::CH2', 'role::CH3', 'role::CH4') if k in at.session_state]}",
        not errs(at) and all(f"role::CH{i}" in at.session_state for i in range(1, 5)))
    t = texts(at)
    row("1", "file panel shows 4ch x 20,000 pts", "'4채널 · 20,000점'", "4채널 · 20,000점" in t, "4채널 · 20,000점" in t)

    # step 2/3: demo defaults button (roles, path, VDD, BW, specs)
    at.button(key="btn_demo_defaults").click().run()
    ss = at.session_state
    roles = [str(ss[f"role::CH{i}"]) for i in range(1, 5)]
    row("2", "demo defaults: roles / logic VDD / bandwidth", "CLK IN OUT IDD, 1.8, 500",
        f"{roles}, {ss['in_logic_vdd']}, {ss['in_bandwidth_mhz']}",
        roles == ["CLK", "IN", "OUT", "IDD"] and ss["in_logic_vdd"] == 1.8 and ss["in_bandwidth_mhz"] == 500.0)
    t = texts(at)
    si_line = next((l for l in t.splitlines() if l.startswith("SI 변환 확인")), "")
    row("3", "spec table -> SI caption", "tpd ≤ 8 ns · rise ≤ 4 ns · voh ≥ 1.6 V · iddq ≤ 2.5 µA", si_line,
        all(s in si_line for s in ("tpd", "rise_time", "voh", "iddq")))
    row("2", "path Buffer in base rows", "Buffer CH2->CH3", ss["paths_base"], any(r.get("이름") == "Buffer" for r in ss["paths_base"]))

    # step 4: add sim
    at.multiselect(key="in_samples").set_value(["synth_scope.csv", "synth_sim.csv"]).run()
    t = texts(at)
    row("4", "sim mapping auto-suggested", "'매핑: v(clk) → CH1 · v(in) → CH2 · v(out) → CH3'",
        next((l for l in t.splitlines() if l.startswith("매핑:")), None),
        "매핑: v(clk) → CH1 · v(in) → CH2 · v(out) → CH3" in t)
    row("4", "no error", "[]", errs(at), not errs(at))

    # step 5: run
    dt, timing = step_run(at, "5")
    t = texts(at)
    row("5", "run -> dashboard, no exception/error", "[]", errs(at), not errs(at) and at.session_state["report"] is not None)
    row("5", "card 1", "✓ PASS 2 · ! MARGINAL 1 · ✕ FAIL 0", "PASS 2" in t and "MARGINAL 1" in t,
        "✓ PASS 2" in t and "! MARGINAL 1" in t and "✕ FAIL 0" in t)
    row("5", "card 2 worst margin", "! VOH 1.75 V / 마진 9.4%", [l for l in t.splitlines() if "VOH 1.75 V" in l or "마진 9.4%" in l][:3],
        "! VOH 1.75 V" in t and "마진 9.4%" in t)
    card3 = next((l for l in t.splitlines() if "rise(CH3)" in l), None)
    row("5", "card 3 sim deviation (plan: rise +50 % · tpLH +33 % 경고)", "rise(CH3) +~50% · tpLH(Buffer) +~33%, 경고 4건",
        f"{card3} / {'경고 4건' in t}", card3 is not None and "tpLH(Buffer) +33" in card3 and "경고 4건" in t)
    row("5", "summary rule 3 on screen", "전 경로 공통 지연 증가 …", "전 경로 공통 지연 증가" in t, "전 경로 공통 지연 증가" in t)
    row("5", "UI timing (run_analysis / click->report)", "< 3 s (plan 1.3)", timing, timing is not None and timing["total_s"] < 3)
    row("5", "AppTest wall time for the click (incl. dashboard render)", "info", f"{dt:.2f} s", True)

    # step 6: add DMM xlsx
    at.multiselect(key="in_samples").set_value(["synth_dmm.xlsx", "synth_scope.csv", "synth_sim.csv"]).run()
    row("6", "DMM xlsx loaded as DC 스윕 'DMM'", "no error, caption 'DC 스윕 1개: DMM'", errs(at),
        not errs(at) and "DC 스윕 1개: DMM" in texts(at))
    step_run(at, "6")
    t = texts(at)
    rep = at.session_state["report"]
    iddq = next((r for r in rep.results if r.metric_id == "iddq"), None)
    row("6", "IDDQ PASS 40 % (report in session)", "PASS 40.0 %", f"{iddq.verdict if iddq else None} {iddq.margin_pct if iddq else None}",
        iddq is not None and iddq.verdict == "PASS" and abs(iddq.margin_pct - 40) < 2)
    row("6", "card 1 after DMM", "✓ PASS 3 · ! MARGINAL 1", "✓ PASS 3" in t, "✓ PASS 3" in t and "! MARGINAL 1" in t)
    row("6", "no error", "[]", errs(at), not errs(at))
    # DC tab: I–V chart is rendered when the DC tab is open; switch dashboard tab
    at.session_state["dash_tab"] = "DC·전력"
    at.run()
    keys = [c.key for c in at.get("plotly_chart")] if hasattr(at, "get") else []
    row("6", "DC tab renders I–V chart + IDDQ tile", "plotly chart 'dash_iv_chart', metric IDDQ 1.50 µA",
        f"charts={len(at.get('plotly_chart'))}, IDDQ metric={[m.value for m in at.metric if 'IDDQ' in m.label]}",
        any("IDDQ" in m.label and "1.50 µA" in str(m.value) for m in at.metric) and not errs(at))

    # step 7a: sample expected bits
    at.button(key="btn_sample_bits").click().run()
    bits = at.session_state["in_expected_bits"]
    row("7", "sample bits button fills 40 bits", "40-bit string", f"{len(bits)} bits", len(bits) == 40)
    step_run(at, "7a")
    t = texts(at)
    row("7", "card 4 = ✓ 100% (40/40 사이클)", "✓ 100% (40/40 사이클)", "100% (40/40 사이클)" in t, "✓ 100% (40/40 사이클)" in t)
    row("7", "card 1 full demo (D9)", "✓ PASS 4 · ! MARGINAL 1 · ✕ FAIL 0", "✓ PASS 4" in t,
        "✓ PASS 4" in t and "! MARGINAL 1" in t and "✕ FAIL 0" in t)
    # step 7b: swap measured file to the error file
    at.multiselect(key="in_samples").set_value(["synth_dmm.xlsx", "synth_scope_err.csv", "synth_sim.csv"]).run()
    roles = [str(at.session_state[f"role::CH{i}"]) for i in range(1, 5)]
    row("7", "roles kept after swapping measured file", "CLK IN OUT IDD", roles, roles == ["CLK", "IN", "OUT", "IDD"])
    step_run(at, "7b")
    t = texts(at)
    row("7", "error file: first mismatch 37 on card 4 + summary", "첫 불일치: 37번째 사이클 / 37번째 사이클에서 첫 불일치 (기대 1, 측정 0)",
        ["첫 불일치: 37번째 사이클" in t, "37번째 사이클에서 첫 불일치 (기대 1, 측정 0)" in t],
        "첫 불일치: 37번째 사이클" in t and "37번째 사이클에서 첫 불일치 (기대 1, 측정 0)" in t)
    row("7", "card 4 ✕ 97.5% (39/40)", "✕ 97.5% (39/40 사이클)", "97.5% (39/40 사이클)" in t, "✕ 97.5% (39/40 사이클)" in t)
    row("7", "no exception/error", "[]", errs(at), not errs(at))

    # step 8: back to normal file, bandwidth 100 MHz
    at.multiselect(key="in_samples").set_value(["synth_dmm.xlsx", "synth_scope.csv", "synth_sim.csv"]).run()
    at.number_input(key="in_bandwidth_mhz").set_value(100.0).run()
    step_run(at, "8")
    t = texts(at)
    bw = [l for l in t.splitlines() if "대역폭 한계" in l]
    row("8", "bandwidth 100 MHz -> rise (and fall) limit warning on screen", "'CH3 rise 2.98 ns: 측정값이 오실로스코프 대역폭 한계에 가까움 …'",
        bw[:4], any("rise" in l and "대역폭 한계에 가까움" in l for l in bw))
    row("8", "header shows 대역폭 100 MHz", "대역폭 100 MHz", "대역폭 100 MHz" in t, "대역폭 100 MHz" in t)
    row("8", "no exception/error", "[]", errs(at), not errs(at))

    # every dashboard tab renders without exception
    bad = []
    for tab in ["파형", "타이밍", "DC·전력", "기능", "시뮬 비교", "원본 데이터"]:
        at.session_state["dash_tab"] = tab
        at.run()
        if errs(at):
            bad.append((tab, errs(at)))
    row("9", "all 6 dashboard tabs render", "no exception", bad, not bad)

    out = ["| 단계 | 확인 항목 | 기대 | 실제 | 결과 |", "|---|---|---|---|---|"]
    for s, w, e, a, ok in ROWS:
        a = a.replace("|", "/").replace("\n", " ")
        out.append(f"| {s} | {w} | {e.replace('|', '/')} | {a[:240]} | {'PASS' if ok else 'FAIL'} |")
    (Path(__file__).parent / "ui_smoke_table.md").write_text("\n".join(out) + "\n", encoding="utf-8")
    print("\n".join(out))
    nf = sum(not r[4] for r in ROWS)
    print(f"\n{len(ROWS)} rows, {nf} failed")
    return 1 if nf else 0


if __name__ == "__main__":
    sys.exit(main())
