"""Golden test: determinism (same input -> byte-identical JSON) and speed (20 000 points x 4 channels)."""

from __future__ import annotations

import time

from core.analyzers import analyze_all
from core.models import AnalyzerOutput

PERF_LIMIT_S = 3.0  # target < 1 s (docs/contract.md section 3), hard limit 3 s


def test_deterministic_json(scope_set, scope_err_set, sim_set, settings, expected):
    for mset, exp in ((scope_set, expected), (scope_err_set, expected), (sim_set, None)):
        a = analyze_all(mset, settings, exp).model_dump_json()
        b = analyze_all(mset, settings, exp).model_dump_json()
        assert a == b
        # and it round-trips through the contract model
        assert AnalyzerOutput.model_validate_json(a).model_dump_json() == a


def test_analyze_all_speed(scope_set, settings, expected):
    assert all(w.n_samples == 20_000 for w in scope_set.waveforms)
    assert len(scope_set.waveforms) == 4
    analyze_all(scope_set, settings, expected)  # warm-up (imports, caches)
    best = float("inf")
    for _ in range(3):
        t0 = time.perf_counter()
        analyze_all(scope_set, settings, expected)
        best = min(best, time.perf_counter() - t0)
    print(f"\nanalyze_all 20k x 4ch: {best * 1e3:.1f} ms")
    assert best < PERF_LIMIT_S
