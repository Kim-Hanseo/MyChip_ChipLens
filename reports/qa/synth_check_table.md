| # | item | expected | actual | result |
|---|---|---|---|---|
| 1 | PRBS7 x^7+x^6+1 seed 0x7F first 40 bits (QA LFSR) == golden.bits | 0000001000001100001010001111001000101100 | 0000001000001100001010001111001000101100 | PASS |
| 2 | IN 0->1 / 1->0 transitions each >= 8 | >= 8 / >= 8 | 8 / 8 | PASS |
| 3 | error bits = o[36] inverted (cycle 37) | 0000001000001100001010001111001000100100 | 0000001000001100001010001111001000100100 | PASS |
| 4 | synth_scope.csv: UTF-8 decodable, no BOM | utf-8 | utf-8 ok | PASS |
| 5 | synth_scope.csv: 5 header lines (D11 format) | ['Model,ChipLens-SynthScope', 'Sample Interval,2.000000E-10', 'Record Length,20000', 'Trigger Position,-2.000000E-06', 'Time(s),CH1(V),CH2(V),CH3(V),CH4(A)'] | ['Model,ChipLens-SynthScope', 'Sample Interval,2.000000E-10', 'Record Length,20000', 'Trigger Position,-2.000000E-06', 'Time(s),CH1(V),CH2(V),CH3(V),CH4(A)'] | PASS |
| 6 | synth_scope.csv: data rows (20,000 per channel) | 20000 | 20000 | PASS |
| 7 | synth_scope.csv: columns (time + CH1..CH4) | 5 | 5 | PASS |
| 8 | synth_scope.csv: t = -2.0 us + n*0.2 ns (5 GS/s) | max err < 1e-15 s | 8.47e-22 | PASS |
| 9 | synth_scope.csv: record length 4 us | 4e-06 | 4.000000e-06 | PASS |
| 10 | synth_scope.csv: CH1 CLK - D11 reference (ramps+ringing) = gaussian noise | std 0.01 V, /max/ < 6 sigma | mean -4.62e-05, std 0.01001, /max/ 0.041 | PASS |
| 11 | synth_scope.csv: CH2 IN - D11 reference (ramps+ringing) = gaussian noise | std 0.01 V, /max/ < 6 sigma | mean -1.77e-05, std 0.009967, /max/ 0.0392 | PASS |
| 12 | synth_scope.csv: CH3 OUT - D11 reference (ramps+ringing) = gaussian noise | std 0.01 V, /max/ < 6 sigma | mean -6.02e-05, std 0.01003, /max/ 0.0397 | PASS |
| 13 | synth_scope.csv: CH4 IDD - D11 reference (ramps+ringing+spikes) = gaussian noise | std 1e-06 A, /max/ < 6 sigma | mean 2e-09, std 9.915e-07, /max/ 3.97e-06 | PASS |
| 14 | synth_scope.csv: ringing present on OUT (residual w/o ringing |max| > 60 mV) | > 0.06 V | 0.101 V | PASS |
| 15 | synth_scope.csv: IDD mean ~ 120 uA | 120 uA +/- 0.05 uA | 120.0020 uA | PASS |
| 16 | synth_scope.csv: IDD spikes peak ~1.5 mA at OUT transitions | max ~ 1.5 mA + base | 1.612 mA | PASS |
| 17 | synth_scope.csv: OUT sampled at 40 CLK rises (QA) == o | 0000001000001100001010001111001000101100 | 0000001000001100001010001111001000101100 | PASS |
| 18 | synth_scope.csv: CLK rise 50% crossings at tau = 25.03 ns + 100k ns | 40 crossings, max err < 0.1 ns | 40, max err 0.007 ns | PASS |
| 19 | synth_scope_err.csv: UTF-8 decodable, no BOM | utf-8 | utf-8 ok | PASS |
| 20 | synth_scope_err.csv: 5 header lines (D11 format) | ['Model,ChipLens-SynthScope', 'Sample Interval,2.000000E-10', 'Record Length,20000', 'Trigger Position,-2.000000E-06', 'Time(s),CH1(V),CH2(V),CH3(V),CH4(A)'] | ['Model,ChipLens-SynthScope', 'Sample Interval,2.000000E-10', 'Record Length,20000', 'Trigger Position,-2.000000E-06', 'Time(s),CH1(V),CH2(V),CH3(V),CH4(A)'] | PASS |
| 21 | synth_scope_err.csv: data rows (20,000 per channel) | 20000 | 20000 | PASS |
| 22 | synth_scope_err.csv: columns (time + CH1..CH4) | 5 | 5 | PASS |
| 23 | synth_scope_err.csv: t = -2.0 us + n*0.2 ns (5 GS/s) | max err < 1e-15 s | 8.47e-22 | PASS |
| 24 | synth_scope_err.csv: record length 4 us | 4e-06 | 4.000000e-06 | PASS |
| 25 | synth_scope_err.csv: CH1 CLK - D11 reference (ramps+ringing) = gaussian noise | std 0.01 V, /max/ < 6 sigma | mean -4.62e-05, std 0.01001, /max/ 0.041 | PASS |
| 26 | synth_scope_err.csv: CH2 IN - D11 reference (ramps+ringing) = gaussian noise | std 0.01 V, /max/ < 6 sigma | mean -1.77e-05, std 0.009967, /max/ 0.0392 | PASS |
| 27 | synth_scope_err.csv: CH3 OUT - D11 reference (ramps+ringing) = gaussian noise | std 0.01 V, /max/ < 6 sigma | mean -6.02e-05, std 0.01003, /max/ 0.0397 | PASS |
| 28 | synth_scope_err.csv: CH4 IDD - D11 reference (ramps+ringing+spikes) = gaussian noise | std 1e-06 A, /max/ < 6 sigma | mean 2e-09, std 9.915e-07, /max/ 3.97e-06 | PASS |
| 29 | synth_scope_err.csv: ringing present on OUT (residual w/o ringing |max| > 60 mV) | > 0.06 V | 0.101 V | PASS |
| 30 | synth_scope_err.csv: IDD mean ~ 120 uA | 120 uA +/- 0.05 uA | 120.0020 uA | PASS |
| 31 | synth_scope_err.csv: IDD spikes peak ~1.5 mA at OUT transitions | max ~ 1.5 mA + base | 1.612 mA | PASS |
| 32 | synth_scope_err.csv: OUT sampled at 40 CLK rises (QA) == o_err | 0000001000001100001010001111001000100100 | 0000001000001100001010001111001000100100 | PASS |
| 33 | synth_scope_err.csv: CLK rise 50% crossings at tau = 25.03 ns + 100k ns | 40 crossings, max err < 0.1 ns | 40, max err 0.007 ns | PASS |
| 34 | err vs normal: Time, CH1, CH2 byte-identical values | True | True | PASS |
| 35 | err vs normal: CH3/CH4 differ only near cycle 37 (tau 3.5-3.75 us) | diff window inside [3.50, 3.75] us | [3.5782, 3.7122] us | PASS |
| 36 | synth_sim.csv: header 'time v(clk) time v(in) time v(out)' (wr_vecnames, repeated time) | time v(clk) time v(in) time v(out) | time v(clk) time v(in) time v(out) | PASS |
| 37 | synth_sim.csv: whitespace separated, scientific notation | no commas, 'e' notation |  0.00000000e+00  0.00000000e+00  0.00000000e+00  0.00000000e | PASS |
| 38 | synth_sim.csv: rows tau 0..4 us at 0.1 ns | 40001 | 40001 | PASS |
| 39 | synth_sim.csv: t = tau = n*0.1 ns | max err < 1e-15 | 8.47e-22 | PASS |
| 40 | synth_sim.csv: repeated time columns identical | True | True | PASS |
| 41 | synth_sim.csv: v(clk) == D11 noise-free, ringing-free reference | max err < 1e-6 V | 1.36e-12 V | PASS |
| 42 | synth_sim.csv: v(in) == D11 noise-free, ringing-free reference | max err < 1e-6 V | 8.02e-13 V | PASS |
| 43 | synth_sim.csv: v(out) == D11 noise-free, ringing-free reference | max err < 1e-6 V | 3.55e-13 V | PASS |
| 44 | synth_dmm.xlsx: sheets | ['DC측정', '조건'] | ['DC측정', '조건'] | PASS |
| 45 | DC측정: A1:C1 merged title | A1:C1 | ['A1:C1'] | PASS |
| 46 | DC측정: title text | 멀티미터 DC 측정 — 칩 #1, 25 °C | 멀티미터 DC 측정 — 칩 #1, 25 °C | PASS |
| 47 | DC측정: row 2 blank | [None, None, None] | [None, None, None] | PASS |
| 48 | DC측정: row 3 headers (µ = U+00B5) | ['전압(V)', '전류(µA)', '비고'] | ['전압(V)', '전류(µA)', '비고'] | PASS |
| 49 | DC측정: '전류(µA)' uses U+00B5 MICRO SIGN | U+00B5 | U+00B5 | PASS |
| 50 | DC측정: rows 4-14 V=1.0..2.0 step 0.1, I=round(1.5 exp((V-1.8)/0.25),4) uA, 1.8 V note 'IDDQ 기준' | 11 rows exact | 11 rows, 1.8V row = (1.8, 1.5, 'IDDQ 기준') | PASS |
| 51 | DC측정: nothing below row 14 | None | None | PASS |
| 52 | DC측정: IDDQ(1.8 V) = 1.5 uA exactly | 1.5 | 1.5 | PASS |
| 53 | 조건 sheet: key-value table (chip ID, temperature, instrument) | chip/온도/장비 keys present | [['항목', '값'], ['칩 ID', '#1'], ['온도(°C)', 25], ['장비', 'ChipLens-SynthDMM (합성 데이터)'], ['측정', 'VDD 스윕 1.0–2.0 V, 0.1 V 간격, IDD 측정']] | PASS |
