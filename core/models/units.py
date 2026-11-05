"""Unit parsing and display formatting (pure functions, decisions D2/D9)."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from .metrics import METRICS

if TYPE_CHECKING:
    from .inputs import Spec

MICRO = "µ"  # µ used in all output text

_PREFIX_SCALE: dict[str, float] = {
    "p": 1e-12,
    "n": 1e-9,
    "u": 1e-6,
    "µ": 1e-6,  # µ micro sign
    "μ": 1e-6,  # μ greek mu
    "m": 1e-3,
    "": 1.0,
    "k": 1e3,
    "K": 1e3,
    "M": 1e6,
    "G": 1e9,
}

# accepted spellings of base units -> canonical SI symbol
_BASE_UNITS: dict[str, str] = {
    "s": "s", "sec": "s",
    "V": "V", "v": "V",
    "A": "A", "a": "A",
    "W": "W", "w": "W",
    "Hz": "Hz", "hz": "Hz", "HZ": "Hz",
    "%": "%",
}

_DISPLAY_PREFIXES: list[tuple[float, str]] = [
    (1e9, "G"), (1e6, "M"), (1e3, "k"), (1.0, ""), (1e-3, "m"), (1e-6, MICRO), (1e-9, "n"), (1e-12, "p"),
]


def parse_unit(text: str | None) -> tuple[str, float] | None:
    """Parse a unit string such as "µA", "μA", "uA", "mV", "ns", "MHz", "V".

    Returns (si_unit, scale) so that si_value = raw_value * scale, or None if unknown.
    """
    if text is None:
        return None
    t = text.strip()
    if not t:
        return None
    if t in _BASE_UNITS:
        return _BASE_UNITS[t], 1.0
    for base_txt, base in _BASE_UNITS.items():
        if t.endswith(base_txt):
            prefix = t[: -len(base_txt)]
            if prefix in _PREFIX_SCALE and prefix != "":
                if base == "%":
                    return None
                return base, _PREFIX_SCALE[prefix]
    return None


def format_number(x: float, sig: int = 3) -> str:
    """Format with `sig` significant digits, keeping trailing zeros (1.5 -> "1.50")."""
    if x == 0 or not math.isfinite(x):
        return f"{0.0:.{sig - 1}f}" if x == 0 else str(x)
    xr = float(f"{x:.{sig - 1}e}")
    exp = math.floor(math.log10(abs(xr)))
    decimals = max(0, sig - 1 - exp)
    return f"{xr:.{decimals}f}"


def format_si(value: float | None, unit: str, sig: int = 3) -> str:
    """Auto-prefixed SI text, e.g. format_si(6.03e-9, "s") -> "6.03 ns". None -> "—"."""
    if value is None:
        return "—"
    if unit == "%":
        return f"{format_number(value, sig)} %"
    a = abs(value)
    if a == 0:
        return f"{format_number(0.0, sig)} {unit}"
    for scale, prefix in _DISPLAY_PREFIXES:
        if a >= scale * 0.9995 or scale == 1e-12:
            return f"{format_number(value / scale, sig)} {prefix}{unit}"
    return f"{format_number(value, sig)} {unit}"  # pragma: no cover


def format_metric_value(metric_id: str, value: float | None, sig: int = 3) -> str:
    """Catalog display: METRICS[metric_id].display_unit, 3 significant digits ("6.03 ns", "1.50 µA")."""
    if value is None:
        return "—"
    m = METRICS[metric_id]
    return f"{format_number(value * m.display_scale, sig)} {m.display_unit}"


def format_pct(x: float | None, signed: bool = False) -> str:
    """Margin/deviation text with one decimal and no space: "9.4%", signed -> "+33.3%"."""
    if x is None:
        return "—"
    return f"{x:+.1f}%" if signed else f"{x:.1f}%"


def format_spec(spec: Spec) -> str:
    """Spec bound text in display units: "≤ 8.00 ns", "≥ 1.60 V", "1.60–1.90 V"."""
    m = METRICS[spec.metric_id]
    if spec.min is not None and spec.max is not None:
        lo = format_number(spec.min * m.display_scale)
        hi = format_number(spec.max * m.display_scale)
        return f"{lo}–{hi} {m.display_unit}"
    if spec.max is not None:
        return f"≤ {format_metric_value(spec.metric_id, spec.max)}"
    return f"≥ {format_metric_value(spec.metric_id, spec.min)}"
