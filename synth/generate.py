"""Synthetic data generator — decisions D11, number for number.

`python -m synth.generate [--out-dir DIR]` writes (default `synth/data/`):
    synth_scope.csv, synth_scope_err.csv, synth_sim.csv, synth_dmm.xlsx, golden.json

Waveform builders are pure functions that return numpy arrays, so tests can use them without files.
CSV and JSON outputs are byte-identical across runs (fixed seed, fixed number formats, "\\n" newlines).

Time conventions:
    tau  = time since the start of the record (s); all D11 timing is given in tau.
    t    = the file's own time axis: scope t = tau - 2.0 us (trigger in the middle), sim t = tau.
Exact crossing times are kept as integers in units of 0.01 ns (TU_S) to avoid float drift.
"""

from __future__ import annotations

import argparse
import json
import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, NamedTuple

import numpy as np

# ---------------------------------------------------------------------------
# D11 parameters
# ---------------------------------------------------------------------------
SEED = 20261105  # numpy default_rng seed (noise)
N_BITS = 40
PRBS7_SEED = 0x7F  # x^7 + x^6 + 1
ERR_CYCLE = 37  # 1-based cycle whose OUT bit is inverted in the error file (o[36])

TU_S = 1e-11  # integer time unit for crossing times: 0.01 ns
CLK_PERIOD_TU = 10_000  # 100 ns -> 10 MHz
CLK_RISE0_TU = 2_503  # first CLK rising 50 % crossing: tau = 25.03 ns
CLK_FALL0_TU = 7_503  # first CLK falling 50 % crossing: tau = 75.03 ns

LOGIC_LOW_V = 0.0  # CLK / IN levels
LOGIC_HIGH_V = 1.8
LOGIC_VDD_V = 1.8
CLK_IN_EDGE_S = 1.0e-9  # CLK / IN rise = fall (10-90 %)
RAMP_FULL_FACTOR = 1.25  # full linear ramp length = 1.25 x (10-90 % time)

RING_FREQ_HZ = 250e6
RING_TAU_S = 2e-9
RING_PEAK_FRAC = 0.05  # ringing peak = 5 % of the transition swing

NOISE_V_SIGMA = 10e-3  # CLK, IN, OUT
NOISE_I_SIGMA = 1e-6  # IDD

IDD_MEAN_A = 120e-6  # pre-noise mean (base current is solved for this)
IDD_SPIKE_PEAK_A = 1.5e-3
IDD_SPIKE_SIGMA_S = 0.5e-9

SCOPE_DT_S = 0.2e-9  # 5 GS/s
SCOPE_N = 20_000
SCOPE_PRE_N = 10_000  # samples before the trigger: t0 = -2.0 us
SCOPE_T0_S = -2.0e-6
SCOPE_T0_TU = -200_000

SIM_DT_S = 0.1e-9
SIM_N = 40_001  # tau = 0 ... 4 us inclusive (like `.tran 0.1n 4u`)

SCOPE_HEADER = ("Time(s)", "CH1(V)", "CH2(V)", "CH3(V)", "CH4(A)")
SIM_HEADER = ("time", "v(clk)", "time", "v(in)", "time", "v(out)")

DMM_SHEET = "DC측정"
DMM_COND_SHEET = "조건"
DMM_TITLE = "멀티미터 DC 측정 — 칩 #1, 25 °C"
DMM_HEADER = ("전압(V)", "전류(µA)", "비고")  # µ = U+00B5
DMM_IDDQ_NOTE = "IDDQ 기준"
DMM_IDDQ_V = 1.8
DMM_CONDITIONS = (
    ("항목", "값"),
    ("칩 ID", "#1"),
    ("온도(°C)", 25),
    ("장비", "ChipLens-SynthDMM (합성 데이터)"),
    ("측정", "VDD 스윕 1.0–2.0 V, 0.1 V 간격, IDD 측정"),
)

FILE_NAMES = {
    "scope": "synth_scope.csv",
    "scope_err": "synth_scope_err.csv",
    "sim": "synth_sim.csv",
    "dmm": "synth_dmm.xlsx",
    "golden": "golden.json",
}

DEFAULT_OUT_DIR = Path(__file__).resolve().parent / "data"


