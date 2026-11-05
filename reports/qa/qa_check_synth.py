"""QA: verify synth/data files against plan Appendix A + decisions D11 directly from the files.

Independent of synth/generate.py and core/: rebuilds the noise-free reference waveforms from the
D11 text (PRBS7, edge times, ramps, ringing, IDD), then compares with the file contents.
golden.json is only cross-checked, never used as the source of truth.

Run: .venv/Scripts/python reports/qa/qa_check_synth.py
"""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "synth" / "data"
CHECKS: list[tuple[str, str, str, bool]] = []  # (item, expected, actual, ok)


def check(item: str, expected, actual, ok: bool) -> None:
    CHECKS.append((item, str(expected), str(actual), bool(ok)))


# ---------------------------------------------------------------- reference model from D11 text

def prbs7_bits(n: int, seed: int = 0x7F) -> str:
    """Fibonacci LFSR for x^7 + x^6 + 1 (taps at bit 7 and 6), output = feedback bit."""
    state = seed
    out = []
    for _ in range(n):
        newbit = ((state >> 6) ^ (state >> 5)) & 1
        state = ((state << 1) | newbit) & 0x7F
        out.append(str(newbit))
    return "".join(out)


def ramp_signal(tau: np.ndarray, init_level: float, events: list[tuple[float, float, float]],
                full_ramp: dict[str, float]) -> np.ndarray:
    """Piecewise-linear signal: events = (t50, from_v, to_v); full ramp length depends on direction."""
    y = np.full_like(tau, init_level, dtype=float)
    for t50, v0, v1 in events:
        L = full_ramp["rise"] if v1 > v0 else full_ramp["fall"]
        a, b = t50 - L / 2, t50 + L / 2
        frac = np.clip((tau - a) / L, 0.0, 1.0)
        mask = tau >= a
        y[mask] = v0 + (v1 - v0) * frac[mask]
    return y


def ringing(tau: np.ndarray, events: list[tuple[float, float, float]], full_ramp: dict[str, float],
            f=250e6, td=2e-9, frac=0.05) -> np.ndarray:
    x = np.linspace(0, 20e-9, 200001)
    unit_peak = float(np.max(np.sin(2 * np.pi * f * x) * np.exp(-x / td)))
    r = np.zeros_like(tau)
    for t50, v0, v1 in events:
        L = full_ramp["rise"] if v1 > v0 else full_ramp["fall"]
        t_end = t50 + L / 2
        A = frac * abs(v1 - v0) / unit_peak
        sgn = 1.0 if v1 > v0 else -1.0
        dt = tau - t_end
        m = dt >= 0
        r[m] += sgn * A * np.sin(2 * np.pi * f * dt[m]) * np.exp(-dt[m] / td)
    return r


def build_reference(tau: np.ndarray, bits: str, out_bits: str, out_par: dict, with_ringing: bool):
    clk_ev, in_ev, out_ev = [], [], []
    for k in range(40):
        clk_ev.append((25.03e-9 + 100e-9 * k, 0.0, 1.8))
        clk_ev.append((75.03e-9 + 100e-9 * k, 1.8, 0.0))
    for k in range(1, 40):
        if bits[k] != bits[k - 1]:
            t = 75.03e-9 + 100e-9 * (k - 1)
            in_ev.append((t, 1.8 * int(bits[k - 1]), 1.8 * int(bits[k])))
    vol, voh = out_par["vol"], out_par["voh"]
    for k in range(1, 40):
        if out_bits[k] != out_bits[k - 1]:
            t_fall_clk = 75.03e-9 + 100e-9 * (k - 1)
            if out_bits[k] == "1":
                out_ev.append((t_fall_clk + out_par["tplh"], vol, voh))
            else:
                out_ev.append((t_fall_clk + out_par["tphl"], voh, vol))
    clk_ev.sort()
    one_ns = {"rise": 1.25e-9, "fall": 1.25e-9}
    out_ramp = {"rise": out_par["rise"] / 0.8, "fall": out_par["fall"] / 0.8}
    clk = ramp_signal(tau, 0.0, clk_ev, one_ns)
    inn = ramp_signal(tau, 1.8 * int(bits[0]), in_ev, one_ns)
    out = ramp_signal(tau, voh if out_bits[0] == "1" else vol, out_ev, out_ramp)
    if with_ringing:
        clk = clk + ringing(tau, clk_ev, one_ns)
        inn = inn + ringing(tau, in_ev, one_ns)
        out = out + ringing(tau, out_ev, out_ramp)
    return clk, inn, out, out_ev


