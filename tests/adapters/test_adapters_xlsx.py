"""xlsx reader (merged title, blank row, Korean headers with units, sheet choice) + DC sweep."""

from __future__ import annotations

import io

import numpy as np
import pytest
from openpyxl import Workbook

from core.adapters import preview_file, read_table, to_dc_sweep
from core.models import FileKind, ReadOptions, WarningCode


def test_dmm_preview_guesses_header_after_title(synth_bytes):
    raw = synth_bytes["synth_dmm.xlsx"]
    p = preview_file(raw, "synth_dmm.xlsx")
    assert p.kind is FileKind.XLSX
    assert p.sheets == ["DC측정", "조건"]
    assert p.options.sheet == "DC측정"
    assert p.options.encoding is None and p.options.delimiter is None
    assert p.options.header_row == 2  # title (merged A1:C1) + blank row skipped
    assert p.raw_rows[0] == ["멀티미터 DC 측정 — 칩 #1, 25 °C", "", ""]  # merged: value only top-left
    assert p.raw_rows[1] == ["", "", ""]
    assert p.raw_rows[2] == ["전압(V)", "전류(µA)", "비고"]
    assert len(p.raw_rows) == 14
    names = [c.name for c in p.columns]
    assert names == ["전압(V)", "전류(µA)", "비고"]
    cur = p.columns[1]
    assert (cur.base_name, cur.unit_text, cur.si_unit, cur.scale) == ("전류", "µA", "A", 1e-6)
    assert p.columns[2].numeric is False
    assert len(p.head_rows) == 10 and p.head_rows[8] == ["1.8", "1.5", "IDDQ 기준"]
    assert p.time_candidates[0] == "전압(V)"


def test_dmm_to_dc_sweep_iddq_point(synth_bytes):
    raw = synth_bytes["synth_dmm.xlsx"]
    t = read_table(raw, "synth_dmm.xlsx", preview_file(raw, "synth_dmm.xlsx").options)
    assert t.data.shape == (11, 3)
    assert str(t.data["비고"].dtype) == "str"
    y_scale = t.column("전류(µA)").scale
    res = to_dc_sweep(t, "전압(V)", "전류(µA)", y_scale=y_scale, name="DMM")
    assert res.notices == []
    s = res.sweep
    assert s is not None and s.name == "DMM"
    assert (s.x_quantity, s.y_quantity) == ("V", "A")
    assert (s.x_label, s.y_label) == ("전압(V)", "전류(µA)")
    np.testing.assert_allclose(s.x, np.round(np.arange(11) * 0.1 + 1.0, 1))
    assert float(np.interp(1.8, s.x, s.y)) == pytest.approx(1.5e-6, rel=1e-12)
    assert s.y[0] == pytest.approx(0.0611e-6)


def test_conditions_sheet_selection(synth_bytes):
    p = preview_file(synth_bytes["synth_dmm.xlsx"], "synth_dmm.xlsx", ReadOptions(sheet="조건"))
    assert p.options.sheet == "조건" and p.options.header_row == 0
    assert [c.name for c in p.columns] == ["항목", "값"]
    assert p.head_rows[0] == ["칩 ID", "#1"]
    with pytest.raises(ValueError, match="시트"):
        preview_file(synth_bytes["synth_dmm.xlsx"], "synth_dmm.xlsx", ReadOptions(sheet="없는시트"))


def _xlsx(rows: list[list[object]], title: str = "Sheet") -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = title
    for r in rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_dc_sweep_sorts_dedups_and_drops_nan():
    raw = _xlsx(
        [
            ["VDD [V]", "I [mA]"],
            [2.0, 3.0],
            [1.0, 1.0],
            [1.5, None],
            [1.0, 9.0],
            [1.5, 2.0],
        ]
    )
    t = read_table(raw, "sweep.xlsm", ReadOptions(header_row=0))
    assert [(c.base_name, c.unit_text, c.scale) for c in t.columns] == [("VDD", "V", 1.0), ("I", "mA", 1e-3)]
    res = to_dc_sweep(t, "VDD [V]", "I [mA]", y_scale=1e-3, name="S1")
    assert [n.code for n in res.notices] == [WarningCode.NAN_DROPPED, WarningCode.NON_MONOTONIC_AXIS]
    np.testing.assert_allclose(res.sweep.x, [1.0, 1.5, 2.0])
    np.testing.assert_allclose(res.sweep.y, [1e-3, 2e-3, 3e-3])  # duplicate x=1.0 keeps the first row


def test_dc_sweep_empty_returns_none():
    raw = _xlsx([["V(V)", "I(A)"], [1.0, None], [None, 2.0], ["x", "y"]])
    t = read_table(raw, "e.xlsx", ReadOptions(header_row=0))
    res = to_dc_sweep(t, "V(V)", "I(A)")
    assert res.sweep is None
    assert [n.code for n in res.notices] == [WarningCode.NAN_DROPPED]


def test_bad_xlsx_raises_korean_error():
    with pytest.raises(ValueError, match="엑셀"):
        preview_file(b"not a zip file", "broken.xlsx")