@dataclass(frozen=True)
class OutputSpec:
    """OUT channel shape. Delays are integers in TU_S units; edge times are 10-90 %."""

    tplh_tu: int
    tphl_tu: int
    rise_s: float
    fall_s: float
    voh_v: float
    vol_v: float


SCOPE_OUT = OutputSpec(tplh_tu=600, tphl_tu=550, rise_s=3.0e-9, fall_s=2.5e-9, voh_v=1.75, vol_v=0.05)
SIM_OUT = OutputSpec(tplh_tu=450, tphl_tu=420, rise_s=2.0e-9, fall_s=1.8e-9, voh_v=1.80, vol_v=0.00)


class Transition(NamedTuple):
    """One linear-ramp transition centred on its 50 % crossing."""

    t50_tu: int  # 50 % crossing, tau in TU_S units
    v_from: float
    v_to: float
    full_s: float  # full ramp length (0 -> 100 %)

    @property
    def t50_s(self) -> float:
        return self.t50_tu * TU_S

    @property
    def rising(self) -> bool:
        return self.v_to > self.v_from


# ---------------------------------------------------------------------------
# bits and transition lists (pure)
# ---------------------------------------------------------------------------
def prbs7(n_bits: int = N_BITS, seed: int = PRBS7_SEED) -> str:
    """PRBS7 (x^7 + x^6 + 1) Fibonacci LFSR: newbit = b6 ^ b5, state = (state << 1 | newbit) & 0x7F."""
    state = seed & 0x7F
    out = []
    for _ in range(n_bits):
        newbit = ((state >> 6) ^ (state >> 5)) & 1
        state = ((state << 1) | newbit) & 0x7F
        out.append("1" if newbit else "0")
    return "".join(out)


def count_transitions(bits: str) -> tuple[int, int]:
    """(number of 0->1, number of 1->0) transitions in a bit string."""
    rises = sum(1 for a, b in zip(bits, bits[1:], strict=False) if a == "0" and b == "1")
    falls = sum(1 for a, b in zip(bits, bits[1:], strict=False) if a == "1" and b == "0")
    return rises, falls


def output_bits(bits: str, error: bool = False) -> str:
    """OUT logic sequence o = IN bits; the error file inverts o[ERR_CYCLE - 1]."""
    if not error:
        return bits
    i = ERR_CYCLE - 1
    return bits[:i] + ("0" if bits[i] == "1" else "1") + bits[i + 1 :]


def clk_rise_tu(n_cycles: int = N_BITS) -> list[int]:
    return [CLK_RISE0_TU + CLK_PERIOD_TU * k for k in range(n_cycles)]


def clk_fall_tu(n_cycles: int = N_BITS) -> list[int]:
    return [CLK_FALL0_TU + CLK_PERIOD_TU * k for k in range(n_cycles)]


def clk_transitions(n_cycles: int = N_BITS) -> list[Transition]:
    """CLK starts low; rise at 25.03 + 100k ns, fall at 75.03 + 100k ns (50 % crossings)."""
    full = CLK_IN_EDGE_S * RAMP_FULL_FACTOR
    out: list[Transition] = []
    for r, f in zip(clk_rise_tu(n_cycles), clk_fall_tu(n_cycles), strict=True):
        out.append(Transition(r, LOGIC_LOW_V, LOGIC_HIGH_V, full))
        out.append(Transition(f, LOGIC_HIGH_V, LOGIC_LOW_V, full))
    return out


def _data_transitions(
    bits: str,
    low: float,
    high: float,
    full_rise_s: float,
    full_fall_s: float,
    delay_rise_tu: int = 0,
    delay_fall_tu: int = 0,
) -> list[Transition]:
    """bit k (k >= 1) starts at CLK falling edge k-1 (+ delay); a transition only where the bit changes."""
    out: list[Transition] = []
    for k in range(1, len(bits)):
        if bits[k] == bits[k - 1]:
            continue
        base = CLK_FALL0_TU + CLK_PERIOD_TU * (k - 1)
        if bits[k] == "1":
            out.append(Transition(base + delay_rise_tu, low, high, full_rise_s))
        else:
            out.append(Transition(base + delay_fall_tu, high, low, full_fall_s))
    return out


def in_transitions(bits: str) -> list[Transition]:
    """IN: 0 <-> 1.8 V, 1.0 ns edges; its 50 % crossing is exactly the CLK falling crossing."""
    full = CLK_IN_EDGE_S * RAMP_FULL_FACTOR
    return _data_transitions(bits, LOGIC_LOW_V, LOGIC_HIGH_V, full, full)


