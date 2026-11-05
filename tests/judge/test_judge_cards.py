"""D9 / contract 4.4: summary cards 1-4 (counts, worst margin ties, card-3 family skipping, functional)."""

from __future__ import annotations

import pytest

from core.judge import build_cards
from core.models import (
    AnalysisSettings,
    FunctionalDetail,
    Source,
    Spec,
    Stats,
    Verdict,
    WarningCode,
    make_result,
)


def _r(metric_id: str, value: float | None = 1.0, *, path=None, channel_id="CH3", verdict=None, margin=None,
       spec=None, sim=None, dev=None, warnings=(), source=Source.MEASURED, mean=None):
    stats = None
    if metric_id in ("rise_time", "fall_time", "tplh", "tphl", "tpd", "setup_slack", "hold_slack") and value is not None:
        m = value if mean is None else mean
        stats = Stats(mean=m, min=min(m, value), max=max(m, value), std=0.0, n=4)
    r = make_result(metric_id, source=source, path=path, channel_id=channel_id, value=value, stats=stats,
                    warnings=warnings)
    if spec is None and verdict is not None and metric_id != "match_rate":
        spec = Spec(metric_id=metric_id, max=10.0)
    return r.model_copy(update={"verdict": verdict, "margin_pct": margin, "spec": spec, "sim_value": sim,
                                "deviation_pct": dev})


def _functional(expected: str | None, measured: str) -> FunctionalDetail:
    n = len(measured)
    mism = [i + 1 for i, (a, b) in enumerate(zip(expected or "", measured)) if a != b]
    compared = min(len(expected), n) if expected else 0
    return FunctionalDetail(
        channel_id="CH3", clk_channel_id="CH1", threshold_v=0.9,
        sample_times_s=[i * 1e-7 for i in range(n)], sample_values_v=[1.75 if b == "1" else 0.05 for b in measured],
        measured_bits=measured, expected_bits=expected, compared_cycles=compared,
        matched_cycles=compared - len(mism), mismatch_cycles=mism, first_mismatch=mism[0] if mism else None,
        match_rate_pct=(compared - len(mism)) / compared * 100.0 if compared else None,
    )


S = AnalysisSettings()


def test_verdict_card_counts_measured_only():
    results = [
        _r("tpd", path="Buffer", verdict=Verdict.PASS, margin=25.0),
        _r("rise_time", verdict=Verdict.PASS, margin=24.0),
        _r("voh", verdict=Verdict.MARGINAL, margin=9.4),
        _r("iddq", channel_id="DMM", verdict=Verdict.FAIL, margin=-3.0),
        _r("match_rate", 100.0, verdict=Verdict.PASS),
        _r("vol"),
        _r("period", channel_id="CH1"),
        _r("voh", verdict=Verdict.FAIL, margin=-1.0, source=Source.SIM),  # ignored
    ]
    c = build_cards(results, None, S).verdicts
    assert (c.pass_count, c.marginal_count, c.fail_count, c.no_spec_count) == (3, 1, 1, 2)


def test_worst_margin_minimum_and_tie_order():
    a = _r("voh", verdict=Verdict.MARGINAL, margin=5.0)
    b = _r("rise_time", verdict=Verdict.MARGINAL, margin=5.0)  # same margin, earlier in catalog
    c = _r("tpd", path="Buffer", verdict=Verdict.PASS, margin=25.0)
    w = build_cards([a, c, b], None, S).worst_margin
    assert w is not None and w.metric_id == "rise_time" and w.margin_pct == 5.0
    assert w.verdict == Verdict.MARGINAL and w.spec == b.spec
    # match_rate has no margin -> not a candidate; no margin at all -> None
    assert build_cards([_r("match_rate", 97.5, verdict=Verdict.FAIL)], None, S).worst_margin is None


def test_sim_card_none_without_sim_values():
    assert build_cards([_r("rise_time"), _r("tplh", path="Buffer")], None, S).sim_deviation is None


def test_sim_card_skips_same_family():
    results = [
        _r("rise_time", 3.0e-9, sim=2.0e-9, dev=50.0, warnings=[WarningCode.SIM_DEVIATION]),
        _r("fall_time", 2.5e-9, sim=1.8e-9, dev=38.9, warnings=[WarningCode.SIM_DEVIATION]),  # edge_rate again
        _r("tplh", 6.0e-9, path="Buffer", sim=4.5e-9, dev=33.3, warnings=[WarningCode.SIM_DEVIATION]),
        _r("tphl", 5.5e-9, path="Buffer", sim=4.2e-9, dev=31.0, warnings=[WarningCode.SIM_DEVIATION]),
        _r("voh", 1.75, sim=1.8, dev=-2.8),
        _r("vol", 0.05, sim=0.0, dev=None),
    ]
    card = build_cards(results, None, S).sim_deviation
    assert card is not None
    assert [(i.metric_id, i.deviation_pct) for i in card.top] == [("rise_time", 50.0), ("tplh", 33.3)]
    assert card.warning_count == 4 and card.tolerance_pct == 20.0
    assert card.top[1].path == "Buffer" and card.top[1].sim_value == 4.5e-9


def test_sim_card_ranks_by_absolute_value_and_applies_offset():
    settings = AnalysisSettings(delay_offset_s=1.0e-9, sim_tolerance_pct=15.0)
    results = [
        _r("voh", 1.0, sim=1.8, dev=-44.4),
        _r("tplh", 6.0e-9, path="Buffer", mean=5.9e-9, sim=4.5e-9, dev=8.9),
        _r("tphl", 5.5e-9, path="Buffer", sim=4.2e-9, dev=7.1),
        _r("vol", 0.30, sim=0.25, dev=20.0),  # output_level family again -> skipped
    ]
    card = build_cards(results, None, settings).sim_deviation
    assert [i.metric_id for i in card.top] == ["voh", "tplh"]
    assert card.top[1].measured_value == pytest.approx(4.9e-9)  # mean 5.9 ns - offset 1.0 ns
    assert card.warning_count == 0 and card.tolerance_pct == 15.0


def test_sim_card_with_only_undefined_deviations():
    card = build_cards([_r("vol", 0.05, sim=0.0, dev=None)], None, S).sim_deviation
    assert card is not None and card.top == [] and card.warning_count == 0


def test_functional_card_conditions():
    ok = _functional("1010", "1010")
    bad = _functional("1010", "1000")
    mr_pass = _r("match_rate", 100.0, verdict=Verdict.PASS)
    mr_fail = _r("match_rate", 75.0, verdict=Verdict.FAIL)
    card = build_cards([mr_pass], ok, S).functional
    assert card is not None and (card.match_rate_pct, card.matched_cycles, card.compared_cycles) == (100.0, 4, 4)
    assert card.verdict == Verdict.PASS and card.first_mismatch is None
    card = build_cards([mr_fail], bad, S).functional
    assert card.verdict == Verdict.FAIL and card.first_mismatch == 3 and card.match_rate_pct == 75.0
    assert build_cards([mr_pass], None, S).functional is None  # no functional detail
    assert build_cards([], _functional(None, "1010"), S).functional is None  # no expected bits
    assert build_cards([_r("match_rate", 100.0)], ok, S).functional is None  # match_rate without verdict
