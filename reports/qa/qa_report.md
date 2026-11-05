# ChipLens Phase 0 MVP — QA 리포트

- 작성: qa-agent (독립 검증, 구현 미참여) · 2026-11-06
- 판단 기준: `docs/chiplens_plan.md` 4.2 · 4.4 · 부록 A, `docs/decisions.md` D9 · D11. 구현 쪽 테스트나 주석, golden.json은 근거로 쓰지 않고 직접 다시 확인했다.
- 구현 코드는 수정하지 않았다. 이번 작업에서 쓴 파일은 모두 `reports/qa/` 아래에 있다.

## 0. 결론

| 항목 | 결과 |
|---|---|
| 4.4 완료 기준 4개 | **4/4 충족** |
| 데모 시나리오 1~8 (core 공개 API, UI와 같은 호출 순서) | 39/39 PASS |
| 데모 시나리오 1~8 (UI, `AppTest`) | 32/32 PASS, 예외 0 · `st.error` 0 |
| golden (D11 정답표 · 허용 오차) | 38/38 PASS |
| 합성 데이터 vs 부록 A/D11 사양 (파일 직접 대조) | 53/53 PASS |
| pytest 전체 (참고용) | 288 passed (34.3 s) |
| 버그 | 차단 0 · 높음 0 · 중간 0 · **낮음 1** (QA-01, UX) |
| 4.1 제외 항목 구현 흔적 | 없음. 8개 항목 모두 `TODO.md`에 있음 |

4.2의 기대 문구와 실제 값이 다른 곳(마진 24.8 %/24.4 %, rise 편차 +49.2 %)은 모두 D11 허용 오차(±2 %p) 안이다. 원인은 데이터 노이즈다(§3.2). 버그 아님.

## 1. 환경 · 재현 방법

- Python: `.venv/Scripts/python`(Windows, Git Bash). 결과는 모두 `PYTHONIOENCODING=utf-8`로 실행해 얻었다.
- 스크립트(모두 `reports/qa/`):

| 스크립트 | 내용 | 결과 표 |
|---|---|---|
| `qa_check_synth.py` | D11 문장만으로 기준 파형(PRBS7·램프·링잉·IDD)을 다시 만들어 파일과 대조 | `synth_check_table.md` |
| `qa_demo_e2e.py` | 4.2 단계 1~8, 파일 바이트 → `preview_file` → `read_table` → `to_waveforms`/`to_dc_sweep`(+`suggest_sim_mapping`) → `MeasurementSet`/`AnalysisRequest` → `run_analysis` | `demo_e2e_table.md`, `golden_table.md`, `out/step*_report.json` |
| `qa_ui_smoke.py` | `streamlit.testing.v1.AppTest`로 4.2 단계 1~8 진행 | `ui_smoke_table.md` |
| `qa_det_purity_perf.py` | 4.4 #3(결정성, 새 프로세스 2개 포함), #4(core 순수성), 성능 | `det_purity_perf_table.md` |
| `qa_extra_probes.py` | 다른 버튼 순서, 카드 클릭, Evidence, 입력 특이 케이스(cp949·mV·×10) | `extra_probes_table.md` |
| `qa_rise_crosscheck.py` | rise/fall을 파일에서 직접 측정해 core 값과 엣지별로 대조 | (stdout) |

- pytest: `.venv/Scripts/python -m pytest -q` → `288 passed in 34.31s`(`pytest_output.txt`). 판정 근거로는 쓰지 않았다.

## 2. 합성 데이터 vs 부록 A / D11 (53/53 PASS)

golden.json을 근거로 쓰지 않고, D11 문장에서 기준 신호를 독립적으로 다시 만들어 파일과 비교했다.

