"""D9 / contract 4.5: summary line rules 0-5 fire / don't fire, order, templates, 8-line limit."""

from __future__ import annotations

from core.judge import build_cards, narrate
from core.models import (
    AnalysisSettings,
    ChannelInfo,
    ChannelMap,
    FunctionalDetail,
    Path,
    Spec,
    Stats,
    Verdict,
    WarningCode,
    make_result,
)

S = AnalysisSettings()
CMAP = ChannelMap(channels=[
    ChannelInfo(channel_id="CH1", role="CLK"),
    ChannelInfo(channel_id="CH2", role="IN"),
    ChannelInfo(channel_id="CH3", role="OUT"),
    ChannelInfo(channel_id="CH4", role="IN"),
    ChannelInfo(channel_id="CH5", role="OUT", label="Q1"),
    ChannelInfo(channel_id="CH6", role="IDD"),
])
BUFFER = Path(name="Buffer", input_channel="CH2", output_channel="CH3")
SLOWP = Path(name="SlowPath", input_channel="CH4", output_channel="CH5")

COMMON = "전 경로 공통 지연 증가 → 측정 경로(패드·PCB·프로브) 지연, VDD 강하, 공정 코너 가능성"
BW_TAIL = ": 측정값이 오실로스코프 대역폭 한계에 가까움 → 실제 값은 더 짧을 수 있음"


def _r(metric_id, value=1.0, *, path=None, channel_id="CH3", spec=None, verdict=None, margin=None, dev=None,
       sim=None, warnings=(), mean=None):
    stats = None
    if metric_id in ("rise_time", "fall_time", "tplh", "tphl", "tpd") and value is not None:
        m = value if mean is None else mean
        stats = Stats(mean=m, min=min(m, value), max=max(m, value), std=0.0, n=4)
    if dev is not None and sim is None:
        sim = 1.0
    r = make_result(metric_id, path=path, channel_id=channel_id, value=value, stats=stats, warnings=warnings)
    return r.model_copy(update={"spec": spec, "verdict": verdict, "margin_pct": margin, "sim_value": sim,
                                "deviation_pct": dev})


def _lines(results, functional=None, paths=(BUFFER,), settings=S):
    cards = build_cards(results, functional, settings)
    return narrate(results, functional, cards, list(paths), CMAP, settings)


def _func(expected: str, measured: str) -> FunctionalDetail:
    mism = [i + 1 for i, (a, b) in enumerate(zip(expected, measured)) if a != b]
    n = min(len(expected), len(measured))
    return FunctionalDetail(
        channel_id="CH3", clk_channel_id="CH1", threshold_v=0.9,
        sample_times_s=[float(i) for i in range(len(measured))],
        sample_values_v=[1.75 if b == "1" else 0.05 for b in measured],
        measured_bits=measured, expected_bits=expected, compared_cycles=n, matched_cycles=n - len(mism),
        mismatch_cycles=mism, first_mismatch=mism[0] if mism else None,
        match_rate_pct=(n - len(mism)) / n * 100.0,
    )


# ---- 0 headline -----------------------------------------------------------------------------


def test_headline_without_judgments():
    assert _lines([_r("vol", 0.05)]) == ["전체 판정: PASS 0 · MARGINAL 0 · FAIL 0"]


def test_headline_with_worst_margin_uses_display_name():
    voh = _r("voh", 1.75, channel_id="CH5", spec=Spec(metric_id="voh", min=1.6), verdict=Verdict.MARGINAL,
             margin=9.375)
    tpd = _r("tpd", 6.0e-9, path="Buffer", spec=Spec(metric_id="tpd", max=8e-9), verdict=Verdict.PASS, margin=25.0)
    lines = _lines([tpd, voh])
    assert lines[0] == "전체 판정: PASS 1 · MARGINAL 1 · FAIL 0 — 최악 마진 VOH 9.4% (Q1)"
    assert lines[1] == "Q1 VOH 1.75 V — 스펙 ≥ 1.60 V 대비 마진 9.4% (MARGINAL)"
    worst_path = _r("tpd", 7.6e-9, path="Buffer", spec=Spec(metric_id="tpd", max=8e-9), verdict=Verdict.MARGINAL,
                    margin=5.0)
    assert _lines([worst_path])[0].endswith("— 최악 마진 tpd 5.0% (Buffer)")


# ---- 1 / 1b FAIL and MARGINAL ---------------------------------------------------------------


