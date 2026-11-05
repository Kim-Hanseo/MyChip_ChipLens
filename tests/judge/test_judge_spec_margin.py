"""D5 / contract 4.1: spec matching, margin formula, verdict boundaries, match_rate special case."""

from __future__ import annotations

import pytest

from core.judge import apply_specs, judge_value, match_spec
from core.models import AnalysisSettings, Spec, Stats, Verdict, make_result

T = 10.0  # default marginal threshold


def _res(metric_id: str, value: float | None, *, path: str | None = None, channel_id: str | None = "CH3"):
    stats = Stats(mean=value, min=value, max=value, std=0.0, n=1) if value is not None else None
    if metric_id in ("voh", "vol", "iddq", "match_rate", "idd_avg", "avg_power", "frequency"):
        stats = None
    return make_result(metric_id, path=path, channel_id=channel_id, value=value, stats=stats)


# ---- margin formula -------------------------------------------------------------------------


def test_upper_limit_margin():
    verdict, margin = judge_value(6.0e-9, Spec(metric_id="tpd", max=8.0e-9), T)
    assert verdict == Verdict.PASS
    assert margin == pytest.approx(25.0)


def test_lower_limit_margin():
    verdict, margin = judge_value(1.75, Spec(metric_id="voh", min=1.6), T)
    assert verdict == Verdict.MARGINAL
    assert margin == pytest.approx(9.375)


def test_range_uses_smaller_margin():
    spec = Spec(metric_id="voh", min=10.0, max=100.0)
    verdict, margin = judge_value(20.0, spec, T)  # lower 100 %, upper 80 %
    assert (verdict, margin) == (Verdict.PASS, pytest.approx(80.0))
    verdict, margin = judge_value(95.0, spec, T)  # lower 850 %, upper 5 %
    assert (verdict, margin) == (Verdict.MARGINAL, pytest.approx(5.0))
    verdict, margin = judge_value(9.0, spec, T)  # below min
    assert verdict == Verdict.FAIL and margin == pytest.approx(-10.0)


def test_negative_limit_uses_absolute_value():
    verdict, margin = judge_value(-1.0, Spec(metric_id="setup_slack", min=-2.0), T)
    assert verdict == Verdict.PASS and margin == pytest.approx(50.0)
    verdict, margin = judge_value(-3.0, Spec(metric_id="setup_slack", max=-2.0), T)
    assert verdict == Verdict.PASS and margin == pytest.approx(50.0)


@pytest.mark.parametrize(
    ("value", "spec", "expected"),
    [
        (-1e-3, Spec(metric_id="vol", max=0.0), Verdict.PASS),
        (0.0, Spec(metric_id="vol", max=0.0), Verdict.PASS),
        (1e-3, Spec(metric_id="vol", max=0.0), Verdict.FAIL),
        (0.0, Spec(metric_id="hold_slack", min=0.0), Verdict.PASS),
        (-1e-12, Spec(metric_id="hold_slack", min=0.0), Verdict.FAIL),
        (0.5, Spec(metric_id="vol", min=0.0, max=1.0), Verdict.PASS),  # range with one zero limit
        (1.5, Spec(metric_id="vol", min=0.0, max=1.0), Verdict.FAIL),
    ],
)
def test_zero_limit_gives_no_margin(value, spec, expected):
    verdict, margin = judge_value(value, spec, T)
    assert verdict == expected
    assert margin is None


# ---- grade boundaries -----------------------------------------------------------------------


def test_exactly_threshold_is_pass_upper():
    verdict, margin = judge_value(9.0, Spec(metric_id="voh", max=10.0), T)
    assert margin == 10.0
    assert verdict == Verdict.PASS


def test_exactly_threshold_is_pass_lower():
    verdict, margin = judge_value(11.0, Spec(metric_id="voh", min=10.0), T)
    assert margin == 10.0
    assert verdict == Verdict.PASS


def test_just_below_threshold_is_marginal():
    verdict, margin = judge_value(9.01, Spec(metric_id="voh", max=10.0), T)
    assert margin < 10.0 and verdict == Verdict.MARGINAL


def test_exactly_zero_margin_is_marginal():
    verdict, margin = judge_value(10.0, Spec(metric_id="voh", max=10.0), T)
    assert margin == 0.0 and verdict == Verdict.MARGINAL
    verdict, margin = judge_value(10.0, Spec(metric_id="voh", min=10.0), T)
    assert margin == 0.0 and verdict == Verdict.MARGINAL