def out_transitions(obits: str, spec: OutputSpec) -> list[Transition]:
    """OUT: 50 % crossing = CLK falling crossing + tpLH (0->1) / tpHL (1->0)."""
    return _data_transitions(
        obits,
        spec.vol_v,
        spec.voh_v,
        spec.rise_s * RAMP_FULL_FACTOR,
        spec.fall_s * RAMP_FULL_FACTOR,
        spec.tplh_tu,
        spec.tphl_tu,
    )


# ---------------------------------------------------------------------------
# signal builders (pure, numpy)
# ---------------------------------------------------------------------------
def scope_tau() -> np.ndarray:
    """tau (s) of the scope record: n * 0.2 ns, n = 0 ... 19 999."""
    return np.arange(SCOPE_N, dtype=np.float64) * SCOPE_DT_S


def scope_time() -> np.ndarray:
    """Scope file time axis (s): -2.0 us + n * 0.2 ns."""
    return (np.arange(SCOPE_N, dtype=np.float64) - SCOPE_PRE_N) * SCOPE_DT_S


def sim_time() -> np.ndarray:
    """Sim time axis (s) = tau: n * 0.1 ns, n = 0 ... 40 000."""
    return np.arange(SIM_N, dtype=np.float64) * SIM_DT_S


def ramp_signal(tau_s: np.ndarray, initial_v: float, transitions: Sequence[Transition]) -> np.ndarray:
    """Piecewise-linear signal: initial level + one full linear ramp per transition."""
    y = np.full(tau_s.shape, float(initial_v))
    for tr in transitions:
        start = tr.t50_s - tr.full_s / 2.0
        frac = np.clip((tau_s - start) / tr.full_s, 0.0, 1.0)
        y += (tr.v_to - tr.v_from) * frac
    return y


def ringing_unit_peak() -> float:
    """Peak of sin(2*pi*f*x) * exp(-x/tau) for x >= 0 (analytic: tan(w x) = w tau)."""
    w = 2.0 * math.pi * RING_FREQ_HZ
    x = math.atan(w * RING_TAU_S) / w
    return math.sin(w * x) * math.exp(-x / RING_TAU_S)


def ringing_amplitude(swing_v: float) -> float:
    """Signed amplitude A so that the first overshoot peak is 5 % of the (signed) swing."""
    return RING_PEAK_FRAC * swing_v / ringing_unit_peak()


def ringing_signal(tau_s: np.ndarray, transitions: Sequence[Transition]) -> np.ndarray:
    """Sum of A*sin(2*pi*250MHz*(t-t_end))*exp(-(t-t_end)/2ns) from each ramp end t_end."""
    w = 2.0 * math.pi * RING_FREQ_HZ
    y = np.zeros(tau_s.shape)
    for tr in transitions:
        a = ringing_amplitude(tr.v_to - tr.v_from)
        t_end = tr.t50_s + tr.full_s / 2.0
        m = tau_s >= t_end
        x = tau_s[m] - t_end
        y[m] += a * np.sin(w * x) * np.exp(-x / RING_TAU_S)
    return y


def idd_spikes(tau_s: np.ndarray, out_trs: Sequence[Transition]) -> np.ndarray:
    """Gaussian current spike (peak 1.5 mA, sigma 0.5 ns) at every OUT 50 % crossing."""
    y = np.zeros(tau_s.shape)
    for tr in out_trs:
        z = (tau_s - tr.t50_s) / IDD_SPIKE_SIGMA_S
        y += IDD_SPIKE_PEAK_A * np.exp(-0.5 * z * z)
    return y


def idd_base_current(tau_s: np.ndarray, out_trs: Sequence[Transition]) -> float:
    """Base current so that the pre-noise IDD mean over the record is exactly 120 uA."""
    return IDD_MEAN_A - float(np.mean(idd_spikes(tau_s, out_trs)))


def idd_signal(tau_s: np.ndarray, out_trs: Sequence[Transition]) -> np.ndarray:
    """Pre-noise IDD: base + spikes, mean exactly 120 uA."""
    spikes = idd_spikes(tau_s, out_trs)
    return (IDD_MEAN_A - float(np.mean(spikes))) + spikes