- **PRBS7**: x⁷+x⁶+1, 시드 0x7F, 앞 40비트 = `0000001000001100001010001111001000101100`. 0→1, 1→0 전이 각 8개. 오류 비트열은 o[36]만 반전(37번째 사이클, 기대 1 → 측정 0).
- **`synth_scope.csv` / `_err.csv`**: UTF-8(BOM 없음). 헤더 5줄이 D11과 글자까지 같다(`Model,…`, `Sample Interval,2.000000E-10`, `Record Length,20000`, `Trigger Position,-2.000000E-06`, `Time(s),CH1(V),CH2(V),CH3(V),CH4(A)`). 데이터 20,000행, t = −2 µs + n·0.2 ns(오차 8.5e-22 s), 길이 4 µs.
  - 파일 − D11 기준(램프 + 링잉, IDD는 기저 + 스파이크)의 잔차가 순수 가우시안이다. CLK/IN/OUT σ = 10.01/9.97/10.03 mV, |max| < 4.1σ. IDD σ = 0.99 µA. 링잉이 실제로 들어 있다(링잉을 빼면 OUT 잔차 101 mV). IDD 평균 120.002 µA, 스파이크 피크 1.61 mA.
  - QA 자체 측정: CLK 상승 40개가 25.03 + 100k ns에서 오차 0.007 ns 이내. CLK 상승 시점에서 샘플링한 OUT은 정상 파일 = PRBS, 오류 파일 = 37번째만 반전.
  - 정상/오류 파일 비교: Time·CH1·CH2 값은 동일. CH3·CH4만 τ 3.578~3.712 µs(37번째 사이클 주변)에서 다르다.
- **`synth_sim.csv`**: 헤더 `time v(clk) time v(in) time v(out)`, 공백 구분, 과학 표기. 40,001행(τ 0~4 µs, 0.1 ns), 반복 시간 열은 모두 같다. 노이즈·링잉 없는 D11 기준과의 최대 오차 1.4e-12 V.
- **`synth_dmm.xlsx`**: 시트 `DC측정`·`조건`. A1:C1 병합 제목 `멀티미터 DC 측정 — 칩 #1, 25 °C`, 2행 빈 줄, 3행 헤더 `전압(V)`·`전류(µA)`(U+00B5 확인)·`비고`. 4~14행 값은 V = 1.0…2.0, I = round(1.5·e^((V−1.8)/0.25), 4)와 정확히 같고, 1.8 V 행 = 1.5 µA, 비고 `IDDQ 기준`. `조건` 시트는 칩 ID·온도·장비 키-값.

## 3. 데모 시나리오 E2E (core 공개 API, UI와 같은 호출 순서)

### 3.1 단계별 표

