"""QA: plan 4.4 #3 (determinism), #4 (core does not import streamlit/plotly) and plan 1.3 speed.

Modes
  (no args)      run all checks, spawning fresh interpreters where required
  --dump PATH    (child) build the full demo request, run_analysis once, write model_dump_json() bytes to PATH
  --modules      (child) import core packages, run the full pipeline, print streamlit/plotly modules in sys.modules

Run: .venv/Scripts/python reports/qa/qa_det_purity_perf.py
"""

from __future__ import annotations

import hashlib
import json
import re
import statistics
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
HERE = Path(__file__).parent
PY = sys.executable
DATA = ROOT / "synth" / "data"


def build_full_request(scope="synth_scope.csv", bw=500e6):
    """Full demo state (scope + sim + DMM + specs + expected bits), built through core public API in UI order."""
    from core.adapters import preview_file, read_table, suggest_sim_mapping, to_dc_sweep, to_waveforms
    from core.models import (METRICS, AnalysisRequest, AnalysisSettings, ChannelConversion, ChannelInfo, ChannelMap,
                             ExpectedPattern, MeasurementSet, Path as SigPath, Role, SessionInfo, Source, Spec,
                             TimeAxisSpec)

    def table_of(name):
        data = (DATA / name).read_bytes()
        pv = preview_file(data, name)
        return pv, read_table(data, name, pv.options)

    pv, t = table_of(scope)
    tcol = pv.time_candidates[0]
    taxis = TimeAxisSpec(column=tcol, scale=t.column(tcol).scale)
    wfs = to_waveforms(t, taxis, [ChannelConversion(column=c.name, channel_id=c.base_name, quantity="A" if c.si_unit == "A" else "V",
                                                    scale=c.scale) for c in t.columns if c.name != tcol]).waveforms
    cmap = ChannelMap(channels=[ChannelInfo(channel_id=c, role=r) for c, r in
                                (("CH1", Role.CLK), ("CH2", Role.IN), ("CH3", Role.OUT), ("CH4", Role.IDD))])
    paths = [SigPath(name="Buffer", input_channel="CH2", output_channel="CH3")]
    spv, st = table_of("synth_sim.csv")
    stc = spv.time_candidates[0]
    sugg = suggest_sim_mapping(st.columns, cmap)
    swfs = to_waveforms(st, TimeAxisSpec(column=stc, scale=st.column(stc).scale),
                        [ChannelConversion(column=k, channel_id=v, quantity="V", scale=st.column(k).scale)
                         for k, v in sugg.items() if v]).waveforms
    _, dt = table_of("synth_dmm.xlsx")
    x = next(c for c in dt.columns if c.si_unit == "V")
    y = next(c for c in dt.columns if c.si_unit == "A")
    sweep = to_dc_sweep(dt, x.name, y.name, x_scale=x.scale, y_scale=y.scale, name="DMM").sweep
    specs = [Spec(metric_id=m, min=None if lo is None else lo / METRICS[m].display_scale,
                  max=None if hi is None else hi / METRICS[m].display_scale)
             for m, lo, hi in (("tpd", None, 8.0), ("rise_time", None, 4.0), ("voh", 1.6, None), ("iddq", None, 2.5))]
    state, bits = 0x7F, ""
    for _ in range(40):
        nb = ((state >> 6) ^ (state >> 5)) & 1
        state = ((state << 1) | nb) & 0x7F
        bits += str(nb)
    return AnalysisRequest(
        measured=MeasurementSet(session=SessionInfo(source=Source.MEASURED, files=[scope, "synth_dmm.xlsx"]),
                                channel_map=cmap, paths=paths, waveforms=wfs, dc_sweeps=[sweep]),
        sim=MeasurementSet(session=SessionInfo(source=Source.SIM, files=["synth_sim.csv"]), channel_map=cmap,
                           paths=paths, waveforms=swfs),
        specs=specs, expected=ExpectedPattern(bits=bits), settings=AnalysisSettings(logic_vdd_v=1.8, bandwidth_hz=bw))