def scope_noise() -> dict[str, np.ndarray]:
    """Gaussian noise for CH1..CH4 (same seed and draw order for the normal and error files)."""
    rng = np.random.default_rng(SEED)
    return {
        "CH1": rng.normal(0.0, NOISE_V_SIGMA, SCOPE_N),
        "CH2": rng.normal(0.0, NOISE_V_SIGMA, SCOPE_N),
        "CH3": rng.normal(0.0, NOISE_V_SIGMA, SCOPE_N),
        "CH4": rng.normal(0.0, NOISE_I_SIGMA, SCOPE_N),
    }


def scope_clean(error: bool = False) -> dict[str, np.ndarray]:
    """Noise-free scope channels (ramps + ringing; IDD with spikes). Keys: t, tau, CH1..CH4."""
    tau = scope_tau()
    bits = prbs7()
    obits = output_bits(bits, error)
    clk = clk_transitions()
    din = in_transitions(bits)
    dout = out_transitions(obits, SCOPE_OUT)
    out0 = SCOPE_OUT.voh_v if obits[0] == "1" else SCOPE_OUT.vol_v
    in0 = LOGIC_HIGH_V if bits[0] == "1" else LOGIC_LOW_V
    return {
        "t": scope_time(),
        "tau": tau,
        "CH1": ramp_signal(tau, LOGIC_LOW_V, clk) + ringing_signal(tau, clk),
        "CH2": ramp_signal(tau, in0, din) + ringing_signal(tau, din),
        "CH3": ramp_signal(tau, out0, dout) + ringing_signal(tau, dout),
        "CH4": idd_signal(tau, dout),
    }


def scope_waveforms(error: bool = False) -> dict[str, np.ndarray]:
    """Scope channels as written to the CSV (clean + noise). Keys: t, CH1 (CLK), CH2 (IN), CH3 (OUT), CH4 (IDD)."""
    clean = scope_clean(error)
    noise = scope_noise()
    out = {"t": clean["t"]}
    for ch in ("CH1", "CH2", "CH3", "CH4"):
        out[ch] = clean[ch] + noise[ch] + 0.0  # + 0.0 turns -0.0 into 0.0
    return out


def sim_waveforms() -> dict[str, np.ndarray]:
    """Noise- and ringing-free sim channels. Keys: t, v(clk), v(in), v(out)."""
    t = sim_time()
    bits = prbs7()
    in0 = LOGIC_HIGH_V if bits[0] == "1" else LOGIC_LOW_V
    out0 = SIM_OUT.voh_v if bits[0] == "1" else SIM_OUT.vol_v
    return {
        "t": t,
        "v(clk)": ramp_signal(t, LOGIC_LOW_V, clk_transitions()) + 0.0,
        "v(in)": ramp_signal(t, in0, in_transitions(bits)) + 0.0,
        "v(out)": ramp_signal(t, out0, out_transitions(bits, SIM_OUT)) + 0.0,
    }


def dmm_rows() -> list[tuple[float, float, str | None]]:
    """(V, I in uA, note) for V = 1.0 ... 2.0 step 0.1; I = round(1.5 * exp((V - 1.8) / 0.25), 4)."""
    rows: list[tuple[float, float, str | None]] = []
    for i in range(11):
        v = round(1.0 + 0.1 * i, 1)
        cur = round(1.5 * math.exp((v - DMM_IDDQ_V) / 0.25), 4)
        rows.append((v, cur, DMM_IDDQ_NOTE if v == DMM_IDDQ_V else None))
    return rows


# ---------------------------------------------------------------------------
# file text
# ---------------------------------------------------------------------------
def scope_csv_text(w: dict[str, np.ndarray]) -> str:
    """D11 scope CSV: 4 metadata lines, header, 20 000 data rows."""
    head = [
        "Model,ChipLens-SynthScope",
        f"Sample Interval,{SCOPE_DT_S:.6E}",
        f"Record Length,{SCOPE_N}",
        f"Trigger Position,{SCOPE_T0_S:.6E}",
        ",".join(SCOPE_HEADER),
    ]
    cols = [w["t"].tolist(), w["CH1"].tolist(), w["CH2"].tolist(), w["CH3"].tolist(), w["CH4"].tolist()]
    body = [
        f"{t:.10E},{a:.6E},{b:.6E},{c:.6E},{d:.6E}" for t, a, b, c, d in zip(*cols, strict=True)
    ]
    return "\n".join(head + body) + "\n"


