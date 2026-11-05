# ChipLens (Phase 0 MVP)

PCB에 실장한 칩의 오실로스코프·멀티미터 측정 파일을 올리고 채널 역할만 지정하면, 타이밍·DC·기능 지표를 계산해 스펙과 시뮬레이션 대비로 판정하는 로컬 Streamlit 앱.

- 기획서: [docs/chiplens_plan.md](docs/chiplens_plan.md) · 결정 사항: [docs/decisions.md](docs/decisions.md) · 모듈 계약: [docs/contract.md](docs/contract.md) · 지표 정의: [docs/metrics.md](docs/metrics.md)
- MVP에서 뺀 항목: [TODO.md](TODO.md)

## 설치와 실행 (Windows)

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt
.venv/Scripts/python -m synth.generate          # synth/data/ 합성 데이터 생성 (이미 있으면 같은 파일로 다시 씀)
.venv/Scripts/python -m pytest -q               # golden test 포함 전체 테스트
.venv/Scripts/python -m streamlit run app_streamlit/app.py --server.address localhost
```

`--server.address localhost`는 이 PC에서만 접속되게 한다(빼면 같은 네트워크의 다른 PC에서도 열림).

## 온라인 배포 (Streamlit Community Cloud)

GitHub 저장소를 [share.streamlit.io](https://share.streamlit.io)에 연결하면 `https://<이름>.streamlit.app` 주소로 누구나 브라우저에서 쓸 수 있다.

1. share.streamlit.io에 GitHub 계정으로 로그인 → **Create app** → "Deploy a public app from GitHub".
2. Repository = 이 저장소, Branch = `main`, Main file path = `app_streamlit/app.py`.
3. Advanced settings → Python version **3.12**.
4. Deploy. `requirements.txt`가 자동 설치된다. 이후 `main`에 push하면 앱이 자동으로 갱신된다.

> 공개 앱은 주소를 아는 누구나 접속할 수 있다. 업로드한 파일은 세션 메모리에만 있고 저장되지 않지만, 미공개 칩의 실측 데이터는 로컬 실행으로 분석하는 것을 권장한다.

## 데모 시나리오 (기획서 4.2)

1. **입력·분석** 탭 → "샘플 데이터 사용"에서 `synth_scope.csv`(파형), `synth_sim.csv`(시뮬 파형)를 고른다. 직접 업로드해도 같은 경로로 처리된다.
2. "데모 기본값 채우기" → 역할 CH1 CLK · CH2 IN · CH3 OUT · CH4 IDD, 경로 `Buffer: CH2 → CH3`, 논리 VDD 1.8 V, 대역폭 500 MHz.
3. 같은 버튼이 스펙 4개도 채운다: tpd ≤ 8 ns, rise ≤ 4 ns, VOH ≥ 1.6 V, IDDQ ≤ 2.5 µA.
4. 시뮬 열 매핑은 `v(clk)/v(in)/v(out)` → CH1/CH2/CH3로 자동 제안된다.
5. **분석 실행** → tpd·rise PASS(마진 ≈ 25 %), VOH MARGINAL(9.4 %), 시뮬 대비 tpLH +33 % · rise +49 % 경고.
6. `synth_dmm.xlsx`(DC 스윕)를 추가하고 재실행 → I–V 곡선 + IDDQ PASS(40 %).
7. 기대 비트열 `0000001000001100001010001111001000101100`(또는 "샘플 기대 비트열 넣기") → 일치율 100 %. 측정 파일을 `synth_scope_err.csv`로 바꾸면 "37번째 사이클에서 첫 불일치".
8. 대역폭을 100 MHz로 바꿔 재실행 → rise/fall에 장비 대역폭 한계 경고.

> 판정은 엣지별 **최악값**으로 하므로, 10 mV 노이즈가 있는 합성 데이터에서 tpd·rise 마진은 25 %보다 조금 작게(≈ 24 %) 나온다. 시뮬 편차는 평균값끼리 비교한다.

## 구조

```
core/            UI 무관 분석 코어 (streamlit·plotly import 금지)
  models/        표준 데이터 모델 · AnalysisResult/AnalysisReport 계약 · 지표 카탈로그
  adapters/      범용 표 리더(CSV·xlsx·텍스트, cp949 대비) · 단위 추출 · 정규화
  preprocess/    레벨 추정 · 히스테리시스 엣지 검출 · 스무딩
  analyzers/     timing · dc_power · functional
  judge/         스펙 마진 · 시뮬 편차 · 대역폭 경고 · 요약 카드 · 규칙 기반 문구
  pipeline.py    run_analysis(AnalysisRequest) -> AnalysisReport
app_streamlit/   Phase 0 UI (입력 흐름 + 대시보드)
synth/           합성 데이터 생성기 + data/ (정답표 golden.json)
tests/           golden · e2e · 단위 · AppTest
.claude/agents/  개발용 서브에이전트 정의 (기획서 8.2)
reports/qa/      qa-agent 독립 검증 리포트
```

## 개발용 서브에이전트

`.claude/agents/`에 기획서 8.2의 에이전트가 정의돼 있다: schema-architect → (parser · analysis · dashboard 병렬) → judge → dashboard 연결 → qa. `api-agent`(Phase 2)와 `plugin-agent`(Phase 3~4)는 정의만 있고 MVP에서는 쓰지 않는다. 소유 영역은 [CLAUDE.md](CLAUDE.md) 참고.
