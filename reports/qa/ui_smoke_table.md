| 단계 | 확인 항목 | 기대 | 실제 | 결과 |
|---|---|---|---|---|
| 0 | app starts | no exception / no error | [] | PASS |
| 0 | sample-data multiselect lists synth/data files | 4 files (dmm, scope, scope_err, sim) | ['synth_dmm.xlsx', 'synth_scope.csv', 'synth_scope_err.csv', 'synth_sim.csv'] | PASS |
| 1 | select synth_scope.csv (kind auto = 파형) | no error; roles widgets CH1..CH4 | errors=[], role keys=['role::CH1', 'role::CH2', 'role::CH3', 'role::CH4'] | PASS |
| 1 | file panel shows 4ch x 20,000 pts | '4채널 · 20,000점' | True | PASS |
| 2 | demo defaults: roles / logic VDD / bandwidth | CLK IN OUT IDD, 1.8, 500 | ['CLK', 'IN', 'OUT', 'IDD'], 1.8, 500.0 | PASS |
| 3 | spec table -> SI caption | tpd ≤ 8 ns · rise ≤ 4 ns · voh ≥ 1.6 V · iddq ≤ 2.5 µA | SI 변환 확인: tpd ≤ 8.00 ns · rise_time ≤ 4.00 ns · voh ≥ 1.60 V · iddq ≤ 2.50 µA | PASS |
| 2 | path Buffer in base rows | Buffer CH2->CH3 | [{'이름': 'Buffer', '입력 채널': 'CH2', '출력 채널': 'CH3', '극성': '비반전'}] | PASS |
| 4 | sim mapping auto-suggested | '매핑: v(clk) → CH1 · v(in) → CH2 · v(out) → CH3' | 매핑: v(clk) → CH1 · v(in) → CH2 · v(out) → CH3 | PASS |
| 4 | no error | [] | [] | PASS |
| 5 | run -> dashboard, no exception/error | [] | [] | PASS |
| 5 | card 1 | ✓ PASS 2 · ! MARGINAL 1 · ✕ FAIL 0 | True | PASS |
| 5 | card 2 worst margin | ! VOH 1.75 V / 마진 9.4% | ['#### :orange[! VOH 1.75 V]', '- CH3 VOH 1.75 V — 스펙 ≥ 1.60 V 대비 마진 9.4% (MARGINAL)', 'CH3 · 스펙 ≥ 1.60 V · 마진 9.4%'] | PASS |
| 5 | card 3 sim deviation (plan: rise +50 % · tpLH +33 % 경고) | rise(CH3) +~50% · tpLH(Buffer) +~33%, 경고 4건 | #### :orange[rise(CH3) +49.2% · tpLH(Buffer) +33.4%] / True | PASS |
| 5 | summary rule 3 on screen | 전 경로 공통 지연 증가 … | True | PASS |
| 5 | UI timing (run_analysis / click->report) | < 3 s (plan 1.3) | {'run_s': 0.036198999965563416, 'total_s': 0.03756349999457598} | PASS |
| 5 | AppTest wall time for the click (incl. dashboard render) | info | 0.43 s | PASS |
| 6 | DMM xlsx loaded as DC 스윕 'DMM' | no error, caption 'DC 스윕 1개: DMM' | [] | PASS |
| 6 | IDDQ PASS 40 % (report in session) | PASS 40.0 % | PASS 40.0 | PASS |
| 6 | card 1 after DMM | ✓ PASS 3 · ! MARGINAL 1 | True | PASS |
| 6 | no error | [] | [] | PASS |
| 6 | DC tab renders I–V chart + IDDQ tile | plotly chart 'dash_iv_chart', metric IDDQ 1.50 µA | charts=3, IDDQ metric=['1.50 µA'] | PASS |
| 7 | sample bits button fills 40 bits | 40-bit string | 40 bits | PASS |
| 7 | card 4 = ✓ 100% (40/40 사이클) | ✓ 100% (40/40 사이클) | True | PASS |
| 7 | card 1 full demo (D9) | ✓ PASS 4 · ! MARGINAL 1 · ✕ FAIL 0 | True | PASS |
| 7 | roles kept after swapping measured file | CLK IN OUT IDD | ['CLK', 'IN', 'OUT', 'IDD'] | PASS |
| 7 | error file: first mismatch 37 on card 4 + summary | 첫 불일치: 37번째 사이클 / 37번째 사이클에서 첫 불일치 (기대 1, 측정 0) | [True, True] | PASS |
| 7 | card 4 ✕ 97.5% (39/40) | ✕ 97.5% (39/40 사이클) | True | PASS |
| 7 | no exception/error | [] | [] | PASS |
| 8 | bandwidth 100 MHz -> rise (and fall) limit warning on screen | 'CH3 rise 2.98 ns: 측정값이 오실로스코프 대역폭 한계에 가까움 …' | ['- CH3 rise 2.98 ns: 측정값이 오실로스코프 대역폭 한계에 가까움 → 실제 값은 더 짧을 수 있음', '- CH3 fall 2.51 ns: 측정값이 오실로스코프 대역폭 한계에 가까움 → 실제 값은 더 짧을 수 있음', '- ! `BANDWIDTH_LIMIT` CH3 rise 평균 2.98 ns < 대역폭 한계 7.00 ns (2 × 0.35 / 100 MHz) → 실제 값은 더 짧을 수 있음', '- ! `BA | PASS |
| 8 | header shows 대역폭 100 MHz | 대역폭 100 MHz | True | PASS |
| 8 | no exception/error | [] | [] | PASS |
| 9 | all 6 dashboard tabs render | no exception | [] | PASS |