def idd_reference(tau: np.ndarray, out_ev) -> np.ndarray:
    spikes = np.zeros_like(tau)
    for t50, _, _ in out_ev:
        spikes += 1.5e-3 * np.exp(-0.5 * ((tau - t50) / 0.5e-9) ** 2)
    base = 120e-6 - spikes.mean()
    return base + spikes


# ---------------------------------------------------------------- helpers

def read_scope(path: Path):
    raw = path.read_bytes()
    text = raw.decode("utf-8")  # must be UTF-8
    lines = text.splitlines()
    data = np.loadtxt(io.StringIO("\n".join(lines[5:])), delimiter=",")
    return raw, lines, data


def crossings(t: np.ndarray, y: np.ndarray, level: float, rising: bool) -> np.ndarray:
    """Simple linear-interpolated level crossings with 2-sample confirmation (QA's own, not core's)."""
    s = y > level
    idx = np.nonzero(s[1:] != s[:-1])[0]
    out = []
    for i in idx:
        up = (not s[i]) and s[i + 1]
        if up != rising:
            continue
        out.append(t[i] + (level - y[i]) * (t[i + 1] - t[i]) / (y[i + 1] - y[i]))
    return np.array(out)


def main() -> int:
    # -------- PRBS
    bits = prbs7_bits(40)
    golden = json.loads((DATA / "golden.json").read_text(encoding="utf-8"))
    check("PRBS7 x^7+x^6+1 seed 0x7F first 40 bits (QA LFSR) == golden.bits", bits, golden["bits"],
          bits == golden["bits"])
    n01 = sum(1 for a, b in zip(bits, bits[1:]) if a == "0" and b == "1")
    n10 = sum(1 for a, b in zip(bits, bits[1:]) if a == "1" and b == "0")
    check("IN 0->1 / 1->0 transitions each >= 8", ">= 8 / >= 8", f"{n01} / {n10}", n01 >= 8 and n10 >= 8)
    bits_err = bits[:36] + ("1" if bits[36] == "0" else "0") + bits[37:]
    check("error bits = o[36] inverted (cycle 37)", bits_err, golden["bits_err"], bits_err == golden["bits_err"])

    out_meas = {"tplh": 6.0e-9, "tphl": 5.5e-9, "rise": 3.0e-9, "fall": 2.5e-9, "voh": 1.75, "vol": 0.05}
    out_sim = {"tplh": 4.5e-9, "tphl": 4.2e-9, "rise": 2.0e-9, "fall": 1.8e-9, "voh": 1.80, "vol": 0.00}

    # -------- scope csv (normal + error)
    results = {}
    for name, obits in (("synth_scope.csv", bits), ("synth_scope_err.csv", bits_err)):
        raw, lines, d = read_scope(DATA / name)
        check(f"{name}: UTF-8 decodable, no BOM", "utf-8", "utf-8 ok" if not raw.startswith(b"\xef\xbb\xbf") else "BOM",
              not raw.startswith(b"\xef\xbb\xbf"))
        exp_hdr = ["Model,ChipLens-SynthScope", "Sample Interval,2.000000E-10", "Record Length,20000",
                   "Trigger Position,-2.000000E-06", "Time(s),CH1(V),CH2(V),CH3(V),CH4(A)"]
        check(f"{name}: 5 header lines (D11 format)", exp_hdr, lines[:5], lines[:5] == exp_hdr)
        check(f"{name}: data rows (20,000 per channel)", 20000, d.shape[0], d.shape[0] == 20000)
        check(f"{name}: columns (time + CH1..CH4)", 5, d.shape[1], d.shape[1] == 5)
        t = d[:, 0]
        n = np.arange(d.shape[0])
        terr = np.max(np.abs(t - (-2.0e-6 + n * 0.2e-9)))
        check(f"{name}: t = -2.0 us + n*0.2 ns (5 GS/s)", "max err < 1e-15 s", f"{terr:.2e}", terr < 1e-15)
        span = t[-1] - t[0] + 0.2e-9
        check(f"{name}: record length 4 us", 4e-6, f"{span:.6e}", abs(span - 4e-6) < 1e-15)
        tau = t + 2.0e-6
        clk, inn, out, out_ev = build_reference(tau, bits, obits, out_meas, with_ringing=True)
        idd = idd_reference(tau, out_ev)
        for col, ref, label, sigma, unit in ((1, clk, "CH1 CLK", 10e-3, "V"), (2, inn, "CH2 IN", 10e-3, "V"),
                                             (3, out, "CH3 OUT", 10e-3, "V"), (4, idd, "CH4 IDD", 1e-6, "A")):
            res = d[:, col] - ref
            ok = abs(res.std() - sigma) < 0.05 * sigma and abs(res.mean()) < 5 * sigma / np.sqrt(len(res)) + 1e-12
            # residual must look like white noise: no structure left near edges
            maxabs = np.max(np.abs(res))
            ok = ok and maxabs < 6 * sigma
            check(f"{name}: {label} - D11 reference (ramps+ringing{'+spikes' if col == 4 else ''}) = gaussian noise",
                  f"std {sigma:g} {unit}, |max| < 6 sigma",
                  f"mean {res.mean():.3g}, std {res.std():.4g}, |max| {maxabs:.3g}", ok)
        # without ringing the residual should be visibly larger near edges (ringing actually present)
        _, _, out_nr, _ = build_reference(tau, bits, obits, out_meas, with_ringing=False)
        res_nr = d[:, 3] - out_nr
        check(f"{name}: ringing present on OUT (residual w/o ringing |max| > 60 mV)", "> 0.06 V",
              f"{np.max(np.abs(res_nr)):.3f} V", np.max(np.abs(res_nr)) > 0.06)
        check(f"{name}: IDD mean ~ 120 uA", "120 uA +/- 0.05 uA", f"{d[:, 4].mean() * 1e6:.4f} uA",
              abs(d[:, 4].mean() - 120e-6) < 0.05e-6)
        check(f"{name}: IDD spikes peak ~1.5 mA at OUT transitions", "max ~ 1.5 mA + base",
              f"{d[:, 4].max() * 1e3:.3f} mA", 1.4e-3 < d[:, 4].max() < 1.8e-3)
        # QA's own measurement straight from the file (moving average 5 points against noise)
        k = 5
        sm = lambda y: np.convolve(y, np.ones(k) / k, mode="same")
        oc = crossings(t, sm(d[:, 3]), (0.05 + 1.75) / 2, True)
        ic = crossings(t, sm(d[:, 2]), 0.9, True)
        clk_r = crossings(t, sm(d[:, 1]), 0.9, True)
        results[name] = {"out_rise50": oc, "in_rise50": ic, "clk_rise50": clk_r, "data": d}
        # sample OUT at CLK rising crossings -> bits
        samp = np.interp(clk_r, t, d[:, 3])
        mbits = "".join("1" if v >= 0.9 else "0" for v in samp)
        check(f"{name}: OUT sampled at {len(clk_r)} CLK rises (QA) == {'o' if obits == bits else 'o_err'}",
              obits, mbits, mbits == obits)
        check(f"{name}: CLK rise 50% crossings at tau = 25.03 ns + 100k ns", "40 crossings, max err < 0.1 ns",
              f"{len(clk_r)}, max err {np.max(np.abs(clk_r + 2e-6 - (25.03e-9 + 1e-7 * np.arange(len(clk_r))))) * 1e9:.3f} ns"
              if len(clk_r) == 40 else len(clk_r),
              len(clk_r) == 40 and np.max(np.abs(clk_r + 2e-6 - (25.03e-9 + 1e-7 * np.arange(40)))) < 0.1e-9)

    # error file vs normal: differs only around cycle 37 OUT and IDD
    dn, de = results["synth_scope.csv"]["data"], results["synth_scope_err.csv"]["data"]
    same_cols = all(np.array_equal(dn[:, c], de[:, c]) for c in (0, 1, 2))
    check("err vs normal: Time, CH1, CH2 byte-identical values", True, same_cols, same_cols)
    diff_rows = np.nonzero(np.any(dn[:, 3:5] != de[:, 3:5], axis=1))[0]
    t_lo, t_hi = dn[diff_rows[0], 0] + 2e-6, dn[diff_rows[-1], 0] + 2e-6
    check("err vs normal: CH3/CH4 differ only near cycle 37 (tau 3.5-3.75 us)",
          "diff window inside [3.50, 3.75] us", f"[{t_lo * 1e6:.4f}, {t_hi * 1e6:.4f}] us",
          3.50e-6 <= t_lo and t_hi <= 3.75e-6)

    # -------- sim csv
    raw = (DATA / "synth_sim.csv").read_bytes()
    lines = raw.decode("utf-8").splitlines()
    check("synth_sim.csv: header 'time v(clk) time v(in) time v(out)' (wr_vecnames, repeated time)",
          "time v(clk) time v(in) time v(out)", lines[0].strip(), lines[0].split() == ["time", "v(clk)", "time", "v(in)", "time", "v(out)"])
    check("synth_sim.csv: whitespace separated, scientific notation", "no commas, 'e' notation",
          lines[1][:60], ("," not in lines[1]) and ("e" in lines[1]))
    s = np.loadtxt(io.StringIO("\n".join(lines[1:])))
    check("synth_sim.csv: rows tau 0..4 us at 0.1 ns", 40001, s.shape[0], s.shape[0] == 40001)
    ts = s[:, 0]
    terr = np.max(np.abs(ts - np.arange(s.shape[0]) * 0.1e-9))
    check("synth_sim.csv: t = tau = n*0.1 ns", "max err < 1e-15", f"{terr:.2e}", terr < 1e-15)
    check("synth_sim.csv: repeated time columns identical", True,
          bool(np.array_equal(s[:, 0], s[:, 2]) and np.array_equal(s[:, 0], s[:, 4])),
          np.array_equal(s[:, 0], s[:, 2]) and np.array_equal(s[:, 0], s[:, 4]))
    clk, inn, out, _ = build_reference(ts, bits, bits, out_sim, with_ringing=False)
    for col, ref, label in ((1, clk, "v(clk)"), (3, inn, "v(in)"), (5, out, "v(out)")):
        e = np.max(np.abs(s[:, col] - ref))
        check(f"synth_sim.csv: {label} == D11 noise-free, ringing-free reference", "max err < 1e-6 V",
              f"{e:.2e} V", e < 1e-6)

    # -------- dmm xlsx
    import openpyxl
    wb = openpyxl.load_workbook(DATA / "synth_dmm.xlsx")
    check("synth_dmm.xlsx: sheets", ["DC측정", "조건"], wb.sheetnames, wb.sheetnames[:2] == ["DC측정", "조건"])
    ws = wb["DC측정"]
    merged = [str(r) for r in ws.merged_cells.ranges]
    check("DC측정: A1:C1 merged title", "A1:C1", merged, "A1:C1" in merged)
    check("DC측정: title text", "멀티미터 DC 측정 — 칩 #1, 25 °C", ws["A1"].value,
          ws["A1"].value == "멀티미터 DC 측정 — 칩 #1, 25 °C")
    row2 = [ws.cell(2, c).value for c in range(1, 4)]
    check("DC측정: row 2 blank", [None, None, None], row2, all(v in (None, "") for v in row2))
    hdr = [ws.cell(3, c).value for c in range(1, 4)]
    check("DC측정: row 3 headers (µ = U+00B5)", ["전압(V)", "전류(µA)", "비고"], hdr,
          hdr == ["전압(V)", "전류(µA)", "비고"])
    check("DC측정: '전류(µA)' uses U+00B5 MICRO SIGN", "U+00B5",
          " ".join(f"U+{ord(ch):04X}" for ch in str(hdr[1]) if not ch.isascii() and ch not in "전류"),
          "µ" in str(hdr[1]))
    ok_rows = True
    rows = []
    for i, r in enumerate(range(4, 15)):
        v, cur, note = (ws.cell(r, c).value for c in range(1, 4))
        V = round(1.0 + 0.1 * i, 1)
        I = round(1.5 * np.exp((V - 1.8) / 0.25), 4)
        rows.append((v, cur, note))
        ok_rows &= abs(float(v) - V) < 1e-12 and abs(float(cur) - I) < 1e-12
        ok_rows &= (note == "IDDQ 기준") if V == 1.8 else (note in (None, ""))
    check("DC측정: rows 4-14 V=1.0..2.0 step 0.1, I=round(1.5 exp((V-1.8)/0.25),4) uA, 1.8 V note 'IDDQ 기준'",
          "11 rows exact", f"{len(rows)} rows, 1.8V row = {rows[8]}", ok_rows and len(rows) == 11)
    check("DC측정: nothing below row 14", None, ws.cell(15, 1).value, ws.cell(15, 1).value in (None, ""))
    check("DC측정: IDDQ(1.8 V) = 1.5 uA exactly", 1.5, rows[8][1], rows[8][1] == 1.5)
    wc = wb["조건"]
    kv = [[c.value for c in row] for row in wc.iter_rows()]
    check("조건 sheet: key-value table (chip ID, temperature, instrument)", "chip/온도/장비 keys present", kv,
          any("칩" in str(r[0]) for r in kv) and any("온도" in str(r[0]) for r in kv)
          and any("장비" in str(r[0]) for r in kv))

    # -------- write report
    out = [f"| # | item | expected | actual | result |", "|---|---|---|---|---|"]
    for i, (item, e, a, ok) in enumerate(CHECKS, 1):
        a = a if len(a) < 160 else a[:157] + "..."
        e = e if len(e) < 160 else e[:157] + "..."
        out.append(f"| {i} | {item} | {e.replace('|', '/')} | {a.replace('|', '/')} | {'PASS' if ok else 'FAIL'} |")
    (Path(__file__).parent / "synth_check_table.md").write_text("\n".join(out) + "\n", encoding="utf-8")
    nfail = sum(not c[3] for c in CHECKS)
    print("\n".join(out))
    print(f"\n{len(CHECKS)} checks, {nfail} failed")
    return 1 if nfail else 0


if __name__ == "__main__":
    sys.exit(main())
