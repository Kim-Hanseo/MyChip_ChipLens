"""Contract tests: mock report round-trip, catalog == decisions D4, model validation, formatters."""

from __future__ import annotations

from pathlib import Path as FsPath

import numpy as np
import pytest
from pydantic import ValidationError

from core.models import (
    METRICS,
    AnalysisReport,
    AnalysisRequest,
    AnalysisSettings,
    ChannelInfo,
    ChannelMap,
    DCSweep,
    ExpectedPattern,
    MeasurementSet,
    Path,
    Role,
    SessionInfo,
    Spec,
    Verdict,
    WarningCode,
    Waveform,
    format_metric_value,
    format_pct,
    format_spec,
    make_result,
    parse_unit,
    result_sort_key,
)

MOCK = FsPath(__file__).parent / "fixtures" / "mock_report.json"

# decisions D4: metric_id -> (category, unit, sim_compare)
D4 = {
    "rise_time": ("timing", "s", True),
    "fall_time": ("timing", "s", True),
    "tplh": ("timing", "s", True),
    "tphl": ("timing", "s", True),
    "tpd": ("timing", "s", False),
    "period": ("timing", "s", True),
    "frequency": ("timing", "Hz", False),
    "duty_cycle": ("timing", "%", True),
    "setup_slack": ("timing", "s", True),
    "hold_slack": ("timing", "s", True),
    "voh": ("dc", "V", True),
    "vol": ("dc", "V", True),
    "idd_avg": ("dc", "A", False),
    "avg_power": ("dc", "W", False),
    "iddq": ("dc", "A", False),
    "match_rate": ("functional", "%", False),
}
D4_AGGREGATE = {
    "rise_time": "max", "fall_time": "max", "tplh": "max", "tphl": "max", "tpd": "max",
    "period": "mean", "duty_cycle": "mean", "setup_slack": "min", "hold_slack": "min",
}


def _load() -> AnalysisReport:
    return AnalysisReport.model_validate_json(MOCK.read_text(encoding="utf-8"))


# ---------- mock report ----------

def test_mock_roundtrip_is_byte_identical():
    r1 = _load()
    j1 = r1.model_dump_json(indent=2)
    r2 = AnalysisReport.model_validate_json(j1)
    assert r2.model_dump_json(indent=2) == j1
    assert r1 == r2
    assert MOCK.read_text(encoding="utf-8").strip() == j1.strip()


def test_mock_matches_demo_state():
    r = _load()
    c = r.cards
    assert (c.verdicts.pass_count, c.verdicts.marginal_count, c.verdicts.fail_count) == (4, 1, 0)
    assert c.worst_margin is not None and c.worst_margin.metric_id == "voh"
    assert round(c.worst_margin.margin_pct, 1) == 9.4 and c.worst_margin.verdict == Verdict.MARGINAL
    assert c.sim_deviation is not None
    top = [(t.metric_id, round(t.deviation_pct, 1)) for t in c.sim_deviation.top]
    assert top == [("rise_time", 50.0), ("tplh", 33.3)]
    assert c.sim_deviation.warning_count == 4
    assert c.functional is not None
    assert (c.functional.match_rate_pct, c.functional.matched_cycles, c.functional.compared_cycles) == (100.0, 40, 40)
    assert r.settings.bandwidth_hz == 500e6
    verdicts = {x.metric_id: x.verdict for x in r.results if x.verdict is not None}
    assert verdicts == {"tpd": "PASS", "rise_time": "PASS", "voh": "MARGINAL", "iddq": "PASS", "match_rate": "PASS"}
    assert all(WarningCode.BANDWIDTH_LIMIT not in x.warnings for x in r.results)
    assert r.results == sorted(r.results, key=result_sort_key)
    f = r.functional
    assert f is not None and len(f.measured_bits) == len(f.sample_times_s) == 40
    assert f.mismatch_cycles == [] and f.first_mismatch is None


def test_mock_evidence_has_per_edge_values():
    r = _load()
    tplh = next(x for x in r.results if x.metric_id == "tplh")
    assert tplh.stats is not None and tplh.stats.n == len(tplh.evidence.edges) > 0
    assert tplh.evidence.worst_time_s in tplh.evidence.edge_times_s
    assert tplh.value == max(e.value for e in tplh.evidence.edges)


# ---------- catalog ----------

def test_catalog_matches_d4():
    assert list(METRICS) == list(D4)
    for mid, (cat, unit, simc) in D4.items():
        m = METRICS[mid]
        assert (m.category.value, m.unit, m.sim_compare) == (cat, unit, simc), mid
        assert m.label and m.definition and m.display_unit and m.display_scale > 0
    for mid, agg in D4_AGGREGATE.items():
        assert METRICS[mid].aggregate.value == agg


