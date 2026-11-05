"""Generic CSV/text reader + Normalizer: synth scope files, cp949, metadata skip, probe factor, notices."""

from __future__ import annotations

import numpy as np
import pytest

from core.adapters import preview_file, read_table, to_waveforms
from core.models import (
    ChannelConversion,
    FileKind,
    RawTable,
    ReadOptions,
    TimeAxisSpec,
    WarningCode,
)
from synth import generate as g


def _codes(notices) -> list[str]:
    return [n.code for n in notices]


def _default_conversions(table: RawTable, skip: str) -> list[ChannelConversion]:
    return [
        ChannelConversion(column=c.name, channel_id=c.base_name, quantity=c.si_unit, scale=c.scale)
        for c in table.columns
        if c.name != skip
    ]


@pytest.mark.parametrize("name", ["synth_scope.csv", "synth_scope_err.csv"])
def test_scope_preview_skips_metadata(synth_bytes, name):
    p = preview_file(synth_bytes[name], name)
    assert p.kind is FileKind.CSV
    assert p.options.encoding == "utf-8-sig"
    assert p.options.delimiter == ","
    assert p.options.header_row == 4  # 4 metadata lines skipped
    assert p.options.data_start_row is None  # = header_row + 1
    assert p.sheets == []
    assert p.raw_rows[0] == ["Model", "ChipLens-SynthScope"]
    assert p.raw_rows[4] == ["Time(s)", "CH1(V)", "CH2(V)", "CH3(V)", "CH4(A)"]
    assert len(p.raw_rows) == 30
    assert [c.name for c in p.columns] == ["Time(s)", "CH1(V)", "CH2(V)", "CH3(V)", "CH4(A)"]
    assert [c.base_name for c in p.columns] == ["Time", "CH1", "CH2", "CH3", "CH4"]
    assert [c.si_unit for c in p.columns] == ["s", "V", "V", "V", "A"]
    assert all(c.numeric and c.scale == 1.0 for c in p.columns)
    assert p.time_candidates[0] == "Time(s)"
    assert len(p.head_rows) == 10 and p.head_rows[0][0] == "-2.0000000000E-06"
    assert p.notices == []


@pytest.mark.parametrize("error", [False, True])
def test_scope_to_waveforms_matches_generator(synth_bytes, error):
    name = "synth_scope_err.csv" if error else "synth_scope.csv"
    p = preview_file(synth_bytes[name], name)
    table = read_table(synth_bytes[name], name, p.options)
    assert table.data.shape == (20000, 5)
    assert all(str(dt) == "float64" for dt in table.data.dtypes)
    res = to_waveforms(table, TimeAxisSpec(column="Time(s)"), _default_conversions(table, "Time(s)"))
    assert res.notices == []
    assert [w.channel_id for w in res.waveforms] == ["CH1", "CH2", "CH3", "CH4"]
    assert [w.quantity for w in res.waveforms] == ["V", "V", "V", "A"]
    ref = g.scope_waveforms(error=error)
    for w in res.waveforms:
        assert w.n_samples == 20000
        assert w.sample_interval_s == pytest.approx(0.2e-9, rel=1e-6)
        assert w.time_s[0] == -2.0e-6
        np.testing.assert_allclose(w.time_s, ref["t"], rtol=0, atol=1e-18)
        np.testing.assert_allclose(w.values, ref[w.channel_id], rtol=1e-6, atol=1e-12)
        assert w.source_column == f"{w.channel_id}({w.quantity})"
        assert w.source_unit == w.quantity.value
    idd = res.waveforms[3].values
    assert float(np.mean(idd)) == pytest.approx(120e-6, rel=1e-2)


def test_read_table_with_user_options_overrides_guess(synth_bytes):
    raw = synth_bytes["synth_scope.csv"]
    # explicit data_start_row: rows 5..9 are skipped
    t = read_table(raw, "synth_scope.csv", ReadOptions(header_row=4, data_start_row=10))
    assert len(t.data) == 20000 - 5
    p = preview_file(raw, "synth_scope.csv", ReadOptions(header_row=None, data_start_row=5))
    assert [c.name for c in p.columns] == ["col0", "col1", "col2", "col3", "col4"]
    assert p.columns[0].header == "" and p.columns[0].base_name == "col0"
    assert p.options.header_row is None and p.options.data_start_row == 5
    with pytest.raises(ValueError):
        read_table(raw, "synth_scope.csv", ReadOptions(header_row=10**6))


