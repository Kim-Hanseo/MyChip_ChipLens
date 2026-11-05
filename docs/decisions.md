# Orchestrator 결정 사항 (Phase 0 MVP)

> 기획서(`docs/chiplens_plan.md`)의 모호한 부분을 Orchestrator가 확정한 내용. 모든 에이전트는 기획서와 함께 이 문서를 따른다.
> 이 문서와 기획서가 충돌하면 이 문서가 우선한다. 변경은 Orchestrator만 한다.

## D1. 저장소 구조와 실행

- 저장소 루트 = 기획서 6.3의 `chiplens/`. 최상위 패키지: `core/`, `synth/`, `app_streamlit/`, 테스트는 `tests/`.
- Python: `.venv/Scripts/python` (Windows, Python 3.12). 설치된 주요 버전: numpy 2.5, pandas 3.1(기본 문자열 dtype·Copy-on-Write 주의), scipy 1.18, pydantic 2.14, plotly 7.1, streamlit 1.66, pytest 9.2, openpyxl 3.1.
- 테스트: `.venv/Scripts/python -m pytest -q` (pyproject의 `pythonpath = ["."]`).
- 앱: `.venv/Scripts/python -m streamlit run app_streamlit/app.py`.
- `core/`는 **streamlit·plotly를 import하지 않는다** (numpy·scipy·pandas·openpyxl·pydantic만).
- 기획서 4.1 "제외(Out)" 항목은 코드로 만들지 않는다. `TODO.md`에만 남기고, 필요하면 확장 지점에 한 줄 `# TODO(Phase N): ...` 주석만 단다. `api/`, `web/`, `core/plugins/` 디렉터리도 만들지 않는다.

## D2. 단위

- 모든 모델 값은 SI 기본 단위: s, V, A, W, Hz. 비율 지표(duty, 일치율)와 마진·편차는 **퍼센트 숫자**(25.0 = 25 %).
- 표시 단위(ns, µA, mV …)는 지표 카탈로그의 `display_unit`/`display_scale`로만 변환한다.
- 단위 접두사는 `µ`(U+00B5), `μ`(U+03BC), `u` 모두 마이크로로 인식한다.

## D3. 채널 식별

- `channel_id`가 정식 키다. 기본값 = 측정 파일의 열 이름(예: `CH1`).
- 경로(`Path`)는 `channel_id`로 입력/출력 채널을 가리킨다.
- 시뮬 파일의 열은 정규화 단계에서 **측정 채널의 `channel_id`로 다시 키를 붙인다** (시뮬 열 → 측정 채널 매핑, UI에서 지정·자동 제안). 따라서 측정과 시뮬에 **같은 ChannelMap·같은 Path·같은 알고리즘**이 그대로 적용된다.

## D4. MVP 지표 ID와 정의

| metric_id | 범주 | 단위 | 대상 | `value`(판정에 쓰는 값) | 시뮬 비교 |
|---|---|---|---|---|---|
| `rise_time` | timing | s | OUT 채널 | 엣지별 10→90 %(실측 low/high 레벨 기준) 중 **최댓값** | O |
| `fall_time` | timing | s | OUT 채널 | 엣지별 90→10 % 중 최댓값 | O |
| `tplh` | timing | s | 경로 | 입력 50 % → 출력 50 %(출력 상승) 엣지별 중 최댓값 | O |
| `tphl` | timing | s | 경로 | 같은 방식(출력 하강) 최댓값 | O |
| `tpd` | timing | s | 경로 | max(tplh 최댓값, tphl 최댓값). "tpd" 스펙은 이 지표를 판정 | X (파생) |
| `period` | timing | s | CLK 채널 | 연속 상승 엣지 간격 평균 | O |
| `frequency` | timing | Hz | CLK 채널 | 1 / period 평균 | X |
| `duty_cycle` | timing | % | CLK 채널 | high 구간 / 주기 평균 | O |
| `setup_slack` | timing | s | DATA·OUT 채널 vs CLK 상승 | 데이터 전이(50 %)마다 (다음 CLK 상승 − 전이 시각), **최솟값** | O |
| `hold_slack` | timing | s | DATA·OUT 채널 vs CLK 상승 | 데이터 전이마다 (전이 시각 − 직전 CLK 상승), 최솟값 | O |
| `voh` | dc | V | OUT 채널 | 안정 구간(엣지 주변 제외) high 레벨 대표값 | O |
| `vol` | dc | V | OUT 채널 | 같은 방식 low 레벨 | O (시뮬값 0이면 편차 None) |
| `idd_avg` | dc | A | IDD 채널 | 전체 평균 | X |
| `avg_power` | dc | W | IDD 채널 | VDD × idd_avg (VDD 채널이 있으면 그 평균, 없으면 논리 VDD) | X |
| `iddq` | dc | A | DC 스윕 | 스윕을 논리 VDD에서 선형 보간한 전류 | X |
| `match_rate` | functional | % | OUT 채널 (기대 비트열 있을 때) | 일치 사이클 / 비교 사이클 × 100 | X |