def test_fail_lines_before_marginal_lines_in_result_order():
    iddq = _r("iddq", 3.0e-6, channel_id="DMM", spec=Spec(metric_id="iddq", max=2.5e-6), verdict=Verdict.FAIL,
              margin=-20.0)
    tpd = _r("tpd", 9.0e-9, path="Buffer", spec=Spec(metric_id="tpd", max=8e-9), verdict=Verdict.FAIL,
             margin=-12.5)
    voh = _r("voh", 1.75, spec=Spec(metric_id="voh", min=1.6), verdict=Verdict.MARGINAL, margin=9.375)
    rise = _r("rise_time", 3.0e-9, spec=Spec(metric_id="rise_time", max=4e-9), verdict=Verdict.PASS, margin=25.0)
    lines = _lines([voh, iddq, rise, tpd])  # unsorted input -> catalog order in output
    assert lines == [
        "전체 판정: PASS 1 · MARGINAL 1 · FAIL 2 — 최악 마진 IDDQ -20.0% (DMM)",
        "Buffer tpd 9.00 ns — 스펙 ≤ 8.00 ns 위반 (FAIL)",
        "DMM IDDQ 3.00 µA — 스펙 ≤ 2.50 µA 위반 (FAIL)",
        "CH3 VOH 1.75 V — 스펙 ≥ 1.60 V 대비 마진 9.4% (MARGINAL)",
    ]


def test_range_spec_and_zero_limit_fail_line():
    vol = _r("vol", 0.2, spec=Spec(metric_id="vol", min=0.0, max=0.1), verdict=Verdict.FAIL, margin=None)
    assert _lines([vol])[1] == "CH3 VOL 0.200 V — 스펙 0.00–0.100 V 위반 (FAIL)"


# ---- 2 functional mismatch ------------------------------------------------------------------


def test_functional_mismatch_line_replaces_match_rate_fail():
    bits = "0000001000001100001010001111001000101100"
    err = bits[:36] + ("0" if bits[36] == "1" else "1") + bits[37:]
    mr = _r("match_rate", 97.5, verdict=Verdict.FAIL)
    lines = _lines([mr], _func(bits, err))
    assert lines == ["전체 판정: PASS 0 · MARGINAL 0 · FAIL 1",
                     "37번째 사이클에서 첫 불일치 (기대 1, 측정 0)"]


def test_no_functional_line_when_all_match():
    bits = "0110"
    assert _lines([_r("match_rate", 100.0, verdict=Verdict.PASS)], _func(bits, bits)) == [
        "전체 판정: PASS 1 · MARGINAL 0 · FAIL 0"]


# ---- 3 common delay vs 4 single slow path ---------------------------------------------------


def _demo_devs():
    return [
        _r("rise_time", 3e-9, dev=50.0), _r("fall_time", 2.5e-9, dev=38.9),
        _r("tplh", 6e-9, path="Buffer", dev=33.3), _r("tphl", 5.5e-9, path="Buffer", dev=31.0),
        _r("voh", 1.75, dev=-2.8),
    ]


def test_rule3_common_delay_fires_for_demo():
    assert _lines(_demo_devs())[1:] == [COMMON]


def test_rule3_not_fired_when_one_below_tolerance():
    results = _demo_devs()
    results[3] = _r("tphl", 5.5e-9, path="Buffer", dev=15.0)
    assert COMMON not in _lines(results)


def test_rule3_not_fired_when_ratio_above_two():
    results = [_r("rise_time", 3e-9, dev=65.0), _r("tplh", 6e-9, path="Buffer", dev=30.0)]
    assert COMMON not in _lines(results)  # 65 / 30 > 2
    results = [_r("rise_time", 3e-9, dev=60.0), _r("tplh", 6e-9, path="Buffer", dev=30.0)]
    assert COMMON in _lines(results)  # exactly 2 -> fires


def test_rule3_needs_two_deviations():
    assert COMMON not in _lines([_r("rise_time", 3e-9, dev=50.0)])


def _two_paths(a_dev: float, b_dev: float):
    return [
        _r("rise_time", 3e-9, dev=40.0),
        _r("tplh", 6e-9, path="Buffer", dev=b_dev), _r("tphl", 5.5e-9, path="Buffer", dev=b_dev),
        _r("tplh", 9e-9, path="SlowPath", channel_id="CH5", dev=a_dev - 1.0),
        _r("tphl", 9e-9, path="SlowPath", channel_id="CH5", dev=a_dev + 1.0),
    ]