def sim_text(w: dict[str, np.ndarray]) -> str:
    """ngspice `wrdata` look-alike (wr_vecnames on, wr_singlescale off): space separated, time repeated."""
    t = w["t"].tolist()
    clk, din, dout = w["v(clk)"].tolist(), w["v(in)"].tolist(), w["v(out)"].tolist()
    lines = [" ".join(SIM_HEADER)]
    lines += [
        f" {ti:.8e}  {a:.8e}  {ti:.8e}  {b:.8e}  {ti:.8e}  {c:.8e}"
        for ti, a, b, c in zip(t, clk, din, dout, strict=True)
    ]
    return "\n".join(lines) + "\n"


def write_dmm_xlsx(path: Path) -> None:
    """D11 multimeter workbook: sheet 'DC측정' (merged title, blank row, header row 3, data rows 4-14)
    and sheet '조건' (key-value table)."""
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = DMM_SHEET
    ws["A1"] = DMM_TITLE
    ws.merge_cells("A1:C1")
    for col, text in enumerate(DMM_HEADER, start=1):
        ws.cell(row=3, column=col, value=text)
    for r, (v, cur, note) in enumerate(dmm_rows(), start=4):
        ws.cell(row=r, column=1, value=v)
        ws.cell(row=r, column=2, value=cur)
        if note is not None:
            ws.cell(row=r, column=3, value=note)
    ws.column_dimensions["A"].width = 12
    ws.column_dimensions["B"].width = 12
    ws.column_dimensions["C"].width = 14
    cond = wb.create_sheet(DMM_COND_SHEET)
    for row in DMM_CONDITIONS:
        cond.append(list(row))
    cond.column_dimensions["A"].width = 12
    cond.column_dimensions["B"].width = 40
    fixed = datetime(2026, 11, 5, 0, 0, 0)
    wb.properties.creator = "ChipLens synth.generate"
    wb.properties.created = fixed
    wb.properties.modified = fixed
    wb.save(path)


# ---------------------------------------------------------------------------
# golden
# ---------------------------------------------------------------------------
def _s(tu: int) -> float:
    """TU_S integer -> seconds, rounded to 1 fs so JSON shows clean decimals."""
    return round(tu * TU_S, 15)


def _edge_lists(bits: str, obits: str, spec: OutputSpec, offset_tu: int) -> dict[str, Any]:
    din = in_transitions(bits)
    dout = out_transitions(obits, spec)
    return {
        "time_offset_s": _s(offset_tu),
        "clk_rise_s": [_s(x + offset_tu) for x in clk_rise_tu()],
        "clk_fall_s": [_s(x + offset_tu) for x in clk_fall_tu()],
        "in_rise_s": [_s(tr.t50_tu + offset_tu) for tr in din if tr.rising],
        "in_fall_s": [_s(tr.t50_tu + offset_tu) for tr in din if not tr.rising],
        "out_rise_s": [_s(tr.t50_tu + offset_tu) for tr in dout if tr.rising],
        "out_fall_s": [_s(tr.t50_tu + offset_tu) for tr in dout if not tr.rising],
    }


def _rel(value: float, unit: str, rel_tol_pct: float, **extra: Any) -> dict[str, Any]:
    return {"value": value, "unit": unit, "rel_tol_pct": rel_tol_pct, **extra}