def test_negative_margin_is_fail():
    verdict, margin = judge_value(10.01, Spec(metric_id="voh", max=10.0), T)
    assert margin < 0.0 and verdict == Verdict.FAIL


def test_threshold_is_a_setting():
    spec = Spec(metric_id="voh", min=1.6)
    assert judge_value(1.75, spec, 5.0)[0] == Verdict.PASS
    assert judge_value(1.75, spec, 20.0)[0] == Verdict.MARGINAL
    assert judge_value(10.0, Spec(metric_id="voh", max=10.0), 0.0)[0] == Verdict.PASS  # T = 0: no MARGINAL


# ---- spec matching --------------------------------------------------------------------------


def test_match_spec_most_specific_wins():
    general = Spec(metric_id="tpd", max=10e-9)
    by_channel = Spec(metric_id="tpd", channel_id="CH3", max=9e-9)
    by_path = Spec(metric_id="tpd", path="Buffer", max=8e-9)
    by_both = Spec(metric_id="tpd", path="Buffer", channel_id="CH3", max=7e-9)
    r = _res("tpd", 6e-9, path="Buffer")
    assert match_spec(r, [general, by_channel, by_path, by_both]) is by_both
    assert match_spec(r, [general, by_channel, by_path]) is by_path
    assert match_spec(r, [general, by_channel]) is by_channel
    assert match_spec(r, [general]) is general


def test_match_spec_tie_takes_first_and_filters_mismatch():
    first = Spec(metric_id="tpd", max=10e-9)
    second = Spec(metric_id="tpd", max=5e-9)
    other_path = Spec(metric_id="tpd", path="Other", max=1e-9)
    other_channel = Spec(metric_id="tpd", channel_id="CH9", max=1e-9)
    other_metric = Spec(metric_id="tplh", max=1e-9)
    r = _res("tpd", 6e-9, path="Buffer")
    assert match_spec(r, [other_path, other_channel, other_metric, first, second]) is first
    assert match_spec(r, [other_path, other_channel, other_metric]) is None
    # a path-less result never matches a path spec
    assert match_spec(_res("rise_time", 3e-9), [Spec(metric_id="rise_time", path="Buffer", max=4e-9)]) is None


# ---- apply_specs ----------------------------------------------------------------------------


def test_apply_specs_fills_judgment_and_keeps_order_and_inputs():
    settings = AnalysisSettings()
    results = [_res("rise_time", 3e-9), _res("voh", 1.75), _res("vol", 0.05), _res("iddq", 1.5e-6, channel_id="DMM")]
    specs = [Spec(metric_id="voh", min=1.6), Spec(metric_id="rise_time", max=4e-9), Spec(metric_id="iddq", max=2.5e-6)]
    out = apply_specs(results, specs, settings)
    assert [r.metric_id for r in out] == ["rise_time", "voh", "vol", "iddq"]
    assert [r.verdict for r in out] == [Verdict.PASS, Verdict.MARGINAL, None, Verdict.PASS]
    assert out[0].spec == specs[1] and out[0].margin_pct == pytest.approx(25.0)
    assert out[3].margin_pct == pytest.approx(40.0)
    assert out[2].spec is None and out[2].margin_pct is None
    assert all(r.verdict is None and r.spec is None for r in results)  # inputs untouched


def test_apply_specs_value_none_gets_spec_only():
    spec = Spec(metric_id="tpd", max=8e-9)
    (r,) = apply_specs([_res("tpd", None, path="Buffer")], [spec], AnalysisSettings())
    assert r.spec == spec and r.verdict is None and r.margin_pct is None


@pytest.mark.parametrize(("value", "verdict"), [(100.0, Verdict.PASS), (97.5, Verdict.FAIL), (0.0, Verdict.FAIL)])
def test_match_rate_ignores_specs(value, verdict):
    spec = Spec(metric_id="match_rate", min=90.0)  # must be ignored
    (r,) = apply_specs([_res("match_rate", value)], [spec], AnalysisSettings())
    assert r.verdict == verdict
    assert r.margin_pct is None and r.spec is None


def test_match_rate_without_value_has_no_verdict():
    (r,) = apply_specs([_res("match_rate", None)], [], AnalysisSettings())
    assert r.verdict is None and r.spec is None and r.margin_pct is None