- 50 % / 10 % / 90 % 기준은 **그 채널의 실측 low/high 레벨** 기준(B10). 기능 샘플링 임계만 논리 VDD/2.
- 여러 엣지에서 나온 지표: `value` = 최악값, `stats` = mean/min/max/std/n. 상승·하강 각각 엣지 1개 이상 없으면 그 지표는 결과에서 빠지거나 `value=None` + 경고.
- 경로 극성: `non_inverting`(입력 상승 → 출력 상승) / `inverting`. 입력 엣지마다 **같은 극성의 다음 출력 엣지**를 짝짓되, 짝짓기 창은 "다음 입력 엣지 전" **그리고** "입력 엣지 간 최소 간격의 0.5배 이내". 창 밖이면 그 입력 엣지는 버린다(오류 주입 파일에서 엉뚱한 100 ns tpd가 나오지 않도록).
- I–V 곡선은 지표가 아니라 `DCSweep` 데이터 그 자체로 DC 탭에 그린다.

## D5. 스펙 판정 (기획서 2.5)

- `Spec(metric_id, path=None, channel_id=None, min=None, max=None)`. path/channel이 None이면 그 metric_id의 모든 결과에 적용.
- 마진: 상한 `(max − v)/|max| × 100`, 하한 `(v − min)/|min| × 100`, 범위는 둘 중 작은 값. 한계값이 0이면 margin=None, PASS/FAIL만.
- 등급: PASS 마진 ≥ T, MARGINAL 0 ≤ 마진 < T, FAIL 마진 < 0. T = `marginal_threshold_pct`(기본 10).
- `match_rate`는 마진 없이 판정: 기대 비트열이 있으면 100 %일 때 PASS, 아니면 FAIL (margin=None).
- 스펙도 기대 비트열도 없는 결과는 verdict=None(회색 "스펙 없음").

## D6. 시뮬 대비 편차

- 시뮬 파형에도 같은 매핑·같은 분석기를 돌려 지표를 뽑고 `(metric_id, path, channel_id)`로 짝짓는다.
- 편차 = `((측정 mean − offset) − 시뮬 mean) / |시뮬 mean| × 100`. **mean(대표값) 끼리 비교**(판정은 worst, 편차는 mean). offset = `delay_offset_s`(PCB·프로브 지연 보정, 기본 0)이며 `tplh`/`tphl`에만 적용.
- 시뮬값이 0이거나 없으면 편차 None. |편차| > `sim_tolerance_pct`(기본 20)이면 경고 코드 `SIM_DEVIATION`.
- 파형 겹쳐 보기는 각 세트의 첫 CLK 상승 엣지 시각으로 시간축을 맞춘 **표시 전용**.

## D7. 기능 검증

- OUT 채널을 CLK 상승 50 % 교차 시각마다 선형 보간으로 샘플링, 임계 = 논리 VDD/2 → 0/1.
- 사이클 번호는 **1부터**: n번째 사이클 = 기록 안의 n번째 CLK 상승 엣지.
- 기대 비트열: '0'/'1'만 유효(공백·`_`·`,` 무시). min(길이)만큼 비교, 길이가 다르면 경고.
- 결과: 측정 비트열, 기대 비트열, 불일치 사이클 목록(1-based), 첫 불일치 사이클, 일치율.

## D8. 장비 대역폭 경고

- 대역폭 BW가 입력되면 `rise_time`/`fall_time`의 **mean** < 2 × 0.35 / BW 일 때 경고 코드 `BANDWIDTH_LIMIT`.
- 데모: 500 MHz → 한계 1.4 ns → 경고 없음 / 100 MHz → 한계 7 ns → rise·fall 경고.

## D9. 요약 카드와 요약 문구

- 카드1 전체 판정: verdict가 있는 모든 결과(스펙 판정 + match_rate)의 PASS/MARGINAL/FAIL 개수.
  - 데모 전체(스펙 4개 + DMM + 기대 비트열): tpd·rise_time·iddq·match_rate = PASS 4, voh = MARGINAL 1, FAIL 0 (기획서 9.1 카드 예시와 일치).
