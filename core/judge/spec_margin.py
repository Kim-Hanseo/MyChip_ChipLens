"""Spec matching, margin and verdict (decisions D5, contract section 4.1)."""

from __future__ import annotations

from core.models import AnalysisResult, AnalysisSettings, Spec, Verdict

MATCH_RATE_ID = "match_rate"
MATCH_RATE_PASS_PCT = 100.0


def _specificity(spec: Spec) -> int:
    """Path given = 2, channel given = 1 (contract 4.1)."""
    return (2 if spec.path is not None else 0) + (1 if spec.channel_id is not None else 0)


def match_spec(result: AnalysisResult, specs: list[Spec]) -> Spec | None:
    """Most specific spec that applies to `result` (ties -> earliest in `specs`), or None."""
    best: Spec | None = None
    best_score = -1
    for spec in specs:
        if spec.metric_id != result.metric_id:
            continue
        if spec.path is not None and spec.path != result.path:
            continue
        if spec.channel_id is not None and spec.channel_id != result.channel_id:
            continue
        score = _specificity(spec)
        if score > best_score:
            best, best_score = spec, score
    return best


def _grade(margin_pct: float, marginal_threshold_pct: float) -> Verdict:
    if margin_pct < 0.0:
        return Verdict.FAIL
    if margin_pct < marginal_threshold_pct:
        return Verdict.MARGINAL
    return Verdict.PASS


def judge_value(value: float, spec: Spec, marginal_threshold_pct: float) -> tuple[Verdict, float | None]:
    """(verdict, margin_pct) for one value against one spec.

    Upper: (max - v)/|max| x 100, lower: (v - min)/|min| x 100, range: the smaller one.
    If any used limit is 0 the margin is None and the verdict is PASS/FAIL by limit satisfaction only.
    """
    limits_ok = True
    zero_limit = False
    margins: list[float] = []
    if spec.max is not None:
        limits_ok &= value <= spec.max
        if spec.max == 0.0:
            zero_limit = True
        else:
            margins.append((spec.max - value) / abs(spec.max) * 100.0)
    if spec.min is not None:
        limits_ok &= value >= spec.min
        if spec.min == 0.0:
            zero_limit = True
        else:
            margins.append((value - spec.min) / abs(spec.min) * 100.0)
    if zero_limit:
        return (Verdict.PASS if limits_ok else Verdict.FAIL), None
    margin = min(margins)
    return _grade(margin, marginal_threshold_pct), margin


def apply_specs(results: list[AnalysisResult], specs: list[Spec],
                settings: AnalysisSettings) -> list[AnalysisResult]:
    """Fill spec/verdict/margin_pct (new objects, input order kept).

    `match_rate` ignores specs: value == 100 -> PASS, else FAIL, margin None, spec None.
    A matched result with value None gets the spec only (verdict/margin None).
    """
    out: list[AnalysisResult] = []
    for r in results:
        if r.metric_id == MATCH_RATE_ID:
            if r.value is None:
                out.append(r.model_copy(update={"spec": None, "verdict": None, "margin_pct": None}))
            else:
                verdict = Verdict.PASS if r.value == MATCH_RATE_PASS_PCT else Verdict.FAIL
                out.append(r.model_copy(update={"spec": None, "verdict": verdict, "margin_pct": None}))
            continue
        spec = match_spec(r, specs)
        if spec is None:
            out.append(r)
        elif r.value is None:
            out.append(r.model_copy(update={"spec": spec, "verdict": None, "margin_pct": None}))
        else:
            verdict, margin = judge_value(r.value, spec, settings.marginal_threshold_pct)
            out.append(r.model_copy(update={"spec": spec, "verdict": verdict, "margin_pct": margin}))
    return out