| 단계 | 기대 (4.2 / 부록 A / D9 / D11) | 실제 | 판정 |
|---|---|---|---|
| 1 업로드 | `preview_file` 자동 추정: 헤더 행 4, 시간 열 `Time(s)`, CH1–3 V · CH4 A. `to_waveforms` 4ch × 20,000점, Δt 0.2 ns, Notice 없음 | header_row 4, `Time(s)`[s], CH1–3[V], CH4[A]. 4 × 20,000, 0.2000 ns, `[]` | PASS |
| 2 매핑 | CH1 CLK · CH2 IN · CH3 OUT · CH4 IDD, `Buffer: CH2 → CH3`, 논리 VDD 1.8 V, BW 500 MHz | 모델 검증 통과 | PASS |
| 3 스펙 | tpd ≤ 8 ns, rise ≤ 4 ns, VOH ≥ 1.6 V, IDDQ ≤ 2.5 µA (표시 단위 → SI) | 8e-9 s / 4e-9 s / 1.6 V / 2.5e-6 A | PASS |
| 4 시뮬 첨부 | wrdata 공백 구분, 반복 시간 열 제거, v(clk)→CH1 · v(in)→CH2 · v(out)→CH3 자동 제안, 측정 channel_id로 다시 키 붙임 | delimiter `' '`, 열 `time, v(clk), v(in), v(out)`, 제안 일치, 3 × 40,001점 · 0.1 ns | PASS |
| 5 분석 | tpd PASS 마진 25 % (D11: ≈25 % ±2 %p) | PASS **24.76 %** (worst 6.019 ns) | PASS(허용 오차 안) |
| 5 | rise PASS 마진 25 % | PASS **24.43 %** (worst 3.023 ns) | PASS(허용 오차 안) |
| 5 | VOH MARGINAL 마진 9.4 % | MARGINAL 9.38 % (VOH 1.7501 V) → 표시 "9.4%" | PASS |
| 5 | 시뮬 대비 tpLH +33 % 경고 | +33.37 %, `SIM_DEVIATION` | PASS |
| 5 | 시뮬 대비 rise +50 % 경고 | **+49.19 %**, `SIM_DEVIATION` | PASS(허용 오차 안) |
| 5 | (부록 A) tpHL +31 %, fall +39 %, 타이밍 경고 4개 | +31.14 % / +39.25 %, 경고 = {tplh, tphl, rise_time, fall_time} | PASS |
| 5 | 카드3 (D9): rise · tpLH 상위 2개, 경고 4 | `rise(CH3) +49.2% · tpLH(Buffer) +33.4%`, "경고 4건" | PASS |
| 5 | 500 MHz에서 대역폭 경고 없음 | 없음 | PASS |
| 5 | 카드1 (DMM 전): PASS 2 · MARGINAL 1 · FAIL 0. 카드2: VOH 9.4 % | 일치 | PASS |
| 5 | 요약 규칙 3 "전 경로 공통 지연 증가 …" | 출력됨 | PASS |
| 6 DMM xlsx | 시트 `DC측정`, 헤더 행 2, `전류(µA)` → A × 1e-6, 11점 I–V | sheet `DC측정`, header_row 2, 전압(V) → V ×1, 전류(µA) → A ×1e-06, 11점 1.0~2.0 V, I(1.8) = 1.5000e-6 A | PASS |
| 6 | IDDQ PASS 마진 40 % | PASS 40.00 % (1.5000 µA, 대상 `DMM`) | PASS |
| 7a 기대 비트열 | 일치율 100 %, 40/40, PASS | 100.0 %, 40/40, PASS, 첫 불일치 없음 | PASS |
| 7a | 카드1 (D9/9.1): PASS 4 (tpd·rise·iddq·match_rate) · MARGINAL 1 (voh) · FAIL 0 | 일치 | PASS |
| 7a | 카드2: ! VOH 1.75 V, 하한 1.6 V, 마진 9.4 %. 카드4: ✓ 100 % (40/40) | 일치 | PASS |
| 7b 오류 파일 | 첫 불일치 37, 97.5 %, FAIL, 문구 "37번째 사이클에서 첫 불일치 (기대 1, 측정 0)" | 37, 불일치 [37], 97.5 %, FAIL, 문구 정확히 일치 | PASS |
| 7b | 오류 파일 tpLH/tpHL이 정상 파일과 같음(엉뚱한 짝짓기 없음, ±3 %) | 6.019 / 5.522 ns (+ `UNPAIRED_EDGES`) | PASS |
| 7b | 카드1: PASS 3 · MARGINAL 1 · FAIL 1 | 일치 | PASS |
| 8 BW 100 MHz | rise에 장비 한계 경고 (D8: rise·fall, 한계 7 ns) | `BANDWIDTH_LIMIT` = {rise_time, fall_time}, 문구 "CH3 rise 2.98 ns: 측정값이 오실로스코프 대역폭 한계에 가까움 → …" | PASS |
| 8 | 판정은 바뀌지 않음 | 단계 7과 같음 | PASS |

전체 39행은 `demo_e2e_table.md`에 있다. 각 단계 보고서 JSON은 `out/`에, 요약 문구는 `out/step*_summary.txt`에 있다.

### 3.2 4.2 기대 문구와 다른 값: 허용 오차인가, 버그인가

| 4.2 문구 | 실제 | 판단 | 근거 |
|---|---|---|---|
| tpd PASS(마진 25 %) | 24.76 % | **허용 오차, 버그 아님** | D11: 등급은 정확히, 마진 ±2 %p. D11 각주가 "판정은 worst이므로 σ 10 mV 노이즈 때문에 ≈24 %가 정상"이라고 명시한다. worst tpd 6.019 ns = 정답 대비 +0.32 % |
| rise PASS(마진 25 %) | 24.43 % | **허용 오차, 버그 아님** | 위와 같다. worst rise 3.023 ns (+0.75 %, golden ≤ 3 %) |
| rise 시뮬 대비 +50 % | +49.19 % (화면 "+49.2%") | **허용 오차, 버그 아님** | D11: 편차 ±2 %p. D6에 따라 편차는 mean끼리 비교한다. 측정 rise mean 2.9837 ns(정답 대비 −0.54 %, golden ≤ 3 % 안)이므로 (2.984 − 2.0)/2.0 = +49.2 %. `qa_rise_crosscheck.py`로 파일에서 직접 잰 엣지별 rise가 core 값과 0.3 ps 이내로 같고(QA mean 2.9835 ns), 엣지 하나(2.917 ns)가 평균을 끌어내린다. 노이즈 실현값 때문이지 알고리즘 편향이 아니다 |
| tpLH +33 % | +33.37 % ("+33.4%") | 일치(반올림) | — |
| VOH 9.4 % · IDDQ 40 % · 100 % · 37번째 | 9.38 % · 40.00 % · 100 % · 37 | 일치 | — |
| 단계 8: "rise time에 경고" | rise와 fall 둘 다 경고 | 정상 | D8이 "100 MHz → rise·fall 경고"로 정했다 |
| (9.1 카드 예시) "rise(Buffer) +50%" | "rise(CH3) +49.2%" | 정상 | D4/계약상 rise_time은 OUT 채널 지표(path None, channel CH3)다. 9.1은 예시 문구이고, D9는 대상 이름을 정하지 않는다 |

