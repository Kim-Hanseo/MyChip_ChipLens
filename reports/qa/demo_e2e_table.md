| 단계 | 확인 항목 | 기대 | 실제 | 결과 |
|---|---|---|---|---|
| 1 | preview_file(synth_scope.csv): header row auto-detected, time column | header row 4, time 'Time(s)' | header_row=4, time_candidates=['Time(s)'] | PASS |
| 1 | columns/units from headers | Time(s)[s], CH1-3 [V], CH4 [A] | Time(s)[s], CH1(V)[V], CH2(V)[V], CH3(V)[V], CH4(A)[A] | PASS |
| 1 | to_waveforms: 4 channels x 20,000 pts, dt 0.2 ns, no notices | CH1..CH4, 20000 each, 0.2 ns, [] | ['CH1', 'CH2', 'CH3', 'CH4'], [20000, 20000, 20000, 20000], 0.2000 ns, [] | PASS |
| 1 | CH4 quantity = A (IDD) | A | A | PASS |
| 2 | ChannelMap/Path/AnalysisSettings accepted | CLK/IN/OUT/IDD, Buffer CH2->CH3, 1.8 V, 500 MHz | ['CLK', 'IN', 'OUT', 'IDD'], Buffer CH2->CH3, 1.8 V, 500 MHz | PASS |
| 3 | spec SI conversion | tpd max 8e-9 s, rise max 4e-9 s, voh min 1.6 V, iddq max 2.5e-6 A | tpd max 8e-09, rise_time max 4e-09, voh 1.6.., iddq max 2.5e-06 | PASS |
| 4 | preview_file(synth_sim.csv): whitespace delimiter, repeated time cols dropped | delimiter ' ', columns time, v(clk), v(in), v(out) | delimiter=' ', columns=['time', 'v(clk)', 'v(in)', 'v(out)'], notices=[] | PASS |
| 4 | suggest_sim_mapping | v(clk)->CH1, v(in)->CH2, v(out)->CH3 | {'v(clk)': 'CH1', 'v(in)': 'CH2', 'v(out)': 'CH3'} | PASS |
| 4 | sim to_waveforms re-keyed | CH1, CH2, CH3 x 40001 pts, 0.1 ns | ['CH1', 'CH2', 'CH3'] x [40001, 40001, 40001], 0.1000 ns | PASS |
| 5 | tpd verdict / margin (plan: PASS 25 %, D11: PASS ≈25 % ±2 %p) | PASS, 23–27 % | PASS, 24.76 % (worst 6.019 ns) | PASS |
| 5 | rise verdict / margin (plan: PASS 25 %) | PASS, 23–27 % | PASS, 24.43 % (worst 3.023 ns) | PASS |
| 5 | VOH verdict / margin (plan: MARGINAL 9.4 %) | MARGINAL, 7.4–11.4 % (9.4 ±2 %p) | MARGINAL, 9.38 % (VOH 1.7501 V) | PASS |
| 5 | tpLH sim deviation (plan: +33 % warning) | +33.3 ±2 %p, SIM_DEVIATION | 33.37 %, ['SIM_DEVIATION'] | PASS |
| 5 | rise sim deviation (plan: +50 % warning) | +50.0 ±2 %p, SIM_DEVIATION | 49.19 %, ['SIM_DEVIATION'] | PASS |
| 5 | tpHL / fall sim deviation (App. A: +31 / +39 %, warnings) | +31.0 / +38.9 ±2 %p, both SIM_DEVIATION | 31.14 / 39.25 % | PASS |
| 5 | SIM_DEVIATION set (App. A: timing 4 warnings) | fall_time, rise_time, tphl, tplh | ['fall_time', 'rise_time', 'tphl', 'tplh'] | PASS |
| 5 | card 3 sim max deviation (D9: rise +50, tplh +33, 4 warnings) | [rise_time +50.0, tplh +33.3], 4 | [('rise_time', 49.2), ('tplh', 33.4)], 4 | PASS |
| 5 | no bandwidth warning at 500 MHz (App. A) | [] | [] | PASS |
| 5 | IDDQ spec has no target yet (DMM not uploaded) | no iddq result | None | PASS |
| 5 | card 1 at step 5 (tpd, rise PASS; voh MARGINAL) | PASS 2 · MARGINAL 1 · FAIL 0 | PASS 2 · MARGINAL 1 · FAIL 0 | PASS |
| 5 | card 2 worst margin = VOH 9.4 % | voh, 9.4 % | voh, 9.38 % | PASS |
| 5 | summary rule 3 (all timing slower by similar ratio) | line '전 경로 공통 지연 증가 …' present | True | PASS |
| 6 | preview_file(synth_dmm.xlsx): sheet DC측정, header row 2 (merged title row 0, blank row 1) | sheet DC측정, header_row 2 | sheet=DC측정, sheets=['DC측정', '조건'], header_row=2 | PASS |
| 6 | Korean header unit extraction | 전압(V) -> V x1, 전류(µA) -> A x1e-6 | 전압(V) -> V x1, 전류(µA) -> A x1e-06 | PASS |
| 6 | to_dc_sweep: 11 points V 1.0..2.0, I(1.8 V) = 1.5 µA (I–V curve data) | 11 pts, 1.0..2.0 V, 1.5e-6 A | 11 pts, 1..2 V, I(1.8)=1.5000e-06 A, notices=[] | PASS |
| 6 | IDDQ verdict / margin (plan: PASS 40 %) | PASS, 38–42 % (IDDQ 1.5 µA ±0.5 %) | PASS, 40.00 % (IDDQ 1.5000 µA, channel DMM) | PASS |
| 7a | match rate with expected bits (normal file) | 100 %, PASS, 40/40, no mismatch | 100.0 %, PASS, 40/40, first=None | PASS |
| 7a | card 1 full demo (D9/plan 9.1) | PASS 4 · MARGINAL 1 · FAIL 0 | PASS 4 · MARGINAL 1 · FAIL 0 | PASS |
| 7a | PASS set (D9) | iddq, match_rate, rise_time, tpd | ['iddq', 'match_rate', 'rise_time', 'tpd'] | PASS |
| 7a | card 2 (plan 9.1: ! VOH 1.75 V, 하한 1.6 V, 마진 9.4 %) | voh MARGINAL 1.75 V 9.4 % | voh MARGINAL 1.750 V 9.4 % | PASS |
| 7a | card 4 (plan 9.1: ✓ 100 % (40/40)) | 100 %, 40/40, PASS | 100.0 %, 40/40, PASS | PASS |
| 7b | error file: first mismatch cycle 37, rate 97.5 %, FAIL | 37, [37], 97.5 %, FAIL | 37, [37], 97.5 %, FAIL | PASS |
| 7b | summary rule '{n}번째 사이클에서 첫 불일치 (기대 e, 측정 m)' | 37번째 사이클에서 첫 불일치 (기대 1, 측정 0) | 37번째 사이클에서 첫 불일치 (기대 1, 측정 0) | PASS |
| 7b | error file tpLH/tpHL unaffected (no bogus ~100 ns pairing) | worst 6.0 / 5.5 ns ±3 % | 6.019 / 5.522 ns, warnings ['SIM_DEVIATION', 'UNPAIRED_EDGES'] | PASS |
| 7b | card 1 with error file | PASS 3 · MARGINAL 1 · FAIL 1 | PASS 3 · MARGINAL 1 · FAIL 1 | PASS |
| 8 | BANDWIDTH_LIMIT at 100 MHz (limit 7 ns; D8: rise·fall) | fall_time, rise_time | ['fall_time', 'rise_time'] | PASS |
| 8 | summary rule 5 for rise | line '… rise …: 측정값이 오실로스코프 대역폭 한계에 가까움 → …' | ['CH3 rise 2.98 ns: 측정값이 오실로스코프 대역폭 한계에 가까움 → 실제 값은 더 짧을 수 있음', 'CH3 fall 2.51 ns: 측정값이 오실로스코프 대역폭 한계에 가까움 → 실제 값은 더 짧을 수 있음'] | PASS |
| 8 | BANDWIDTH_LIMIT notices | 2 notices (rise, fall) | ['CH3 rise 평균 2.98 ns < 대역폭 한계 7.00 ns (2 × 0.35 / 100 MHz) → 실제 값은 더 짧을 수 있음', 'CH3 fall 평균 2.51 ns < 대역폭 한계 7.00 ns (2 × 0.35 / 100 MHz) → 실제 값은 더 짧을 수 있음'] | PASS |
| 8 | verdicts unchanged by bandwidth | same as step 7 | True | PASS |