def child_dump(path: str) -> None:
    from core.pipeline import run_analysis
    Path(path).write_bytes(run_analysis(build_full_request()).model_dump_json().encode("utf-8"))


def child_modules() -> None:
    import core  # noqa: F401
    import core.adapters  # noqa: F401
    import core.analyzers  # noqa: F401
    import core.judge  # noqa: F401
    import core.models  # noqa: F401
    import core.pipeline  # noqa: F401
    import core.preprocess  # noqa: F401
    after_import = sorted(m for m in sys.modules if m.split(".")[0] in ("streamlit", "plotly"))
    from core.pipeline import run_analysis
    run_analysis(build_full_request())
    after_run = sorted(m for m in sys.modules if m.split(".")[0] in ("streamlit", "plotly"))
    print(json.dumps({"after_import": after_import, "after_run": after_run}))


def main() -> int:
    rows = []

    def row(what, expected, actual, ok):
        rows.append((what, str(expected), str(actual), bool(ok)))

    from core.pipeline import run_analysis

    # ---------------- 4.4 #3 determinism, same process
    req = build_full_request()
    a = run_analysis(req).model_dump_json().encode()
    b = run_analysis(req).model_dump_json().encode()
    req2 = build_full_request()  # rebuilt from file bytes
    c = run_analysis(req2).model_dump_json().encode()
    row("same process: run_analysis(req) x2 -> model_dump_json bytes", "identical", f"{a == b} (sha256 {hashlib.sha256(a).hexdigest()[:16]}, {len(a):,} B)", a == b)
    row("same process: request rebuilt from file bytes -> bytes", "identical", a == c, a == c)
    # errors file + bw 100 MHz as a second input
    r_err = build_full_request(scope="synth_scope_err.csv", bw=100e6)
    e1, e2 = (run_analysis(r_err).model_dump_json().encode() for _ in range(2))
    row("same process: error file + 100 MHz x2", "identical", e1 == e2, e1 == e2)
    no_ts = not re.search(rb"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}", a) and b"uuid" not in a.lower()
    row("report JSON has no timestamp / uuid-like fields (D10)", "none", "none found" if no_ts else "found", no_ts)

    # ---------------- fresh processes x2
    outs = []
    for i in (1, 2):
        p = HERE / "out" / f"det_proc{i}.json"
        p.parent.mkdir(exist_ok=True)
        subprocess.run([PY, __file__, "--dump", str(p)], check=True, cwd=str(ROOT))
        outs.append(p.read_bytes())
    row("2 fresh interpreters: model_dump_json bytes", "identical",
        f"{outs[0] == outs[1]} (sha256 {hashlib.sha256(outs[0]).hexdigest()[:16]} / {hashlib.sha256(outs[1]).hexdigest()[:16]})",
        outs[0] == outs[1])
    row("fresh interpreter bytes == in-process bytes", "identical", outs[0] == a, outs[0] == a)

    # ---------------- 4.4 #4 purity: source scan
    pat = re.compile(r"^\s*(import|from)\s+(streamlit|plotly)\b|import_module\(\s*['\"](streamlit|plotly)|__import__\(\s*['\"](streamlit|plotly)", re.M)
    hits = []
    for f in sorted((ROOT / "core").rglob("*.py")):
        for m in pat.finditer(f.read_text(encoding="utf-8")):
            hits.append(f"{f.relative_to(ROOT)}: {m.group(0).strip()}")
    row("source scan core/**/*.py for streamlit/plotly imports", "0 hits", hits or "0 hits", not hits)
    third = set()
    for f in (ROOT / "core").rglob("*.py"):
        for m in re.finditer(r"^\s*(?:import|from)\s+([A-Za-z_][\w]*)", f.read_text(encoding="utf-8"), re.M):
            third.add(m.group(1))
    allowed = {"numpy", "scipy", "pandas", "openpyxl", "pydantic", "core", "__future__"}
    stdlib = set(sys.stdlib_module_names)
    extra = sorted(t for t in third if t not in allowed and t not in stdlib)
    row("core third-party imports ⊂ numpy/scipy/pandas/openpyxl/pydantic (D1)", "nothing else",
        f"third-party used: {sorted(t for t in third if t not in stdlib and t != '__future__')}, extra: {extra or 'none'}",
        not extra)
    proc = subprocess.run([PY, __file__, "--modules"], check=True, cwd=str(ROOT), capture_output=True, text=True)
    mods = json.loads(proc.stdout.strip().splitlines()[-1])
    row("fresh interpreter: import core, core.adapters, core.analyzers, core.judge, core.pipeline (+models, preprocess)"
        " -> streamlit/plotly in sys.modules", "none", mods["after_import"] or "none", not mods["after_import"])
    row("same interpreter after a full run_analysis -> streamlit/plotly in sys.modules", "none", mods["after_run"] or "none",
        not mods["after_run"])

    # ---------------- speed (plan 1.3: 20k pts x 4 ch, analysis -> verdict cards <= 3 s)
    t_build, t_run = [], []
    for _ in range(5):
        t0 = time.perf_counter()
        rq = build_full_request()
        t1 = time.perf_counter()
        run_analysis(rq)
        t2 = time.perf_counter()
        t_build.append(t1 - t0)
        t_run.append(t2 - t1)
    from core.analyzers import analyze_all
    t_all = []
    for _ in range(5):
        t0 = time.perf_counter()
        analyze_all(req.measured, req.settings, req.expected)
        t_all.append(time.perf_counter() - t0)
    med = statistics.median
    row("analyze_all (measured 20k x 4ch) median of 5", "< 1 s target, 3 s limit (contract §3)",
        f"{med(t_all) * 1e3:.1f} ms (max {max(t_all) * 1e3:.1f} ms)", max(t_all) < 1.0)
    row("run_analysis full demo (20k x 4ch + sim 40k x 3ch + DMM + bits) median of 5", "< 3 s",
        f"{med(t_run) * 1e3:.1f} ms (max {max(t_run) * 1e3:.1f} ms)", max(t_run) < 3.0)
    row("file bytes -> preview_file -> read_table -> to_waveforms/to_dc_sweep (3 files) median of 5", "info",
        f"{med(t_build) * 1e3:.1f} ms", True)
    row("adapters + run_analysis total (upload -> cards data)", "< 3 s", f"{(med(t_build) + med(t_run)) * 1e3:.1f} ms",
        med(t_build) + med(t_run) < 3.0)
    # larger stress: 4x record (80k pts x 4 ch) to see scaling
    import numpy as np
    from core.models import AnalysisRequest, MeasurementSet, Waveform
    m = req.measured
    big = []
    for w in m.waveforms:
        n = w.n_samples
        dt_s = w.sample_interval_s
        ts = np.concatenate([w.time_s + k * n * dt_s for k in range(4)])
        big.append(Waveform(channel_id=w.channel_id, quantity=w.quantity, time_s=ts, values=np.tile(w.values, 4)))
    breq = AnalysisRequest(measured=MeasurementSet(session=m.session, channel_map=m.channel_map, paths=m.paths,
                                                   waveforms=big, dc_sweeps=m.dc_sweeps),
                           sim=req.sim, specs=req.specs, settings=req.settings)
    t0 = time.perf_counter()
    run_analysis(breq)
    row("stress: 80k pts x 4ch (record tiled x4) run_analysis", "info (scaling)", f"{(time.perf_counter() - t0) * 1e3:.1f} ms", True)

    out = ["| 확인 항목 | 기대 | 실제 | 결과 |", "|---|---|---|---|"]
    for w, e, a_, ok in rows:
        out.append(f"| {w} | {e} | {a_.replace('|', '/')[:260]} | {'PASS' if ok else 'FAIL'} |")
    (HERE / "det_purity_perf_table.md").write_text("\n".join(out) + "\n", encoding="utf-8")
    print("\n".join(out))
    nf = sum(not r[3] for r in rows)
    print(f"\n{len(rows)} rows, {nf} failed")
    return 1 if nf else 0


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "--dump":
        child_dump(sys.argv[2])
    elif len(sys.argv) > 1 and sys.argv[1] == "--modules":
        child_modules()
    else:
        sys.exit(main())