- 카드2 최악 마진: margin이 있는 결과 중 최소 마진.
- 카드3 시뮬 최대 편차: |편차| 내림차순 상위 2개 + 경고 개수. 이미 뽑힌 항목과 같은 지표 family(rise/fall = `edge_rate`, tplh/tphl/tpd = `prop_delay` …)는 건너뛴다(schema-architect 제안, Orchestrator 승인 — 9.1 카드 예시와 일치). 데모: rise +50 %, tplh +33 % … 타이밍 경고 4개(tplh, tphl, rise_time, fall_time).
- 카드4 기능 일치율: 일치율, 일치/전체 사이클, 첫 불일치.
- 요약 문구(한국어, 결정적, 아래 순서, 최대 8줄):
  0. 헤드라인: 전체 판정 개수 + 최악 마진 지표
  1. FAIL: `"{경로} {지표} {값} — 스펙 {스펙} 위반 (FAIL)"` (경로 없으면 채널)
  1b. MARGINAL: `"{경로} {지표} {값} — 스펙 {스펙} 대비 마진 {m}% (MARGINAL)"`
  2. 기능 불일치: `"{n}번째 사이클에서 첫 불일치 (기대 {e}, 측정 {m})"`
  3. 공통 지연 증가: D = 시뮬 편차가 있는 `tplh`/`tphl`/`rise_time`/`fall_time` 전체. |D| ≥ 2, 모두 > +허용편차, max(D)/min(D) ≤ 2 → `"전 경로 공통 지연 증가 → 측정 경로(패드·PCB·프로브) 지연, VDD 강하, 공정 코너 가능성"`
  4. 특정 경로만 느림(경로 ≥ 2일 때만): 경로별 mean(tplh, tphl 편차)가 허용편차 초과이고 나머지 경로 중앙값보다 허용편차 이상 크면 `"{경로}만 시뮬 대비 +{편차}% → 해당 경로 부하·배선 기생 확인 필요"`. 4가 나오면 3은 내지 않는다.
  5. 대역폭 한계: `"{채널} {지표} {값}: 측정값이 오실로스코프 대역폭 한계에 가까움 → 실제 값은 더 짧을 수 있음"`
- 값 표시는 카탈로그 표시 단위로 유효숫자 3자리(예: `6.03 ns`, `1.75 V`, `1.50 µA`), 마진·편차는 소수 1자리.

## D10. 결정성

- `AnalysisReport`에는 타임스탬프·난수 ID를 넣지 않는다. 같은 입력으로 `run_analysis`를 두 번 부르면 `model_dump_json()`이 **바이트 단위로 같아야** 한다.
- 정렬 순서가 있는 모든 목록(결과, 경고, 문구)은 결정적 순서로 정렬한다.

## D11. 합성 데이터 정답 사양 (부록 A 구체화) — parser-agent 생성, analysis-agent 검증

공통: 난수 시드 `20261105`(numpy `default_rng`). 정상 파일과 오류 파일은 같은 시드 → 37번째 사이클 주변 OUT·IDD 외에는 동일. 출력 위치 `synth/data/`, 생성 명령 `python -m synth.generate`.

**타이밍 기준** (τ = 기록 시작부터의 시간)
- CLK 10 MHz, 0 ↔ 1.8 V, rise/fall 1.0 ns(10–90 %, 전체 길이 1.25 ns 선형 램프), 시작은 low.
  - 상승 50 % 교차: τ = 25.03 ns + 100k ns (k = 0…39), 하강 50 % 교차: τ = 75.03 ns + 100k ns. (0.03 ns는 교차점을 샘플 격자 밖에 두기 위함)
- IN: 40비트 PRBS7(x⁷+x⁶+1, 시드 0x7F)의 앞 40비트. 0 ↔ 1.8 V, rise/fall 1.0 ns. bit0은 처음부터, bit k(k ≥ 1)는 CLK 하강 k−1 (τ = 75.03 + 100(k−1) ns)에서 시작 — 그 시각이 IN의 50 % 교차. 생성기는 0→1, 1→0 전이가 각각 8개 이상인지 assert.
- OUT 논리열 o = IN 비트(오류 파일은 o[36] 반전 = 37번째 사이클). 비트가 바뀌는 하강 엣지 시각 + tpLH 6.0 ns(0→1) / tpHL 5.5 ns(1→0)이 OUT의 50 % 교차. 50 % 교차를 중심으로 선형 램프: rise 3.0 ns(10–90 %, 전체 3.75 ns), fall 2.5 ns(전체 3.125 ns). VOL 0.05 V, VOH 1.75 V. 초기 레벨 = o[0].
- 링잉: CLK·IN·OUT의 모든 전이에서 램프 끝(t_end)부터 `A·sin(2π·250 MHz·(t−t_end))·exp(−(t−t_end)/2 ns)`, 전이 방향으로 오버슈트, 피크가 스윙의 5 %가 되도록 A 결정.
- 노이즈: CLK·IN·OUT 가우시안 σ 10 mV, IDD σ 1 µA.
- IDD: 기저 전류 + OUT 전이마다 가우시안 스파이크(피크 1.5 mA, σ 0.5 ns, OUT 50 % 교차 시각). 노이즈 전 평균이 정확히 120 µA가 되도록 기저를 맞춤.