def golden_dict() -> dict[str, Any]:
    """Everything an answer check needs: parameters, bits, exact crossing times, D11 answer table."""
    bits = prbs7()
    obits_err = output_bits(bits, error=True)
    in_r, in_f = count_transitions(bits)
    err_r, err_f = count_transitions(obits_err)
    tau = scope_tau()
    base_ok = idd_base_current(tau, out_transitions(bits, SCOPE_OUT))
    base_err = idd_base_current(tau, out_transitions(obits_err, SCOPE_OUT))
    dev = {
        "tplh": (6.0 - 4.5) / 4.5 * 100,
        "tphl": (5.5 - 4.2) / 4.2 * 100,
        "rise_time": (3.0 - 2.0) / 2.0 * 100,
        "fall_time": (2.5 - 1.8) / 1.8 * 100,
        "voh": (1.75 - 1.80) / 1.80 * 100,
    }
    d11_dev = {"tplh": 33.3, "tphl": 31.0, "rise_time": 50.0, "fall_time": 38.9, "voh": -2.8}

    def out_params(spec: OutputSpec) -> dict[str, float]:
        return {
            "tplh_s": _s(spec.tplh_tu),
            "tphl_s": _s(spec.tphl_tu),
            "rise_10_90_s": spec.rise_s,
            "fall_10_90_s": spec.fall_s,
            "rise_full_ramp_s": spec.rise_s * RAMP_FULL_FACTOR,
            "fall_full_ramp_s": spec.fall_s * RAMP_FULL_FACTOR,
            "voh_v": spec.voh_v,
            "vol_v": spec.vol_v,
        }

    return {
        "description": "ChipLens synthetic data answer key (docs/decisions.md D11). Times in seconds on "
        "each file's own time axis (scope t = tau - 2 us, sim t = tau). Cycles are 1-based.",
        "generator": "python -m synth.generate",
        "seed": SEED,
        "files": {k: v for k, v in FILE_NAMES.items() if k != "golden"},
        "setup": {
            "channel_map": [
                {"channel_id": "CH1", "role": "CLK"},
                {"channel_id": "CH2", "role": "IN"},
                {"channel_id": "CH3", "role": "OUT"},
                {"channel_id": "CH4", "role": "IDD"},
            ],
            "paths": [
                {"name": "Buffer", "input_channel": "CH2", "output_channel": "CH3", "polarity": "non_inverting"}
            ],
            "sim_mapping": {"v(clk)": "CH1", "v(in)": "CH2", "v(out)": "CH3"},
            "logic_vdd_v": LOGIC_VDD_V,
            "scope_columns": {"time": "Time(s)", "CH1": "CH1(V)", "CH2": "CH2(V)", "CH3": "CH3(V)", "CH4": "CH4(A)"},
            "dmm": {"sheet": DMM_SHEET, "x_column": DMM_HEADER[0], "y_column": DMM_HEADER[1],
                    "x_scale": 1.0, "y_scale": 1e-6, "sweep_name": "DMM"},
        },
        "params": {
            "n_bits": N_BITS,
            "prbs": {"polynomial": "x^7+x^6+1", "seed": PRBS7_SEED,
                     "lfsr": "newbit = b6 ^ b5; state = ((state << 1) | newbit) & 0x7F; output = newbit"},
            "clk": {
                "frequency_hz": 1e7, "period_s": 1e-7, "low_v": LOGIC_LOW_V, "high_v": LOGIC_HIGH_V,
                "rise_10_90_s": CLK_IN_EDGE_S, "fall_10_90_s": CLK_IN_EDGE_S,
                "full_ramp_s": CLK_IN_EDGE_S * RAMP_FULL_FACTOR, "initial": "low",
                "rise50_tau_s": "25.03 ns + 100k ns (k = 0..39)", "fall50_tau_s": "75.03 ns + 100k ns (k = 0..39)",
            },
            "in": {
                "low_v": LOGIC_LOW_V, "high_v": LOGIC_HIGH_V, "rise_10_90_s": CLK_IN_EDGE_S,
                "fall_10_90_s": CLK_IN_EDGE_S, "full_ramp_s": CLK_IN_EDGE_S * RAMP_FULL_FACTOR,
                "timing": "bit0 from the start; bit k (k >= 1) 50 % crossing at CLK falling k-1 "
                          "(tau = 75.03 + 100(k-1) ns)",
            },
            "out_scope": out_params(SCOPE_OUT),
            "out_sim": out_params(SIM_OUT),
            "out_rule": "o = IN bits (error file: o[36] inverted = cycle 37); OUT 50 % crossing = CLK falling "
                        "crossing where o changes + tpLH (0->1) / tpHL (1->0); linear ramp centred on it",
            "ringing": {
                "frequency_hz": RING_FREQ_HZ, "decay_tau_s": RING_TAU_S, "peak_fraction_of_swing": RING_PEAK_FRAC,
                "unit_peak": ringing_unit_peak(),
                "amplitude_clk_in_v": ringing_amplitude(LOGIC_HIGH_V - LOGIC_LOW_V),
                "amplitude_out_v": ringing_amplitude(SCOPE_OUT.voh_v - SCOPE_OUT.vol_v),
                "applies_to": ["CH1", "CH2", "CH3"], "sim": False,
            },
            "noise": {"voltage_sigma_v": NOISE_V_SIGMA, "current_sigma_a": NOISE_I_SIGMA,
                      "rng": "numpy default_rng(seed); draw order CH1, CH2, CH3, CH4", "sim": False},
            "idd": {
                "mean_pre_noise_a": IDD_MEAN_A, "spike_peak_a": IDD_SPIKE_PEAK_A,
                "spike_sigma_s": IDD_SPIKE_SIGMA_S, "spike_at": "every OUT 50 % crossing",
                "base_current_a": base_ok, "base_current_err_a": base_err,
            },
            "scope": {
                "sample_interval_s": SCOPE_DT_S, "n_points": SCOPE_N, "t0_s": SCOPE_T0_S,
                "t_last_s": round((SCOPE_N - 1 - SCOPE_PRE_N) * SCOPE_DT_S, 15),
                "columns": list(SCOPE_HEADER), "metadata_lines": 4, "header_row": 4, "encoding": "utf-8",
                "roles": {"CH1": "CLK", "CH2": "IN", "CH3": "OUT", "CH4": "IDD"},
            },
            "sim": {
                "sample_interval_s": SIM_DT_S, "n_points": SIM_N, "t0_s": 0.0,
                "t_last_s": round((SIM_N - 1) * SIM_DT_S, 15), "header": list(SIM_HEADER),
                "delimiter": "whitespace", "format": "ngspice wrdata (wr_vecnames on, wr_singlescale off)",
                "idd": None,
            },
            "dmm": {
                "sheet": DMM_SHEET, "title": DMM_TITLE, "title_merge": "A1:C1", "header_row_1based": 3,
                "data_rows_1based": [4, 14], "header": list(DMM_HEADER),
                "formula": "I_uA = round(1.5 * exp((V - 1.8) / 0.25), 4)",
                "rows": [{"v": v, "i_ua": cur, "note": note} for v, cur, note in dmm_rows()],
                "conditions_sheet": DMM_COND_SHEET,
            },
        },
        "bits": bits,
        "bits_err": obits_err,
        "transitions": {
            "in_rise": in_r, "in_fall": in_f,
            "out_rise": in_r, "out_fall": in_f,
            "out_err_rise": err_r, "out_err_fall": err_f,
            "clk_rise": N_BITS, "clk_fall": N_BITS,
        },
        "edges": {
            "scope": _edge_lists(bits, bits, SCOPE_OUT, SCOPE_T0_TU),
            "scope_err": _edge_lists(bits, obits_err, SCOPE_OUT, SCOPE_T0_TU),
            "sim": _edge_lists(bits, bits, SIM_OUT, 0),
        },
        "answers": {
            "scope": {
                "tplh": _rel(6.0e-9, "s", 3.0, check=["mean", "worst"]),
                "tphl": _rel(5.5e-9, "s", 3.0, check=["mean", "worst"]),
                "tpd": _rel(6.0e-9, "s", 3.0, check=["worst"]),
                "rise_time": _rel(3.0e-9, "s", 3.0, check=["mean", "worst"]),
                "fall_time": _rel(2.5e-9, "s", 3.0, check=["mean", "worst"]),
                "voh": _rel(1.75, "V", 1.0),
                "vol": {"value": 0.05, "unit": "V", "rel_tol_pct": 1.0, "abs_tol": 0.0005},
                "period": _rel(1e-7, "s", 1.0),
                "frequency": _rel(1e7, "Hz", 1.0),
                "duty_cycle": _rel(50.0, "%", 1.0),
                "setup_slack": _rel(44.0e-9, "s", 3.0, check=["worst"]),
                "hold_slack": _rel(55.5e-9, "s", 3.0, check=["worst"]),
                "idd_avg": _rel(120e-6, "A", 1.0),
                "avg_power": _rel(216e-6, "W", 1.0, logic_vdd_v=LOGIC_VDD_V),
                "match_rate": {"value": 100.0, "unit": "%", "exact": True, "matched_cycles": 40,
                               "compared_cycles": 40, "mismatch_cycles": [], "first_mismatch": None},
            },
            "scope_err": {
                "match_rate": {"value": 97.5, "unit": "%", "exact": True, "matched_cycles": 39,
                               "compared_cycles": 40, "mismatch_cycles": [ERR_CYCLE],
                               "first_mismatch": ERR_CYCLE, "expected_bit": bits[ERR_CYCLE - 1],
                               "measured_bit": obits_err[ERR_CYCLE - 1]},
                "tplh": _rel(6.0e-9, "s", 3.0, check=["mean", "worst"], note="same as normal file"),
                "tphl": _rel(5.5e-9, "s", 3.0, check=["mean", "worst"], note="same as normal file"),
            },
            "sim": {
                "tplh": _rel(4.5e-9, "s", 3.0),
                "tphl": _rel(4.2e-9, "s", 3.0),
                "rise_time": _rel(2.0e-9, "s", 3.0),
                "fall_time": _rel(1.8e-9, "s", 3.0),
                "voh": _rel(1.80, "V", 1.0),
                "vol": {"value": 0.0, "unit": "V", "abs_tol": 0.0005},
                "period": _rel(1e-7, "s", 1.0),
                "duty_cycle": _rel(50.0, "%", 1.0),
            },
            "dmm": {"iddq": _rel(1.5e-6, "A", 0.5, logic_vdd_v=LOGIC_VDD_V, sweep_name="DMM")},
            "sim_deviation_pct": {
                k: {"value": round(v, 4), "d11_rounded": d11_dev[k], "abs_tol_pp": 2.0} for k, v in dev.items()
            },
            "demo_judgment": {
                "settings": {"logic_vdd_v": LOGIC_VDD_V, "marginal_threshold_pct": 10.0, "sim_tolerance_pct": 20.0},
                "specs": [
                    {"metric_id": "tpd", "max": 8e-9, "verdict": "PASS", "margin_pct": 25.0, "abs_tol_pp": 2.0},
                    {"metric_id": "rise_time", "max": 4e-9, "verdict": "PASS", "margin_pct": 25.0, "abs_tol_pp": 2.0},
                    {"metric_id": "voh", "min": 1.6, "verdict": "MARGINAL", "margin_pct": 9.375, "abs_tol_pp": 2.0},
                    {"metric_id": "iddq", "max": 2.5e-6, "verdict": "PASS", "margin_pct": 40.0, "abs_tol_pp": 2.0},
                ],
                "card_verdicts": {"pass": 4, "marginal": 1, "fail": 0},
                "note": "judgment uses the worst value, so tpd/rise margins come out slightly below 25 % "
                        "(about 24 %) because of the 10 mV noise",
            },
            "bandwidth": {
                "500e6": {"limit_s": 1.4e-9, "warnings": []},
                "100e6": {"limit_s": 7e-9, "warnings": ["rise_time", "fall_time"]},
            },
        },
    }