### 3.3 golden (4.4 #2, D11 정답표) — 38/38 PASS (`golden_table.md`)

| 항목 | 정답 · 허용 | 실제 |
|---|---|---|
| tplh mean / worst | 6.0 ns ±3 % | 6.0018 / 6.0190 ns |
| tphl mean / worst | 5.5 ns ±3 % | 5.5079 / 5.5215 ns |
| rise mean / worst | 3.0 ns ±3 % | 2.9837 / 3.0226 ns |
| fall mean / worst | 2.5 ns ±3 % | 2.5065 / 2.5537 ns (2.15 %) |
| tpd worst | 6.0 ns ±3 % | 6.0190 ns |
| voh / vol | 1.75 V ±1 % / 0.05 V ±0.5 mV | 1.75007 V / 0.04994 V (−0.056 mV) |
| period / freq / duty | 100 ns / 10 MHz / 50 % ±1 % | 100.0002 ns / 10.0000 MHz / 49.9992 % |
| setup / hold worst (CH3) | 44.0 / 55.5 ns ±3 % | 43.979 / 55.484 ns |
| idd_avg / avg_power | 120 µA / 216 µW ±1 % | 120.002 µA / 216.004 µW |
| iddq | 1.5 µA ±0.5 % | 1.50000 µA |
| match_rate | 100 % (40/40) / 오류 97.5 %, 37 | 100 % (40/40) / 97.5 %, 37 |
| 오류 파일 tplh / tphl | 정상과 같음 ±3 % | 6.0004·6.0190 / 5.5079·5.5215 ns |
| 시뮬 tplh/tphl/rise/fall/voh | 4.5/4.2/2.0/1.8 ns/1.80 V | 4.5000/4.2000/2.0000/1.8000 ns/1.8000 V |
| 편차 tplh/tphl/rise/fall/voh | +33.3/+31.0/+50.0/+38.9/−2.8 % ±2 %p | +33.37/+31.14/+49.19/+39.25/−2.77 % (vol: 시뮬 0 → None) |
| 데모 판정 tpd/rise/voh/iddq | PASS≈25/PASS≈25/MARGINAL 9.4/PASS 40 ±2 %p | PASS 24.76/PASS 24.43/MARGINAL 9.38/PASS 40.00 |

## 4. UI 스모크

### 4.1 `AppTest` (32/32 PASS, `ui_smoke_table.md`)
사용한 위젯 key(app_streamlit 코드에서 읽음): `in_samples`(샘플 데이터 multiselect), `btn_demo_defaults`, `btn_sample_bits`, `btn_run`, `in_bandwidth_mhz`, `role::CH1..4`, `dash_tab`, `dash_card_worst`.

