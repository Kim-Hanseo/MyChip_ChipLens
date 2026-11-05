"""Header text -> (base name, unit) and ColumnInfo construction."""

from __future__ import annotations

import re

from core.models import ColumnInfo, parse_unit

# "CH1(V)", "Time (s)", "전류(µA)", "I [mA]": trailing (...) or [...] group
_UNIT_RE = re.compile(r"^(?P<base>.*?)\s*(?:\((?P<paren>[^()]*)\)|\[(?P<brack>[^\[\]]*)\])\s*$")
# SPICE vector names: v(node), i(source) -- no space between the letter and "("
_SPICE_RE = re.compile(r"^(?P<kind>[vViI])\(.+\)$")
_SPICE_QUANTITY = {"v": "V", "i": "A"}

TIME_NAMES = frozenset({"time", "t", "시간"})


def split_header_unit(header: str) -> tuple[str, str | None]:
    """Split a header into (base_name, unit_text).

    "CH1(V)" -> ("CH1", "V"), "Time(s)" -> ("Time", "s"), "전류(µA)" -> ("전류", "µA"),
    "I [mA]" -> ("I", "mA"). If the bracket content is not a unit (core.models.parse_unit), the
    header is returned unchanged with no unit: "V(out)" -> ("V(out)", None).
    """
    h = header.strip()
    m = _UNIT_RE.match(h)
    if m is None:
        return h, None
    inner = m.group("paren") if m.group("paren") is not None else m.group("brack")
    inner = (inner or "").strip()
    base = m.group("base").strip()
    parsed = parse_unit(inner)
    if parsed is None or not base:
        return h, None
    # SPICE node names that happen to look like units, e.g. v(a) or v(s): keep as a SPICE vector
    if _SPICE_RE.match(h) and base.lower() in _SPICE_QUANTITY and parsed[0] != _SPICE_QUANTITY[base.lower()]:
        return h, None
    return base, inner


def spice_quantity(header: str) -> str | None:
    """"V" for v(...), "A" for i(...), else None."""
    m = _SPICE_RE.match(header.strip())
    return _SPICE_QUANTITY[m.group("kind").lower()] if m else None


def build_column_info(name: str, header: str, numeric: bool) -> ColumnInfo:
    """ColumnInfo for one column: unit from the header, SI unit + scale via parse_unit."""
    header = header.strip()
    if header:
        base, unit = split_header_unit(header)
    else:
        base, unit = name, None
    si_unit: str | None = None
    scale = 1.0
    parsed = parse_unit(unit) if unit is not None else None
    if parsed is not None:
        si_unit, scale = parsed
    elif header and (q := spice_quantity(header)) is not None:
        si_unit = q
    return ColumnInfo(
        name=name,
        header=header,
        base_name=base or name,
        unit_text=unit,
        si_unit=si_unit,
        scale=scale,
        numeric=numeric,
    )


def is_time_like(col: ColumnInfo) -> bool:
    """True if the column is in seconds or is named time / t / 시간."""
    return col.si_unit == "s" or col.base_name.strip().lower() in TIME_NAMES