def test_cp949_csv_falls_back_with_notice():
    text = "장비,테스트 스코프\n시간(s),전압(mV),전류(µA)\n0,100,1.5\n1e-9,200,2.5\n2e-9,300,3.5\n"
    raw = text.replace("µ", "u").encode("cp949")
    p = preview_file(raw, "한글.csv")
    assert p.options.encoding == "cp949"
    assert _codes(p.notices) == [WarningCode.ENCODING_FALLBACK]
    assert p.options.header_row == 1
    assert [c.name for c in p.columns] == ["시간(s)", "전압(mV)", "전류(uA)"]
    assert [(c.si_unit, c.scale) for c in p.columns] == [("s", 1.0), ("V", 1e-3), ("A", 1e-6)]
    t = read_table(raw, "한글.csv", p.options)
    assert _codes(t.notices) == [WarningCode.ENCODING_FALLBACK]
    res = to_waveforms(
        t,
        TimeAxisSpec(column="시간(s)"),
        [ChannelConversion(column="전압(mV)", channel_id="V1", quantity="V", scale=1e-3)],
    )
    np.testing.assert_allclose(res.waveforms[0].values, [0.1, 0.2, 0.3])
    # explicit encoding works too; a wrong explicit encoding is a Korean ValueError
    assert read_table(raw, "x.csv", ReadOptions(encoding="cp949", header_row=1)).data.shape == (3, 3)
    with pytest.raises(ValueError, match="인코딩"):
        read_table(raw, "x.csv", ReadOptions(encoding="utf-8", header_row=1))


def test_utf8_bom_and_delimiters():
    rows = [["Time(s)", "CH1(V)"], ["0", "1.0"], ["1", "2.0"], ["2", "3.0"]]
    for d in ("\t", ";", ","):
        raw = ("﻿" + "\n".join(d.join(r) for r in rows) + "\n").encode("utf-8")
        p = preview_file(raw, "a.txt")
        assert p.kind is FileKind.TEXT
        assert p.options.delimiter == d
        assert p.options.encoding == "utf-8-sig" and p.notices == []
        assert [c.name for c in p.columns] == ["Time(s)", "CH1(V)"]
    raw = b"  Time(s)   CH1(V)\n  0   1.0\n  1    2.0\n"
    p = preview_file(raw, "ws.dat")
    assert p.options.delimiter == " "
    assert [c.name for c in p.columns] == ["Time(s)", "CH1(V)"]


def test_probe_factor_and_scale():
    raw = b"Time(ns),CH1(mV)\n0,10\n1,20\n2,30\n"
    p = preview_file(raw, "probe.csv")
    t = read_table(raw, "probe.csv", p.options)
    tc, vc = t.columns
    assert (tc.si_unit, tc.scale) == ("s", 1e-9)
    res = to_waveforms(
        t,
        TimeAxisSpec(column=tc.name, scale=tc.scale),
        [ChannelConversion(column=vc.name, channel_id="CH1", quantity="V", scale=vc.scale, probe_factor=10.0)],
    )
    w = res.waveforms[0]
    np.testing.assert_allclose(w.time_s, [0.0, 1e-9, 2e-9])
    np.testing.assert_allclose(w.values, [0.1, 0.2, 0.3])  # 10 mV x 10 = 0.1 V
    assert w.probe_factor == 10.0 and w.source_unit == "mV"


def test_time_from_start_and_interval():
    raw = b"CH1(V),CH2(V)\n0,1\n1,0\n0,1\n"
    t = read_table(raw, "notime.csv", ReadOptions(header_row=0))
    res = to_waveforms(
        t,
        TimeAxisSpec(column=None, start_s=-1e-6, interval_s=1e-9),
        [
            ChannelConversion(column="CH1(V)", channel_id="CH1", quantity="V"),
            ChannelConversion(column="CH2(V)", channel_id="CH2", quantity="V"),
        ],
    )
    for w in res.waveforms:
        np.testing.assert_allclose(w.time_s, [-1e-6, -1e-6 + 1e-9, -1e-6 + 2e-9])