**파일**
1. `synth_scope.csv` / `synth_scope_err.csv` — 5 GS/s(Δt 0.2 ns), 20 000점, 시간 열 t = −2.0 µs + nΔt (트리거 중앙). 형식:
   ```
   Model,ChipLens-SynthScope
   Sample Interval,2.000000E-10
   Record Length,20000
   Trigger Position,-2.000000E-06
   Time(s),CH1(V),CH2(V),CH3(V),CH4(A)
   -2.0000000000E-06,...
   ```
   CH1=CLK, CH2=IN, CH3=OUT, CH4=IDD(A). UTF-8.
2. `synth_sim.csv` — ngspice `wrdata` 흉내(`wr_vecnames` 켜짐, `wr_singlescale` 꺼짐): **공백 구분**, 첫 줄 헤더 `time v(clk) time v(in) time v(out)`(벡터마다 시간 열 반복), 과학 표기. Δt 0.1 ns, τ 0~4 µs(t = τ), 노이즈·링잉 없음. CLK·IN 타이밍 동일, OUT: tpLH 4.5, tpHL 4.2, rise 2.0, fall 1.8 ns, VOH 1.80, VOL 0.00 V. IDD 없음.
3. `synth_dmm.xlsx` — 시트 `DC측정`: A1:C1 병합 제목 `멀티미터 DC 측정 — 칩 #1, 25 °C`, 2행 빈 줄, 3행 헤더 `전압(V)`, `전류(µA)`(U+00B5), `비고`, 4~14행 V = 1.0…2.0(0.1 간격), I[µA] = round(1.5·exp((V−1.8)/0.25), 4) (1.8 V에서 정확히 1.5), 1.8 V 행 비고 `IDDQ 기준`. 시트 `조건`: 칩 ID·온도·장비 키-값 표.
4. `golden.json` — 위 파라미터 전부 + 40비트 문자열 + 아래 정답표.

**정답표 (golden)**

| 항목 | 정답 | 허용 오차(golden test) |
|---|---|---|
| tplh / tphl (mean, worst) | 6.0 / 5.5 ns | ≤ 3 % |
| rise_time / fall_time (mean, worst) | 3.0 / 2.5 ns | ≤ 3 % |
| voh / vol | 1.75 / 0.05 V | ≤ 1 % (vol은 ±0.5 mV → 엣지 주변 제외한 안정 구간 중앙값 수준의 정밀도 필요) |
| period / frequency / duty | 100 ns / 10 MHz / 50 % | ≤ 1 % |
| setup_slack / hold_slack (worst) | 44.0 / 55.5 ns | ≤ 3 % |
| idd_avg / avg_power(논리 VDD 1.8 V) | 120 µA / 216 µW | ≤ 1 % |
| iddq (DMM, 1.8 V) | 1.5 µA | ≤ 0.5 % |
| match_rate | 100 % (40/40) / 오류 파일 97.5 %, 첫 불일치 37 | 정확히 |
| 오류 파일 tplh/tphl | 정상과 같음(엉뚱한 짝짓기 없음) | ≤ 3 % |
| 시뮬 tplh / tphl / rise / fall / voh | 4.5 / 4.2 / 2.0 / 1.8 ns / 1.80 V | ≤ 3 %(타이밍), ≤ 1 %(레벨) |
| 시뮬 편차 tplh / tphl / rise / fall / voh | +33.3 / +31.0 / +50.0 / +38.9 / −2.8 % | ±2 %p |
| 데모 판정 tpd(≤ 8 ns) / rise(≤ 4 ns) / voh(≥ 1.6 V) / iddq(≤ 2.5 µA) | PASS ≈25 % / PASS ≈25 % / MARGINAL 9.4 % / PASS 40 % | 등급 정확, 마진 ±2 %p |

> 참고: 판정은 최악값(worst)이므로 노이즈 σ 10 mV 때문에 tpd·rise 마진은 25 %보다 약간 작게(≈24 %) 나오는 것이 정상이다.