def golden_json_text() -> str:
    return json.dumps(golden_dict(), indent=2, ensure_ascii=False) + "\n"


# ---------------------------------------------------------------------------
# entry point
# ---------------------------------------------------------------------------
def _write_text(path: Path, text: str) -> None:
    path.write_bytes(text.encode("utf-8"))


def write_all(out_dir: Path | str = DEFAULT_OUT_DIR) -> dict[str, Path]:
    """Generate all five files into out_dir. Returns {key: path}."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    bits = prbs7()
    rises, falls = count_transitions(bits)
    assert rises >= 8 and falls >= 8, f"PRBS7 needs >= 8 rises and falls, got {rises}/{falls}"
    paths = {k: out / v for k, v in FILE_NAMES.items()}
    _write_text(paths["scope"], scope_csv_text(scope_waveforms(error=False)))
    _write_text(paths["scope_err"], scope_csv_text(scope_waveforms(error=True)))
    _write_text(paths["sim"], sim_text(sim_waveforms()))
    write_dmm_xlsx(paths["dmm"])
    _write_text(paths["golden"], golden_json_text())
    return paths


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate ChipLens synthetic data (decisions D11).")
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR), help="output directory")
    args = parser.parse_args(argv)
    paths = write_all(args.out_dir)
    bits = prbs7()
    rises, falls = count_transitions(bits)
    print(f"bits={bits} (0->1: {rises}, 1->0: {falls})")
    for p in paths.values():
        print(f"wrote {p} ({p.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
