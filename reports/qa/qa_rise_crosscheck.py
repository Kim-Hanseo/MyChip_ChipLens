"""QA: independent rise/fall 10-90 % measurement straight from synth_scope.csv (true levels 0.05/1.75 V),
to judge whether core's rise mean 2.984 ns (-> sim deviation +49.2 % instead of +50 %) is data noise or bias.
Run: .venv/Scripts/python reports/qa/qa_rise_crosscheck.py"""
import io, sys
from pathlib import Path
import numpy as np
ROOT = Path(__file__).resolve().parents[2]
lines = (ROOT / "synth/data/synth_scope.csv").read_text(encoding="utf-8").splitlines()
d = np.loadtxt(io.StringIO("\n".join(lines[5:])), delimiter=",")
t, y = d[:, 0] + 2e-6, d[:, 3]
bits = ""; s = 0x7F
for _ in range(40):
    nb = ((s >> 6) ^ (s >> 5)) & 1; s = ((s << 1) | nb) & 0x7F; bits += str(nb)
lo, hi = 0.05, 1.75
def cross(level, t0, t1, rising):
    m = (t >= t0) & (t <= t1); tt, yy = t[m], y[m]
    idx = [i for i in range(len(yy) - 1) if (yy[i] < level <= yy[i + 1]) if rising] if rising else \
          [i for i in range(len(yy) - 1) if (yy[i] > level >= yy[i + 1])]
    # all crossings in the window; return mean and the first/last to show noise multiplicity
    xs = [tt[i] + (level - yy[i]) * (tt[i + 1] - tt[i]) / (yy[i + 1] - yy[i]) for i in idx]
    return xs
rises, falls = [], []
for k in range(1, 40):
    if bits[k] == bits[k - 1]:
        continue
    tf = 75.03e-9 + 100e-9 * (k - 1)
    if bits[k] == "1":
        c = tf + 6.0e-9; x10 = cross(lo + 0.1 * (hi - lo), c - 3e-9, c, True); x90 = cross(lo + 0.9 * (hi - lo), c, c + 3e-9, True)
        rises.append((x90[0] - x10[-1], len(x10), len(x90)))
    else:
        c = tf + 5.5e-9; x90 = cross(lo + 0.9 * (hi - lo), c - 3e-9, c, False); x10 = cross(lo + 0.1 * (hi - lo), c, c + 3e-9, False)
        falls.append((x10[0] - x90[-1], len(x90), len(x10)))
r = np.array([v[0] for v in rises]); f = np.array([v[0] for v in falls])
print("rise per edge [ns]:", np.round(r * 1e9, 4), "crossing multiplicity:", [v[1:] for v in rises])
print(f"rise mean {r.mean()*1e9:.4f} ns  max {r.max()*1e9:.4f} ns  -> sim dev {(r.mean()-2e-9)/2e-9*100:+.2f} %")
print("fall per edge [ns]:", np.round(f * 1e9, 4))
print(f"fall mean {f.mean()*1e9:.4f} ns  max {f.max()*1e9:.4f} ns  -> sim dev {(f.mean()-1.8e-9)/1.8e-9*100:+.2f} %")