def test_rule4_specific_path_suppresses_rule3():
    results = _two_paths(55.0, 30.0)  # rule 3 alone would fire too (all > 20, 56/30 <= 2)
    lines = _lines(results, paths=(BUFFER, SLOWP))
    assert lines[1:] == ["SlowPath만 시뮬 대비 +55.0% → 해당 경로 부하·배선 기생 확인 필요"]
    assert COMMON not in lines
    # same numbers with only one path defined -> rule 4 cannot fire, rule 3 does
    assert _lines(results, paths=(SLOWP,))[1:] == [COMMON]


def test_rule4_not_fired_when_paths_are_similar():
    lines = _lines(_two_paths(33.0, 31.0), paths=(BUFFER, SLOWP))
    assert lines[1:] == [COMMON]


def test_rule4_needs_gap_of_tolerance():
    lines = _lines(_two_paths(49.0, 30.0), paths=(BUFFER, SLOWP))  # gap 19 < 20
    assert not any("만 시뮬 대비" in ln for ln in lines)
    lines = _lines(_two_paths(50.0, 30.0), paths=(BUFFER, SLOWP))  # gap exactly 20
    assert lines[1] == "SlowPath만 시뮬 대비 +50.0% → 해당 경로 부하·배선 기생 확인 필요"


def test_rule4_needs_deviation_above_tolerance():
    lines = _lines(_two_paths(19.0, -10.0), paths=(BUFFER, SLOWP))  # gap 29 but 19 <= tol
    assert lines == ["전체 판정: PASS 0 · MARGINAL 0 · FAIL 0"]


# ---- 5 bandwidth ----------------------------------------------------------------------------


def test_bandwidth_line_uses_mean():
    rise = _r("rise_time", 3.1e-9, mean=2.98e-9, warnings=[WarningCode.BANDWIDTH_LIMIT])
    fall = _r("fall_time", 2.5e-9, channel_id="CH5", warnings=[WarningCode.BANDWIDTH_LIMIT])
    tplh = _r("tplh", 6e-9, path="Buffer")
    lines = _lines([fall, rise, tplh])
    assert lines[1:] == [f"CH3 rise 2.98 ns{BW_TAIL}", f"Q1 fall 2.50 ns{BW_TAIL}"]


def test_no_bandwidth_line_without_warning():
    assert _lines([_r("rise_time", 3e-9)]) == ["전체 판정: PASS 0 · MARGINAL 0 · FAIL 0"]


# ---- full order and 8-line limit ------------------------------------------------------------


def test_full_order():
    bits = "0110"
    results = [
        _r("tpd", 9e-9, path="Buffer", spec=Spec(metric_id="tpd", max=8e-9), verdict=Verdict.FAIL, margin=-12.5),
        _r("voh", 1.75, spec=Spec(metric_id="voh", min=1.6), verdict=Verdict.MARGINAL, margin=9.375),
        _r("match_rate", 75.0, verdict=Verdict.FAIL),
        _r("rise_time", 3e-9, dev=50.0, warnings=[WarningCode.BANDWIDTH_LIMIT]),
        _r("tplh", 6e-9, path="Buffer", dev=33.3),
    ]
    lines = _lines(results, _func(bits, "0100"))
    assert lines == [
        "전체 판정: PASS 0 · MARGINAL 1 · FAIL 2 — 최악 마진 tpd -12.5% (Buffer)",
        "Buffer tpd 9.00 ns — 스펙 ≤ 8.00 ns 위반 (FAIL)",
        "CH3 VOH 1.75 V — 스펙 ≥ 1.60 V 대비 마진 9.4% (MARGINAL)",
        "3번째 사이클에서 첫 불일치 (기대 1, 측정 0)",
        COMMON,
        f"CH3 rise 3.00 ns{BW_TAIL}",
    ]


def test_at_most_eight_lines_cut_from_end():
    spec = Spec(metric_id="voh", min=2.0)
    fails = [_r("voh", 1.0 + i * 0.01, channel_id=f"X{i}", spec=spec, verdict=Verdict.FAIL, margin=-50.0 + i)
             for i in range(10)]
    bw = _r("rise_time", 3e-9, warnings=[WarningCode.BANDWIDTH_LIMIT])
    lines = _lines([*fails, bw])
    assert len(lines) == 8
    assert lines[0].startswith("전체 판정: PASS 0 · MARGINAL 0 · FAIL 10")
    assert lines[1].startswith("X0 VOH 1.00 V") and lines[7].startswith("X6 VOH")
    assert not any(BW_TAIL in ln for ln in lines)


def test_narrate_is_deterministic_and_does_not_mutate():
    results = _demo_devs()
    before = [r.model_dump_json() for r in results]
    assert _lines(results) == _lines(list(reversed(results)))
    assert [r.model_dump_json() for r in results] == before