- 단계 1: `synth_scope.csv` 선택 → 종류 자동 '파형', "4채널 · 20,000점", 역할 위젯 CH1..CH4.
- 단계 2·3: "데모 기본값 채우기" → CLK/IN/OUT/IDD, 1.8 V, 500 MHz, 경로 Buffer, 스펙 SI 캡션 `tpd ≤ 8.00 ns · rise_time ≤ 4.00 ns · voh ≥ 1.60 V · iddq ≤ 2.50 µA`.
- 단계 4: 시뮬 추가 → "매핑: v(clk) → CH1 · v(in) → CH2 · v(out) → CH3".
- 단계 5: 분석 실행 → 대시보드. 카드1 `✓ PASS 2 · ! MARGINAL 1 · ✕ FAIL 0`, 카드2 `! VOH 1.75 V` / `CH3 · 스펙 ≥ 1.60 V · 마진 9.4%`, 카드3 `rise(CH3) +49.2% · tpLH(Buffer) +33.4%` + "경고 4건", 요약 규칙 3. UI 측정 시간: run_analysis 0.036 s, 클릭 → 보고서 0.038 s.
- 단계 6: DMM 추가 → "DC 스윕 1개: DMM", IDDQ PASS 40 %, DC 탭에 I–V 차트와 IDDQ 타일 `1.50 µA`.
- 단계 7: "샘플 기대 비트열 넣기"(40비트) → 카드4 `✓ 100% (40/40 사이클)`, 카드1 `✓ PASS 4 · ! MARGINAL 1 · ✕ FAIL 0`. 오류 파일로 바꿔도 역할 유지 → `✕ 97.5% (39/40 사이클)`, "첫 불일치: 37번째 사이클", 요약 "37번째 사이클에서 첫 불일치 (기대 1, 측정 0)".
- 단계 8: 대역폭 100 → 재실행 → 요약·경고에 "CH3 rise 2.98 ns: 측정값이 오실로스코프 대역폭 한계에 가까움 → …"(fall도), 헤더 "대역폭 100 MHz".
- 대시보드 탭 6개(파형·타이밍·DC·전력·기능·시뮬 비교·원본 데이터) 모두 예외 없이 렌더링.
- 추가 프로브(`extra_probes_table.md`): 버튼 순서를 바꿔도(데모 기본값 → 파일 3개 → 비트열 → 실행) 같은 카드가 나온다. 카드2 "파형에서 보기" → 파형 탭으로 가서 `voh||CH3`를 강조한다(9.3). 같은 입력으로 UI에서 2회 실행 → 보고서 JSON 바이트 동일.

### 4.2 실제 서버
`.venv/Scripts/python -m streamlit run app_streamlit/app.py --server.port 8765 --server.headless true` → `GET /` **200**, `/_stcore/health` → `ok`(200). 확인 후 종료했고, 포트 8765가 비었음도 확인했다(`out/streamlit_server.log`).

## 5. 4.4 완료 기준 체크리스트

- [x] **데모 시나리오 1~8이 끊기지 않고 동작**: core API 경로 39/39, UI(AppTest) 32/32. 예외·`st.error` 없음. 한계: `st.file_uploader`의 실제 브라우저 업로드는 AppTest로 조작할 수 없어 검증하지 못했다. 코드상 업로드와 샘플 선택은 같은 `FileEntry(bytes)` 경로로 합쳐진다(`app_streamlit/input_flow.py::_collect_entries`).
- [x] **golden 오차**: tpd·rise/fall ≤ 3 %(최대 2.15 %, fall worst), VOH/VOL ≤ 1 %(VOH 0.004 %, VOL −0.056 mV), 일치율·첫 불일치 위치 정확(100 %·40/40, 97.5 %·37). D11 표 전체 38/38.
- [x] **같은 입력 2회 → 결과 동일**: 같은 프로세스 2회, 파일에서 요청을 다시 만든 경우, 오류 파일 + 100 MHz 2회, **새 인터프리터 2개**에서 `model_dump_json()` 바이트가 모두 같다(sha256 `945b3c9ca8a1b9b8…`, 52,211 B). 새 프로세스 결과도 같은 프로세스 결과와 같다. UI에서 2회 실행해도 같다. 보고서에 타임스탬프·UUID 없음.
- [x] **core가 Streamlit을 import하지 않음**: `core/**/*.py` 소스에서 `import/from streamlit|plotly`, `import_module`, `__import__` 0건. core가 쓰는 서드파티는 {numpy, scipy, pandas, openpyxl, pydantic}뿐(D1). 새 인터프리터에서 `import core, core.adapters, core.analyzers, core.judge, core.pipeline`(+models, preprocess) 뒤 `sys.modules`에 streamlit/plotly 없음. 전체 `run_analysis`를 실행한 뒤에도 없음.

## 6. 성능 (기획서 1.3: 2만 점 × 4채널, 분석 → 판정 카드 ≤ 3 s)

| 측정 | 결과 |
|---|---|
| `analyze_all` 측정 세트 20k × 4ch (5회 중앙값) | **9.5 ms** (최대 10.6 ms) |
| `run_analysis` 전체 데모(20k × 4ch + 시뮬 40k × 3ch + DMM + 비트열) | **32.8 ms** (최대 38.9 ms) |
| 파일 바이트 → 어댑터 3개 파일 | 409 ms |
| 어댑터 + 분석 합계 | 442 ms |
| UI 클릭 → 보고서 (AppTest 세션 기록) | 38 ms. 클릭 → 대시보드 렌더 완료까지 0.43 s (AppTest wall) |
| 스트레스 80k × 4ch | 77.7 ms |