def test_enum_strings_are_fixed():
    assert [r.value for r in Role] == ["CLK", "IN", "OUT", "EN", "DATA", "VDD", "IDD", "UNUSED"]
    assert [v.value for v in Verdict] == ["PASS", "MARGINAL", "FAIL"]
    assert WarningCode.BANDWIDTH_LIMIT.value == "BANDWIDTH_LIMIT"
    assert WarningCode.SIM_DEVIATION.value == "SIM_DEVIATION"


# ---------- validation ----------

def test_waveform_validation():
    w = Waveform(channel_id="CH1", quantity="V", time_s=[0.0, 1e-9, 2e-9], values=[0, 1, 0])
    assert isinstance(w.time_s, np.ndarray) and w.time_s.dtype == np.float64
    assert w.sample_interval_s == pytest.approx(1e-9)
    with pytest.raises(ValidationError):
        Waveform(channel_id="CH1", quantity="V", time_s=[0, 2, 1], values=[0, 1, 0])
    with pytest.raises(ValidationError):
        Waveform(channel_id="CH1", quantity="V", time_s=[0, 1, 2], values=[0, 1])
    with pytest.raises(ValidationError):
        Waveform(channel_id="CH1", quantity="V", time_s=[0, 1], values=[0, float("nan")])


def test_measurement_set_and_request_validation():
    cmap = ChannelMap(channels=[ChannelInfo(channel_id="CH1", role="CLK"), ChannelInfo(channel_id="CH3", role="OUT")])
    w = Waveform(channel_id="CH3", quantity="V", time_s=[0, 1], values=[0, 1])
    ms = MeasurementSet(channel_map=cmap, waveforms=[w], paths=[Path(name="B", input_channel="CH1", output_channel="CH3")])
    assert ms.waveform("CH3") is w and ms.waveform("CH1") is None
    with pytest.raises(ValidationError):
        MeasurementSet(channel_map=cmap, waveforms=[Waveform(channel_id="CH9", quantity="V", time_s=[0, 1], values=[0, 1])])
    with pytest.raises(ValidationError):
        AnalysisRequest(measured=ms, sim=ms)  # sim set must be source="sim"
    sim = ms.model_copy(update={"session": SessionInfo(source="sim")})
    req = AnalysisRequest(measured=ms, sim=sim, settings=AnalysisSettings(bandwidth_hz=500e6))
    assert req.settings.marginal_threshold_pct == 10.0 and req.settings.sim_tolerance_pct == 20.0
    with pytest.raises(ValidationError):
        DCSweep(x=[1.0, 1.0], y=[1e-6, 2e-6])


def test_spec_and_expected_validation():
    with pytest.raises(ValidationError):
        Spec(metric_id="tpd")
    with pytest.raises(ValidationError):
        Spec(metric_id="nope", max=1.0)
    with pytest.raises(ValidationError):
        Spec(metric_id="voh", min=2.0, max=1.0)
    assert ExpectedPattern(bits="0101 1100_1,0").bits == "0101110010"
    with pytest.raises(ValidationError):
        ExpectedPattern(bits="01x1")


def test_make_result_fills_catalog_fields():
    r = make_result("tplh", path="Buffer", channel_id="CH3", value=6e-9,
                    warnings=[WarningCode.UNPAIRED_EDGES, WarningCode.UNPAIRED_EDGES])
    assert (r.label, r.category, r.unit) == (METRICS["tplh"].label, "timing", "s")
    assert r.verdict is None and r.margin_pct is None and r.warnings == ["UNPAIRED_EDGES"]
    assert r.representative() == 6e-9


# ---------- units / formatting ----------

@pytest.mark.parametrize("text,expected", [
    ("µA", ("A", 1e-6)), ("μA", ("A", 1e-6)), ("uA", ("A", 1e-6)),
    ("mV", ("V", 1e-3)), ("ns", ("s", 1e-9)), ("V", ("V", 1.0)), ("MHz", ("Hz", 1e6)), ("xyz", None),
])
def test_parse_unit(text, expected):
    got = parse_unit(text)
    if expected is None:
        assert got is None
    else:
        assert got[0] == expected[0] and got[1] == pytest.approx(expected[1])


def test_display_formatting():
    assert format_metric_value("tpd", 6.03e-9) == "6.03 ns"
    assert format_metric_value("voh", 1.75) == "1.75 V"
    assert format_metric_value("iddq", 1.5e-6) == "1.50 µA"
    assert format_metric_value("tpd", None) == "—"
    assert format_pct(9.375) == "9.4%" and format_pct(33.333, signed=True) == "+33.3%"
    assert format_spec(Spec(metric_id="tpd", max=8e-9)) == "≤ 8.00 ns"
    assert format_spec(Spec(metric_id="voh", min=1.6)) == "≥ 1.60 V"
