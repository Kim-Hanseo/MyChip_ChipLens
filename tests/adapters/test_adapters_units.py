"""split_header_unit and ColumnInfo unit extraction (µ U+00B5, μ U+03BC, u)."""

from __future__ import annotations

import pytest

from core.adapters import preview_file, split_header_unit


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        ("CH1(V)", ("CH1", "V")),
        ("Time(s)", ("Time", "s")),
        ("Time (s)", ("Time", "s")),
        ("전류(µA)", ("전류", "µA")),
        ("전류(μA)", ("전류", "μA")),
        ("전류(uA)", ("전류", "uA")),
        ("I [mA]", ("I", "mA")),
        ("CH2 [mV]", ("CH2", "mV")),
        ("Freq(MHz)", ("Freq", "MHz")),
        ("Duty(%)", ("Duty", "%")),
        ("  Time(ns)  ", ("Time", "ns")),
        ("V(out)", ("V(out)", None)),
        ("v(clk)", ("v(clk)", None)),
        ("v(a)", ("v(a)", None)),  # SPICE node "a", not ampere
        ("i(vdd)", ("i(vdd)", None)),
        ("온도(°C)", ("온도(°C)", None)),
        ("CH1", ("CH1", None)),
        ("time", ("time", None)),
        ("", ("", None)),
    ],
)
def test_split_header_unit(header, expected):
    assert split_header_unit(header) == expected


def test_micro_variants_give_same_scale():
    raw = "t(ns),a(µA),b(μA),c(uA),d(mA),e(nA),f(pA),g(kV)\n1,1,1,1,1,1,1,1\n2,2,2,2,2,2,2,2\n".encode()
    p = preview_file(raw, "u.csv")
    got = {c.base_name: (c.si_unit, c.scale) for c in p.columns}
    assert got == {
        "t": ("s", 1e-9),
        "a": ("A", 1e-6),
        "b": ("A", 1e-6),
        "c": ("A", 1e-6),
        "d": ("A", 1e-3),
        "e": ("A", 1e-9),
        "f": ("A", 1e-12),
        "g": ("V", 1e3),
    }
    assert [c.unit_text for c in p.columns][1:4] == ["µA", "μA", "uA"]


def test_spice_columns_get_si_unit():
    p = preview_file(b"time v(out) i(vdd)\n0 1 2\n1 1 2\n", "s.txt")
    assert [(c.base_name, c.si_unit, c.scale) for c in p.columns] == [
        ("time", None, 1.0),
        ("v(out)", "V", 1.0),
        ("i(vdd)", "A", 1.0),
    ]
