| 프로브 | 확인 항목 | 기대 | 실제 | 결과 |
|---|---|---|---|---|
| A | demo defaults before any file | no error | [] | PASS |
| A | roles applied to channels that appear later | CLK IN OUT IDD | ['CLK', 'IN', 'OUT', 'IDD'] | PASS |
| A | full demo cards in alternate order | ✓ PASS 4 · ! MARGINAL 1 · ✕ FAIL 0, ✓ 100% (40/40) | True | PASS |
| B | DC tab: I–V curve drawn (no 'DC 스윕 데이터 없음' info) | I–V chart present | no-data info shown=False, charts=3 | PASS |
| B | waveform tab: default highlight = worst-margin metric with markers | selectbox present, no error | selected=rise_time//CH3 | PASS |
| B | card 2 '파형에서 보기' -> waveform tab, VOH highlighted | 파형, voh||CH3 | 파형, voh//CH3 | PASS |
| E | UI: same inputs, run twice -> report JSON bytes | identical | True | PASS |
| C | evidence per metric == docs/metrics.md §3 (edges, ref keys, worst, params) | all 16 match | all match | PASS |
| C | (observation) valued results with no evidence at all | info | ['idd_avg'] | PASS |
| C | tpLH evidence: ref levels + interval per edge | keys present, t_start/t_end set | ref=['in_v50', 'out_v50'], edges=8, interval=True | PASS |
| D | cp949 CSV: UTF-8 fails -> cp949 + ENCODING_FALLBACK | encoding cp949, ENCODING_FALLBACK | cp949, ['ENCODING_FALLBACK'] | PASS |
| D | Korean headers with units: 시간(ns) -> s x1e-9, 출력(mV) -> V x1e-3 | as stated | {'시간(ns)': ('시간', 'ns', 's', 1e-09), '출력(mV)': ('출력', 'mV', 'V', 0.001)} | PASS |
| D | probe x10 + mV: max value = 180 mV x 10 = 1.8 V, dt = 1 ns | 1.8 V, 1 ns | 1.8000 V, 1.0000 ns | PASS |
| D | no time column: start + n*interval | -1 us, 0.2 ns | -1.000e-06, 2.000e-10 | PASS |
| D | B9: unit forgotten (mV read as V, 180 V) -> SUSPICIOUS_RANGE | SUSPICIOUS_RANGE | ['SUSPICIOUS_RANGE'] | PASS |