def test_nan_and_non_monotonic_rows_dropped():
    raw = b"t(s),a(V),b(V)\n0,1,1\n1,,2\n2,3,x\n3,4,4\n3,5,5\n2.5,6,6\n4,7,7\n"
    t = read_table(raw, "bad.csv", ReadOptions(header_row=0))
    assert np.isnan(t.data["a(V)"].iloc[1]) and np.isnan(t.data["b(V)"].iloc[2])
    res = to_waveforms(
        t,
        TimeAxisSpec(column="t(s)"),
        [
            ChannelConversion(column="a(V)", channel_id="A", quantity="V"),
            ChannelConversion(column="b(V)", channel_id="B", quantity="V"),
        ],
    )
    assert _codes(res.notices) == [WarningCode.NAN_DROPPED, WarningCode.NON_MONOTONIC_AXIS]
    assert "2개" in res.notices[0].message and "2개" in res.notices[1].message
    np.testing.assert_allclose(res.waveforms[0].time_s, [0, 3, 4])
    np.testing.assert_allclose(res.waveforms[0].values, [1, 4, 7])
    # only channel B selected -> row 1 (NaN only in A) is kept
    res_b = to_waveforms(t, TimeAxisSpec(column="t(s)"), [ChannelConversion(column="b(V)", channel_id="B", quantity="V")])
    np.testing.assert_allclose(res_b.waveforms[0].time_s, [0, 1, 3, 4])


def test_suspicious_range_notice_keeps_waveform():
    raw = b"Time(s),CH1(V),CH4(A)\n0,0.1,0.001\n1e-9,0.2,0.002\n2e-9,0.3,0.003\n"
    t = read_table(raw, "x.csv", ReadOptions(header_row=0))
    res = to_waveforms(
        t,
        TimeAxisSpec(column="Time(s)"),
        [
            ChannelConversion(column="CH1(V)", channel_id="CH1", quantity="V", scale=1e3),  # mistaken kV
            ChannelConversion(column="CH4(A)", channel_id="CH4", quantity="A", probe_factor=1e4),
        ],
    )
    assert _codes(res.notices) == [WarningCode.SUSPICIOUS_RANGE, WarningCode.SUSPICIOUS_RANGE]
    assert [n.channel_id for n in res.notices] == ["CH1", "CH4"]
    assert len(res.waveforms) == 2 and res.waveforms[0].values.max() == pytest.approx(300.0)


def test_errors_are_korean_value_errors():
    raw = b"Time(s),CH1(V),note\n0,1,a\n1e-9,2,b\n"
    t = read_table(raw, "x.csv", ReadOptions(header_row=0))
    assert t.column("note").numeric is False and str(t.data["note"].dtype) == "str"
    with pytest.raises(ValueError, match="없습니다"):
        to_waveforms(t, TimeAxisSpec(column="nope"), [ChannelConversion(column="CH1(V)", channel_id="CH1", quantity="V")])
    with pytest.raises(ValueError, match="숫자 열"):
        to_waveforms(t, TimeAxisSpec(column="Time(s)"), [ChannelConversion(column="note", channel_id="N", quantity="V")])
    with pytest.raises(ValueError, match="중복"):
        to_waveforms(
            t,
            TimeAxisSpec(column="Time(s)"),
            [ChannelConversion(column="CH1(V)", channel_id="X", quantity="V")] * 2,
        )
    one = read_table(b"Time(s),CH1(V)\n0,1\n", "one.csv", ReadOptions(header_row=0))
    with pytest.raises(ValueError, match="2개 이상"):
        to_waveforms(one, TimeAxisSpec(column="Time(s)"), [ChannelConversion(column="CH1(V)", channel_id="CH1", quantity="V")])
    with pytest.raises(ValueError, match="xls"):
        preview_file(b"\xd0\xcf\x11\xe0", "old.xls")
    with pytest.raises(ValueError, match="빈 파일"):
        preview_file(b"", "empty.csv")


def test_headerless_numeric_file_and_duplicate_names():
    p = preview_file(b"0,1\n1,2\n2,3\n", "plain.csv")
    assert p.options.header_row is None and p.options.data_start_row is None
    assert [c.name for c in p.columns] == ["col0", "col1"]
    assert p.time_candidates == ["col0", "col1"]  # both strictly increasing
    p2 = preview_file(b"V,V,,x\n1,2,3,\n4,5,6,\n", "dup.csv")
    assert [c.name for c in p2.columns] == ["V", "V_2", "col2", "x"]
    p3 = preview_file(b"a,b,\n1,2,\n3,4,\n", "trail.csv")  # trailing delimiter -> empty column dropped
    assert [c.name for c in p3.columns] == ["a", "b"]