## 7. 범위 밖 구현 (4.1 제외 항목) · `TODO.md`

- `api/`, `web/`, `core/plugins/` 디렉터리 없음.
- 코드(`core/`, `app_streamlit/`, `synth/`)에서 로그인·인증·DB(sqlalchemy/sqlite/fastapi), 장비별 CSV 자동 인식(장비 이름·auto-detect), ngspice raw 바이너리, Shmoo/Fmax/Vmin, 다운샘플링(LTTB·min-max·decimate·resample), 칩 간 통계, TCAM/SRAM/DRAM 플러그인, PDF(reportlab/fpdf), Parquet/pyarrow를 검색한 결과 **구현 흔적 없음**. 검색어에 걸린 것은 셋업 슬랙 정의 문구의 "(Shmoo)가 아님"과 `levels.py`의 지역 변수 `vmin`(히스토그램 범위)뿐이다.
- 파형 차트는 2,000점이 넘으면 Plotly `Scattergl`(WebGL)을 쓰지만 점을 줄이지는 않는다. 기획서 10.1이 MVP 단계에 "WebGL 모드"를 두고 있으므로 4.1 위반이 아니다.
- 코드의 TODO 주석은 1건: `core/adapters/__init__.py` `# TODO(Phase 1): instrument-specific scope CSV auto-detection; ngspice raw binary parser.` (D1 허용 형식)
- `TODO.md`에 8개 제외 항목이 모두 있다: 로그인·DB·공유(Phase 2), 장비별 CSV 자동 인식 · ngspice raw · Shmoo/Fmax/Vmin · 다운샘플링 · PDF(Phase 1), 칩 간 통계(Phase 2 "칩 간 비교(통계)"), TCAM 플러그인(Phase 3~4).

## 8. 버그 목록

| ID | 심각도 | 영역(소유) | 재현 | 기대 vs 실제 |
|---|---|---|---|---|
| QA-01 | 낮음 (UX, 4.2/4.4 위반 아님) | `app_streamlit/` (dashboard-agent): `state.apply_demo_defaults` + `input_flow._paths_section` | 앱을 새로 연다 → 파일을 고르기 **전에** "데모 기본값 채우기"를 누른다 (`qa_extra_probes.py` A) | 기대: 버튼 도움말은 순서 제한을 말하지 않으므로 오류 없이 채워지거나 중립 안내만 나와야 한다. 실제: 빨간 `st.error` "경로 'Buffer': 알 수 없는 채널 CH2, CH3"가 뜬다(채널 목록이 비어 있음). 파일을 고르면 저절로 사라지고 결과는 정상이다. 4.2 순서(업로드 먼저)에서는 나타나지 않는다 |

차단·높음·중간 등급 버그는 없다.

## 9. 관찰 (버그 아님, 참고)

1. **rise 편차가 "+50 %"가 아니라 "+49.2 %"로 보임**: §3.2 참고. D11 허용 오차 안이고, 원인은 데이터 노이즈다. 데모 발표 때 "≈+50 %"라고 설명하면 된다.
2. **Evidence**: 16개 지표 모두 `docs/metrics.md` §3 표와 정확히 같다. 다만 `idd_avg`는 정의상 마커·기준 전압이 없는(기록 전체 평균) 유일한 지표다. 기획서 1.3의 "모든 지표에 … 마커"를 문자 그대로 읽으면 예외가 된다.
3. **AppTest 한계**: 실제 브라우저 파일 업로드(`st.file_uploader`)와 data_editor 셀 편집은 AppTest로 조작하지 않았다. 스펙·경로 표는 "데모 기본값 채우기"로 채운 값으로 검증했다.
4. **서버 바인딩**: 기본 `streamlit run`이 모든 인터페이스에서 수신한다(로그에 Network/External URL이 찍힘). 기획서 4.1은 "로컬 실행"이고, 미공개 칩 데이터를 다룰 때는 `--server.address localhost`를 고려할 만하다(판정 기준 밖).
5. 입력 특이 케이스(기획서 2.2/B9) 프로브: cp949 + 한글 헤더 → `ENCODING_FALLBACK`. `시간(ns)` → ×1e-9, `출력(mV)` → ×1e-3, 프로브 ×10 반영. 시간 열이 없으면 시작 + 간격으로 축을 만든다. mV를 V로 잘못 읽으면 `SUSPICIOUS_RANGE`. 모두 정상.
