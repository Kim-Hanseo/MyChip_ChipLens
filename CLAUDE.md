# ChipLens — 칩 성능 테스트·분석 웹 (Phase 0 MVP)

기획서: `docs/chiplens_plan.md` · Orchestrator 결정: `docs/decisions.md` (충돌 시 decisions 우선) · 계약: `docs/contract.md`, `core/models/`

## 실행
- Python: `.venv/Scripts/python` (Windows). 전역 Python에 설치하지 않는다.
- 테스트: `.venv/Scripts/python -m pytest -q`
- 합성 데이터: `.venv/Scripts/python -m synth.generate`
- 앱: `.venv/Scripts/python -m streamlit run app_streamlit/app.py`

## 설계 원칙 (기획서 6.1)
1. `core/`는 UI 무관 순수 Python. **streamlit·plotly import 금지.**
2. 모든 입력은 표준 모델(`core/models`)로 바뀐 뒤에만 분석기로 간다.
3. 분석 출력은 `AnalysisReport`/`AnalysisResult` JSON 하나 — UI는 이것과 정규화된 입력만 읽는다.
4. 모든 판정은 결정적 규칙. 같은 입력 → 바이트 단위로 같은 JSON.
5. 기획서 4.1 제외 항목은 만들지 않고 `TODO.md`에만 기록.

## 소유 영역 (기획서 8.2)
| 경로 | 소유 에이전트 |
|---|---|
| `core/models/`, `docs/contract.md`, `docs/metrics.md`, `tests/fixtures/`, `tests/test_contract.py`, `tests/test_core_purity.py` | schema-architect |
| `core/adapters/`, `synth/`, `tests/adapters/` | parser-agent |
| `core/preprocess/`, `core/analyzers/`, `tests/golden/`, `tests/analysis/` | analysis-agent |
| `core/judge/`, `core/pipeline.py`, `tests/judge/`, `tests/e2e/` | judge-agent |
| `app_streamlit/`, `tests/app/` | dashboard-agent |
| `reports/qa/` | qa-agent (구현 코드 수정 금지) |

- 계약(`core/models`)은 schema-architect만 수정한다. 다른 에이전트는 계약 변경이 필요하면 직접 고치지 말고 최종 보고에 "계약 변경 요청"으로 적는다.
- 남의 영역 파일은 읽기만 한다.

## 코드 규칙
- 식별자·주석은 영어, 사용자에게 보이는 문구(UI, 요약 문구)는 한국어.
- 타입 힌트 사용, 공개 함수에는 짧은 docstring.
- 테스트는 결정적이어야 한다(시드 고정, 시간 의존 없음).
