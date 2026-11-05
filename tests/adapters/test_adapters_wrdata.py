"""ngspice wrdata (space separated, repeated time columns) + sim re-keying to measured channel_ids."""

from __future__ import annotations

import numpy as np
import pytest

from core.adapters import preview_file, read_table, suggest_sim_mapping, to_waveforms
from core.models import (
    ChannelConversion,
    ChannelInfo,
    ChannelMap,
    FileKind,
    MeasurementSet,
    Path,
    ReadOptions,
    SessionInfo,
    TimeAxisSpec,
    WarningCode,
)
from synth import generate as g

CMAP = ChannelMap(
    channels=[
        ChannelInfo(channel_id="CH1", role="CLK"),
        ChannelInfo(channel_id="CH2", role="IN"),
        ChannelInfo(channel_id="CH3", role="OUT"),
        ChannelInfo(channel_id="CH4", role="IDD"),
    ]
)


def test_sim_preview_dedups_time_columns(synth_bytes):
    raw = synth_bytes["synth_sim.csv"]
    p = preview_file(raw, "synth_sim.csv")
    assert p.kind is FileKind.CSV
    assert p.options.delimiter == " "
    assert p.options.header_row == 0
    assert p.raw_rows[0] == ["time", "v(clk)", "time", "v(in)", "time", "v(out)"]
    assert [c.name for c in p.columns] == ["time", "v(clk)", "v(in)", "v(out)"]
    assert [c.si_unit for c in p.columns] == [None, "V", "V", "V"]  # v(...) -> V, scale 1
    assert [c.unit_text for c in p.columns] == [None, None, None, None]
    assert [c.base_name for c in p.columns] == ["time", "v(clk)", "v(in)", "v(out)"]
    assert p.time_candidates[0] == "time"
    assert len(p.head_rows[0]) == 4
    assert p.notices == []


def test_sim_to_waveforms_rekeyed_to_measured_ids(synth_bytes, golden):
    raw = synth_bytes["synth_sim.csv"]
    table = read_table(raw, "synth_sim.csv", preview_file(raw, "synth_sim.csv").options)
    assert table.data.shape == (40001, 4)
    mapping = suggest_sim_mapping(table.columns, CMAP)
    assert mapping == golden["setup"]["sim_mapping"] == {"v(clk)": "CH1", "v(in)": "CH2", "v(out)": "CH3"}
    convs = [
        ChannelConversion(column=col, channel_id=cid, quantity="V", scale=table.column(col).scale)
        for col, cid in mapping.items()
        if cid is not None
    ]
    res = to_waveforms(table, TimeAxisSpec(column="time"), convs)
    assert res.notices == []
    ref = g.sim_waveforms()
    for w, col in zip(res.waveforms, mapping, strict=True):
        assert w.n_samples == 40001
        assert w.sample_interval_s == pytest.approx(0.1e-9, rel=1e-6)
        np.testing.assert_allclose(w.values, ref[col], rtol=1e-8, atol=1e-12)
        assert w.source_column == col
    sim_set = MeasurementSet(
        session=SessionInfo(source="sim"),
        channel_map=CMAP,
        paths=[Path(name="Buffer", input_channel="CH2", output_channel="CH3")],
        waveforms=res.waveforms,
    )
    assert sim_set.waveform("CH3") is not None and sim_set.waveform("CH4") is None


def test_repeated_time_column_mismatch_kept_with_notice():
    raw = b"time v(a) time v(b)\n0 1 0 2\n1e-9 1 1.5e-9 2\n2e-9 1 2e-9 2\n"
    p = preview_file(raw, "mismatch.txt")
    assert p.kind is FileKind.TEXT
    assert [c.name for c in p.columns] == ["time", "v(a)", "time_2", "v(b)"]
    assert [n.code for n in p.notices] == [WarningCode.TIME_COLUMN_MISMATCH]
    t = read_table(raw, "mismatch.txt", p.options)
    assert [n.code for n in t.notices] == [WarningCode.TIME_COLUMN_MISMATCH]
    # equal within relative 1e-9 -> dropped
    raw2 = b"time v(a) time v(b)\n0 1 0 2\n1e-9 1 1.0000000000001e-9 2\n"
    assert [c.name for c in read_table(raw2, "ok.txt", ReadOptions(header_row=0)).columns] == ["time", "v(a)", "v(b)"]


def test_wrdata_with_unit_time_header_and_tabs():
    raw = b"Time(s)\tV(out)\tTime(s)\tI(VDD)\n0\t0\t0\t1e-6\n1e-10\t0.5\t1e-10\t2e-6\n"
    p = preview_file(raw, "sim.tsv")
    assert p.options.delimiter == "\t"
    assert [c.name for c in p.columns] == ["Time(s)", "V(out)", "I(VDD)"]
    assert [c.si_unit for c in p.columns] == ["s", "V", "A"]
    assert suggest_sim_mapping(p.columns, CMAP) == {"V(out)": "CH3", "I(VDD)": "CH4"}
