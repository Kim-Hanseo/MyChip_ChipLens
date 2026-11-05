# ChipLens 모듈 계약 (Phase 0 MVP, schema v0.1)

> 소유: schema-architect. 기준: `docs/decisions.md`(D1–D11) > 이 문서 > `docs/chiplens_plan.md`.
> 타입 정의의 원본은 `core/models/` 코드다. 이 문서는 **누가 어떤 함수를 어떤 시그니처로 만들고, 어떤 필드를 채우는지**를 고정한다.
> parser / analysis / judge / dashboard 에이전트는 서로 대화 없이 이 문서만 보고 병렬 구현한다. 모호하면 "계약 변경 요청"으로 보고하고, 임의 해석 시 이 문서의 가장 단순한 읽기를 따른다.

## 0. 공통 규칙

| 항목 | 규칙 |
|---|---|
| import | 모델·열거형·헬퍼는 전부 `from core.models import ...`. 다른 에이전트는 `core/models`를 수정하지 않는다. |
| 단위 | 모든 모델 값은 SI(s, V, A, W, Hz). 비율·마진·편차는 퍼센트 숫자(25.0 = 25 %). 표시 변환은 `METRICS[id].display_scale`/`display_unit` 또는 `format_*` 헬퍼로만. |
| 시각 | `Evidence`, `FunctionalDetail`, `Edge`의 모든 시각은 **그 파형 자신의 시간축**(파일의 시간 열 그대로, 예: −2 µs 시작) 기준 초. |
| NaN | 모델은 NaN/inf를 거부한다(`allow_inf_nan=False`). 값이 없으면 `None`. |
| 불변 갱신 | 판정·편차·경고 추가는 `result.model_copy(update={...})`로 새 객체를 만든다. |
| 정렬 (D10) | 결과 목록 = `sorted(..., key=result_sort_key)`(카탈로그 순서 → path → channel_id → source), 경고 = `notice_sort_key`, `Evidence.edges` = `t_s` 오름차순, `AnalysisResult.warnings` = 중복 없는 정렬 목록(`make_result`가 처리). |
| 결정성 | 타임스탬프·난수 ID 금지. 같은 요청 → `AnalysisReport.model_dump_json()` 바이트 동일. |
| Waveform 비교 | `Waveform`/`DCSweep`/`MeasurementSet`는 numpy 배열을 가지므로 `==` 비교 금지. |
| 역할 문자열 | `Role`: `"CLK" "IN" "OUT" "EN" "DATA" "VDD" "IDD" "UNUSED"`. `UNUSED` 채널은 분석기가 무시. |
| "그 CLK" | `ChannelMap.channels` 순서상 **첫 번째 `CLK` 채널**(파형이 있는 것). 나머지 CLK는 MVP에서 무시. |
| 기능 대상 채널 | `ExpectedPattern.channel_id`, 없으면 순서상 첫 번째 `OUT` 채널. |
| 테스트 파일 이름 | `tests/` 하위에 `__init__.py`가 없으므로 **테스트 파일 이름은 저장소 전체에서 유일**하게 (예: `tests/adapters/test_adapters_csv.py`). |
| 금지 | `core/`에서 streamlit·plotly import 금지 (`tests/test_core_purity.py`가 검사). |

## 1. 모델 지도 (`core/models/`)

| 파일 | 내용 |
|---|---|
| `enums.py` | `Role`, `Source`(`"measured"`/`"sim"`), `Polarity`(`"non_inverting"`/`"inverting"`), `Category`(`"timing"`/`"dc"`/`"functional"`), `Verdict`(`"PASS"`/`"MARGINAL"`/`"FAIL"`, 스펙 없음 = `None`), `Aggregate`(`"max"`/`"min"`/`"mean"`/`"single"`), `Target`, `Quantity`(`"V"`/`"A"`), `EdgeKind`(`"rise"`/`"fall"`), `FileKind`(`"csv"`/`"xlsx"`/`"text"`), `WarningCode`, 표시용 `ROLE_LABELS`, `VERDICT_SYMBOLS`(✓ ! ✕ –), `VERDICT_LABELS` |
| `inputs.py` | `Waveform`, `DCSweep`, `ChannelInfo`, `ChannelMap`, `Path`(별칭 `SignalPath`), `Spec`, `SessionInfo`, `AnalysisSettings`, `ExpectedPattern`, `MeasurementSet`, `AnalysisRequest`, 전처리 값 객체 `Levels`, `Edge` |
| `results.py` | `Stats`, `EdgeSample`, `Evidence`, `AnalysisResult`, `Notice`, `FunctionalDetail`, `AnalyzerOutput`, 카드(`VerdictCard`, `WorstMarginCard`, `DeviationItem`, `SimDeviationCard`, `FunctionalCard`, `SummaryCards`), `AnalysisReport`, 헬퍼 `make_result`, `result_sort_key`, `notice_sort_key` |
| `tables.py` | 업로드 단계 타입: `ReadOptions`, `ColumnInfo`, `TablePreview`, `RawTable`(pandas DataFrame 보유), `TimeAxisSpec`, `ChannelConversion`, `WaveformBuildResult`, `DCSweepBuildResult` |
| `metrics.py` | `MetricDef`, `METRICS`(D4의 16개, 정렬 순서 = 정식 순서), `METRIC_IDS`, `METRIC_INDEX` |
| `units.py` | `parse_unit`, `format_number`(유효숫자 3), `format_si`, `format_metric_value`, `format_pct`, `format_spec`, `MICRO`(= `µ` U+00B5) |

핵심 필드 (전체는 코드 참조):

- `Waveform(channel_id, quantity: "V"|"A", time_s: ndarray, values: ndarray, source_column, source_unit, probe_factor)` — 길이 ≥ 2, 같은 길이, `time_s` 엄격 증가, 유한값. 리스트를 넣으면 float64 1-D 배열로 변환. 역할은 갖지 않는다(역할은 `ChannelMap`만).
- `DCSweep(name="DC", x, y, x_quantity="V", y_quantity="A", x_label, y_label)` — x 엄격 증가(어댑터가 정렬).
- `ChannelMap(channels: list[ChannelInfo(channel_id, role, label)])` + `get`, `role_of`, `ids_with_role`, `display_name`(label 또는 channel_id).
- `Path(name, input_channel, output_channel, polarity="non_inverting")`.
- `Spec(metric_id, path=None, channel_id=None, min=None, max=None)` — SI 값, min/max 중 하나 이상.
- `SessionInfo(source, chip_id, temperature_c, vdd_v, frequency_hz, instrument, sample_interval_s, files, notes)` — **표시용 메타데이터**. 분석은 `source`만 읽는다. 대역폭은 여기 없고 `AnalysisSettings.bandwidth_hz` 하나뿐이다.
- `AnalysisSettings(logic_vdd_v=1.8, bandwidth_hz=None, marginal_threshold_pct=10, sim_tolerance_pct=20, delay_offset_s=0, edge_hysteresis_pct=10, min_pulse_width_s=0, smoothing_points=0)`.
- `ExpectedPattern(bits, channel_id=None)` — 검증 시 공백·`_`·`,`·탭·줄바꿈 제거, '0'/'1' 외 문자는 오류. `bits`에는 정리된 문자열이 저장된다.
- `MeasurementSet(session, channel_map, paths, waveforms, dc_sweeps)` — 파형 channel_id ⊂ channel_map, 경로 채널 ⊂ channel_map. **파형이 없는 채널·경로는 분석기가 조용히 건너뛴다**(시뮬 세트에 IDD가 없는 경우 등).
- `AnalysisRequest(measured, sim=None, specs=[], expected=None, settings)` — `measured.session.source == "measured"`, `sim.session.source == "sim"` 검증.

## 2. `core.adapters` — parser-agent

`core/adapters/__init__.py`에서 아래 6개를 공개한다. 실패(지원 안 되는 형식, 없는 열, 유효 행 < 2 등)는 **한국어 메시지의 `ValueError`**. 경미한 문제는 `Notice`로 반환(어댑터 Notice는 UI가 표시만 하고 `AnalysisReport`에는 들어가지 않는다).

```python
def preview_file(data: bytes, file_name: str, options: ReadOptions | None = None) -> TablePreview
def read_table(data: bytes, file_name: str, options: ReadOptions) -> RawTable
def split_header_unit(header: str) -> tuple[str, str | None]
def to_waveforms(table: RawTable, time_axis: TimeAxisSpec, channels: list[ChannelConversion]) -> WaveformBuildResult
def to_dc_sweep(table: RawTable, x_column: str, y_column: str, *, x_scale: float = 1.0,
                y_scale: float = 1.0, name: str = "DC") -> DCSweepBuildResult
def suggest_sim_mapping(sim_columns: list[ColumnInfo], channel_map: ChannelMap) -> dict[str, str | None]
```

| 함수 | 동작 |
|---|---|
| `preview_file` | (a) 업로드 단계. `options=None`이면 전부 자동 추정, 주어지면 그 옵션 그대로 다시 미리보기(사용자 수정 반영). 종류는 확장자(소문자): `.csv`→`csv`, `.xlsx`/`.xlsm`→`xlsx`, 그 외→`text`(`.xls`는 `ValueError`). 인코딩 `"utf-8-sig"` 실패 시 `"cp949"` + `ENCODING_FALLBACK`. 구분자 후보 `","`, `"\t"`, `";"`, `" "`(공백 연속 1개 이상). 헤더 행 = 숫자 행이 길게 이어지기 직전 행(0-based, `raw_rows` 인덱스와 같은 기준). `raw_rows` = 헤더 처리 전 앞 30행(셀 문자열, 빈 셀 `""`, xlsx 병합 셀은 왼쪽 위 셀에만 값). `head_rows` = 데이터 앞 10행(문자열, `columns`와 정렬). `sheets` = 통합 문서 순서 시트 이름(text는 `[]`). `time_candidates` = `si_unit == "s"` 열 → 이름이 time/t/시간인 열 → 단조 증가 숫자 열 순. |
| `read_table` | (b) 옵션 → `RawTable`. `data`의 열 = `[c.name for c in columns]`, 숫자 열 float64(변환 불가 → NaN), 그 외 str, **단위 변환 없음(원시값)**. 열 이름: 헤더 텍스트, 빈 헤더는 `col{i}`(0-based), 중복은 `_2`, `_3` 접미사. ngspice `wrdata`처럼 같은 시간 열 헤더가 반복되면, 첫 시간 열과 값이 같은(상대 1e-9 이내) 반복 열은 제거하고, 다르면 접미사로 남기고 `TIME_COLUMN_MISMATCH`. |
| `split_header_unit` | 헤더 → (base_name, unit_text). `"CH1(V)"`→`("CH1","V")`, `"Time(s)"`→`("Time","s")`, `"전류(µA)"`→`("전류","µA")`, `"I [mA]"`→`("I","mA")`. 괄호 안이 `parse_unit`으로 해석되지 않으면 단위 없음: `"V(out)"`/`"v(clk)"`→`("v(clk)", None)`. 이때 SPICE 표기 `v(...)`/`i(...)`는 `ColumnInfo.si_unit`을 `"V"`/`"A"`(scale 1)로 둔다. 단위 접두사 해석은 `core.models.parse_unit`(µ U+00B5, μ U+03BC, u 모두 마이크로). |
| `to_waveforms` | (c) `TimeAxisSpec(column, scale, start_s, interval_s)` + 채널별 `ChannelConversion(column, channel_id, quantity, scale, probe_factor)` → `Waveform` 목록(입력 순서). SI 값 = 원시 × `scale` × `probe_factor`. 시간 = 열 × `scale`, 열이 없으면 `start_s + i·interval_s`. 시간 또는 선택한 채널 중 하나라도 NaN인 행 제거 → `NAN_DROPPED`. 시간이 직전까지의 최댓값 이하인 행 제거 → `NON_MONOTONIC_AXIS`. 변환 후 `|V| > 100` 또는 `|A| > 10`이면 `SUSPICIOUS_RANGE`(channel_id 채움, 파형은 그대로 반환). `Waveform.source_column`=열 이름, `source_unit`=그 열의 `unit_text`, `probe_factor` 기록. |
| `to_dc_sweep` | (d) x/y 열 → `DCSweep`(x × `x_scale`, y × `y_scale`). NaN 행 제거(`NAN_DROPPED`), x 오름차순 정렬, 중복 x는 첫 행만(`NON_MONOTONIC_AXIS`). 유효 행 0이면 `sweep=None`. `x_label`/`y_label` = 원래 헤더. |
| `suggest_sim_mapping` | (e) 시뮬 열 → 측정 channel_id 제안. 키 = 숫자이면서 `si_unit != "s"`인 열 이름(입력 순서), 값 = 제안 channel_id 또는 `None`. 열 `base_name`을 영숫자 토큰으로 나눠 소문자 비교: ① 토큰 == channel_id 또는 label(소문자) ② 토큰 == 역할 이름(소문자, 예 `v(clk)`→`clk`→CLK)이고 그 역할 채널이 정확히 하나. 측정 채널 하나는 한 열에만 배정(앞 열 우선). `UNUSED` 채널은 후보 아님. |

**시뮬 재키잉(D3)** = 별도 함수 없음. UI가 시뮬 표에 `to_waveforms`를 부를 때 `ChannelConversion.channel_id`에 **측정 channel_id**를 넣는다. 그 결과로 `MeasurementSet(session=SessionInfo(source="sim", ...), channel_map=측정과 동일, paths=측정과 동일, waveforms=시뮬 파형)`을 만든다.

## 3. `core.preprocess` / `core.analyzers` — analysis-agent

```python
# core.preprocess
def estimate_levels(wf: Waveform, settings: AnalysisSettings) -> Levels
def detect_edges(wf: Waveform, levels: Levels, settings: AnalysisSettings) -> list[Edge]   # t50_s 오름차순

# core.analyzers
def analyze_timing(mset: MeasurementSet, settings: AnalysisSettings) -> AnalyzerOutput
def analyze_dc_power(mset: MeasurementSet, settings: AnalysisSettings) -> AnalyzerOutput
def analyze_functional(mset: MeasurementSet, settings: AnalysisSettings,
                       expected: ExpectedPattern | None) -> AnalyzerOutput   # .functional 채움
def analyze_all(mset: MeasurementSet, settings: AnalysisSettings,
                expected: ExpectedPattern | None = None) -> AnalyzerOutput   # 위 3개 합침, 정렬
```

- 결과는 반드시 `make_result(metric_id, source=mset.session.source, path=..., channel_id=..., value=..., stats=..., evidence=..., warnings=...)`로 만든다. `spec / verdict / margin_pct / sim_value / deviation_pct`는 **기본값(None) 그대로**.
- 결과를 내는 대상 (파형이 있는 것만, 지표 정의·Evidence 키는 `docs/metrics.md`):

| 대상 | 지표 | `path` | `channel_id` |
|---|---|---|---|
| 각 `OUT` 채널 | `rise_time`, `fall_time`, `voh`, `vol`, `setup_slack`, `hold_slack` | None | 그 채널 |
| 각 `DATA` 채널 | `setup_slack`, `hold_slack` | None | 그 채널 |
| "그 CLK" 채널 | `period`, `frequency`, `duty_cycle` | None | CLK 채널 |
| 각 `Path` (입·출력 파형 모두 있을 때) | `tplh`, `tphl`, `tpd` | `path.name` | `path.output_channel` |
| 각 `IDD` 채널 | `idd_avg`, `avg_power` | None | IDD 채널 |
| 각 `DCSweep` | `iddq` | None | `sweep.name` |
| 기능 대상 OUT (기대 비트열이 있을 때만) | `match_rate` | None | 대상 OUT 채널 |

- setup/hold는 CLK 파형이 없으면 내지 않는다. `tpd`는 tplh·tphl 중 하나라도 값이 있으면 낸다.
- 값을 못 구하면(엣지 부족 등) 결과는 내되 `value=None`, `stats=None`, `warnings=[INSUFFICIENT_EDGES]` + 같은 위치의 `Notice`. `iddq`에서 논리 VDD가 스윕 x 범위 밖이면 `value=None` + `OUT_OF_SWEEP_RANGE`.
- `stats`는 `METRICS[id].has_stats`이고 값이 있을 때만(`std`는 모집단 표준편차 ddof=0, `n` = 엣지/사이클 수).
- `value`는 `METRICS[id].aggregate`대로: `max`/`min` = 엣지별 값의 최악, `mean` = 평균, `single` = 단일 값. `Evidence.worst_time_s` = 최악 엣지의 `t_s`(`max`/`min` 지표만).
- `analyze_functional`: CLK·대상 OUT 파형이 있으면 **기대 비트열이 없어도** `FunctionalDetail`(측정 비트열)을 채운다. 기대 비트열이 있는데 CLK 또는 대상 OUT 파형이 없으면 결과 없이 `MISSING_ROLE` Notice. 기대 비트열 길이 ≠ 측정 비트 수이면 `match_rate` 결과 warnings와 Notice에 `EXPECTED_LENGTH_MISMATCH`.
- `FunctionalDetail` 채우기: `sample_times_s` = CLK 상승 50 % 교차 시각(사이클 1..n), `sample_values_v` = 그 시각 OUT 선형 보간 값, `threshold_v = logic_vdd_v / 2`, `measured_bits`(값 ≥ 임계 → '1'), `expected_bits` = 정리된 기대 비트열 전체(없으면 None), `compared_cycles = min(두 길이)`, `matched_cycles`, `mismatch_cycles`(1-based 오름차순), `first_mismatch`, `match_rate_pct = matched/compared × 100`(compared = 0이면 None, 이때 match_rate 결과 value=None). 대시보드는 이 필드만으로 0/1 레인과 불일치 강조를 그린다.
- `UNPAIRED_EDGES`: D4 짝짓기 창 밖이라 버린 입력 엣지가 1개 이상이면 해당 `tplh`/`tphl` 결과 warnings + Notice(값은 남은 엣지로 계산).
- 분석기는 `BANDWIDTH_LIMIT`, `SIM_DEVIATION`을 **넣지 않는다**(judge 몫).
- Notice를 만들 때 `source=mset.session.source`, `metric_id/path/channel_id`를 결과와 같게, `message`는 한국어 한 줄.
- 성능: 2만 점 × 4채널 `analyze_all` < 1 s 목표(한도 3 s). 샘플 단위 Python 루프 금지.

## 4. `core.judge` / `core.pipeline` — judge-agent

```python
# core.judge
def match_spec(result: AnalysisResult, specs: list[Spec]) -> Spec | None
def judge_value(value: float, spec: Spec, marginal_threshold_pct: float) -> tuple[Verdict, float | None]
def apply_specs(results: list[AnalysisResult], specs: list[Spec],
                settings: AnalysisSettings) -> list[AnalysisResult]
def apply_sim_comparison(results: list[AnalysisResult], sim_results: list[AnalysisResult],
                         settings: AnalysisSettings) -> tuple[list[AnalysisResult], list[Notice]]
def apply_bandwidth_check(results: list[AnalysisResult],
                          settings: AnalysisSettings) -> tuple[list[AnalysisResult], list[Notice]]
def build_cards(results: list[AnalysisResult], functional: FunctionalDetail | None,
                settings: AnalysisSettings) -> SummaryCards
def narrate(results: list[AnalysisResult], functional: FunctionalDetail | None, cards: SummaryCards,
            paths: list[Path], channel_map: ChannelMap, settings: AnalysisSettings) -> list[str]

# core.pipeline
def run_analysis(request: AnalysisRequest) -> AnalysisReport
```

### 4.1 스펙 판정 (D5)
- `match_spec`: `spec.metric_id == r.metric_id` 이고 (`spec.path` None 또는 == `r.path`) 이고 (`spec.channel_id` None 또는 == `r.channel_id`)인 후보 중 구체성 점수(path 지정 2 + channel 지정 1) 최대, 동점이면 목록 앞쪽.
- `judge_value`: 상한 `(max−v)/|max|×100`, 하한 `(v−min)/|min|×100`, 범위 = 둘 중 작은 값. 사용한 한계값 중 0이 있으면 margin=None이고 한계 만족 여부로 PASS/FAIL만. 등급: margin ≥ T → PASS, 0 ≤ margin < T → MARGINAL, < 0 → FAIL (T = `marginal_threshold_pct`).
- `apply_specs`: 매칭된 스펙을 `spec`에 넣고 판정. `value is None`이면 `spec`만 넣고 verdict/margin은 None. **`match_rate`는 스펙을 보지 않는다**: 결과가 있고 value가 있으면 `value == 100.0` → PASS, 아니면 FAIL, margin=None, spec=None.

### 4.2 시뮬 편차 (D6)
- 측정 결과 중 `METRICS[id].sim_compare`인 것만, `result.key == (metric_id, path, channel_id)`가 같은 시뮬 결과와 짝짓기.
- `sim_value = sim.representative()`(= stats.mean 또는 value). 측정값 m = `result.representative()` − (`delay_offset_s` if metric_id in {`tplh`, `tphl`} else 0).
- `deviation_pct = (m − sim_value)/|sim_value| × 100`. 시뮬값이 0 또는 None, m이 None이면 None(이때도 `sim_value`는 채움, None이 아니면).
- `|deviation_pct| > sim_tolerance_pct` → 결과 warnings에 `SIM_DEVIATION` + Notice(message 예: `"Buffer tpLH 시뮬 대비 +33.3% (허용 ±20.0% 초과)"`).

### 4.3 대역폭 경고 (D8) — **judge가 넣는다**
- `settings.bandwidth_hz`가 있으면 한계 = `2 × 0.35 / bandwidth_hz`. **측정** `rise_time`/`fall_time` 중 `stats.mean < 한계`인 결과에 `BANDWIDTH_LIMIT` + Notice. 시뮬 결과에는 적용하지 않는다.

### 4.4 요약 카드 (D9)
- `verdicts`: 측정 결과의 verdict 개수(PASS/MARGINAL/FAIL), `no_spec_count` = verdict None 개수.
- `worst_margin`: margin_pct가 있는 결과 중 최소, 동점은 `result_sort_key` 순. 없으면 None.
- `sim_deviation`: `sim_value`가 채워진 결과가 하나도 없으면 None. 아니면 `deviation_pct`가 있는 결과를 (|편차| 내림차순, `result_sort_key`)로 정렬하고, **이미 뽑힌 항목과 `METRICS[id].family`가 같은 항목은 건너뛰며** 최대 2개 → `top`. `DeviationItem.measured_value` = 오프셋 보정 후 m. `warning_count` = `SIM_DEVIATION`을 가진 결과 수, `tolerance_pct` = 설정값. (family: rise/fall = `edge_rate`, tplh/tphl/tpd = `prop_delay`, setup/hold = `slack`, voh/vol = `output_level` → 데모 결과 `rise_time +50.0 %`, `tplh +33.3 %`.)
- `functional`: `functional`이 있고 `expected_bits`가 None이 아니며 `match_rate` 결과에 verdict가 있을 때만. 그 외 None.

### 4.5 요약 문구 (D9, 최대 8줄, 넘치면 뒤에서 자름)
- 대상 = `path`가 있으면 경로 이름, 없으면 `channel_map.display_name(channel_id)`. 지표 = `METRICS[id].short_label`. 값 = `format_metric_value`, 스펙 = `format_spec`, 마진 `f"{m:.1f}"`, 편차 `f"{d:+.1f}"`.
- 0 헤드라인: `"전체 판정: PASS {p} · MARGINAL {m} · FAIL {f}"` + worst_margin이 있으면 `" — 최악 마진 {지표} {마진}% ({대상})"`.
- 1 FAIL(결과 순서대로): `"{대상} {지표} {값} — 스펙 {스펙} 위반 (FAIL)"`. match_rate FAIL은 이 줄 대신 2번 줄.
- 1b MARGINAL: `"{대상} {지표} {값} — 스펙 {스펙} 대비 마진 {마진}% (MARGINAL)"`.
- 2 기능 불일치: `"{n}번째 사이클에서 첫 불일치 (기대 {e}, 측정 {m})"` — e/m = 그 사이클의 기대/측정 비트.
- 3 / 4: D9 그대로(4가 나오면 3은 안 냄). 3 = `"전 경로 공통 지연 증가 → 측정 경로(패드·PCB·프로브) 지연, VDD 강하, 공정 코너 가능성"`, 4 = `"{경로}만 시뮬 대비 {편차}% → 해당 경로 부하·배선 기생 확인 필요"`(편차는 부호 포함 `+31.0` 형식).
- 5 대역폭: `BANDWIDTH_LIMIT` 결과마다 `"{대상} {지표} {stats.mean 값}: 측정값이 오실로스코프 대역폭 한계에 가까움 → 실제 값은 더 짧을 수 있음"`.

### 4.6 `run_analysis` 순서
1. `m = analyze_all(request.measured, settings, request.expected)`
2. `s = analyze_all(request.sim, settings, None)` (sim 있을 때)
3. `apply_specs` → `apply_sim_comparison(m.results, s.results)` → `apply_bandwidth_check`
4. `build_cards(results, m.functional, settings)` → `narrate(...)`
5. `clk_t0_s` / `sim_clk_t0_s` = 각 세트 "그 CLK" 파형에 `estimate_levels` → `detect_edges` 후 첫 `rise`의 `t50_s`(없으면 None). 시뮬 비교 탭 겹쳐 보기 정렬용(D6, 표시 전용).
6. `AnalysisReport(session=measured.session, sim_session=sim.session|None, settings, channel_map=measured.channel_map, paths=measured.paths, specs=request.specs, results=정렬, sim_results=s.results 정렬(판정 필드 비움), functional=m.functional, cards, summary_lines, warnings=sorted(m.notices + s.notices + judge notices, key=notice_sort_key), clk_t0_s, sim_clk_t0_s)`.

## 5. 경고 코드 — 누가 넣는가 (하나로 고정)

| 코드 | 넣는 쪽 | 붙는 곳 | 조건 |
|---|---|---|---|
| `BANDWIDTH_LIMIT` | **judge** (`apply_bandwidth_check`) | 측정 `rise_time`/`fall_time` 결과 + Notice | D8: stats.mean < 2×0.35/BW |
| `SIM_DEVIATION` | **judge** (`apply_sim_comparison`) | 측정 결과 + Notice | D6: \|편차\| > 허용 |
| `INSUFFICIENT_EDGES` | analyzer | 결과(value=None) + Notice | 지표 계산에 필요한 엣지/사이클 없음 |
| `UNPAIRED_EDGES` | analyzer | `tplh`/`tphl` 결과 + Notice | 짝짓기 창 밖 입력 엣지 버림 |
| `EXPECTED_LENGTH_MISMATCH` | analyzer | `match_rate` 결과 + Notice | D7: 길이 다름 |
| `OUT_OF_SWEEP_RANGE` | analyzer | `iddq` 결과(value=None) + Notice | 논리 VDD가 스윕 범위 밖 |
| `MISSING_ROLE` | analyzer | Notice만 | 기대 비트열이 있는데 CLK/OUT 파형 없음 |
| `ENCODING_FALLBACK` | adapter | Notice (TablePreview/RawTable) | cp949로 읽음 |
| `NAN_DROPPED` | adapter | Notice | NaN 행 제거 |
| `NON_MONOTONIC_AXIS` | adapter | Notice | 시간/스윕 x 역행·중복 행 제거 |
| `SUSPICIOUS_RANGE` | adapter | Notice | \|V\|>100 또는 \|A\|>10 (B9) |
| `TIME_COLUMN_MISMATCH` | adapter | Notice | wrdata 반복 시간 열 값 불일치 |

규칙: 결과에 코드를 넣는 쪽이 **같은 code·metric_id·path·channel_id의 Notice도 함께** 만든다. `AnalysisResult.warnings`는 코드만, 문구는 `Notice.message`(한국어).

## 6. UI(dashboard-agent)가 부르는 진입점

| 단계 | 호출 |
|---|---|
| 업로드·형식 확인 | `preview_file(bytes, name)` → 화면에 `options`/`sheets`/`raw_rows`/`columns`/`time_candidates`/`head_rows`/`notices`. 사용자가 옵션을 바꾸면 `preview_file(bytes, name, options)` 다시 호출. |
| 표 읽기 | `read_table(bytes, name, options)` → `RawTable` (원본 데이터 탭은 `RawTable.data` 사용 가능) |
| 단위·배율 | 열별 기본값: `ColumnInfo.si_unit`(→ `quantity`), `scale`, channel_id 기본 = `base_name`. 사용자 수정 후 `to_waveforms(table, TimeAxisSpec(...), [ChannelConversion(...)])`. |
| DC 스윕 | `to_dc_sweep(table, x_col, y_col, x_scale=..., y_scale=..., name=...)` |
| 시뮬 매핑 | `suggest_sim_mapping(sim_table.columns, channel_map)` → 드롭다운 기본값 → `to_waveforms`에 측정 channel_id로 재키잉 |
| 요청 구성 | `MeasurementSet` ×(1~2), `Spec`(입력은 표시 단위 → SI = 표시값 / `METRICS[id].display_scale`), `ExpectedPattern`, `AnalysisSettings` → `AnalysisRequest` |
| 분석 | `core.pipeline.run_analysis(request) -> AnalysisReport` |
| 표시 | `METRICS`(label·short_label·definition 툴팁), `format_metric_value`, `format_pct`, `format_spec`, `ROLE_LABELS`, `VERDICT_SYMBOLS`/`VERDICT_LABELS` |

- 보고서에는 파형 배열이 없다. 파형 탭은 UI가 들고 있는 `MeasurementSet.waveforms` + `AnalysisResult.evidence`(마커: `edges[].t_s`, 구간 `t_start_s`–`t_end_s`, 기준 전압 `ref_levels_v`, 최악 `worst_time_s`)로 그린다.
- 타이밍 탭 엣지별 분포 = `evidence.edges[].value`(시각 `t_s`). 기능 탭 = `report.functional`. 시뮬 겹쳐 보기 = 각 세트 시간에서 `clk_t0_s`/`sim_clk_t0_s`를 뺀다.
- 목업: `AnalysisReport.model_validate_json(Path("tests/fixtures/mock_report.json").read_text(encoding="utf-8"))`.

## 7. `tests/fixtures/mock_report.json`
부록 A 데모 전체 상태(스펙 tpd ≤ 8 ns, rise_time ≤ 4 ns, voh ≥ 1.6 V, iddq ≤ 2.5 µA + 시뮬 + DMM + 기대 비트열, 대역폭 500 MHz, 경로 `Buffer: CH2 → CH3`, CH1 CLK · CH2 IN · CH3 OUT · CH4 IDD, DMM 스윕 이름 `"DMM"`).
카드1 PASS 4 · MARGINAL 1 · FAIL 0 / 카드2 voh 9.4 % / 카드3 rise_time +50.0 %, tplh +33.3 %, 경고 4 / 카드4 100 % (40/40). 엣지 값은 결정적 가짜 지터를 넣은 **목업**이며 정답 데이터가 아니다(비트열도 목업 PRBS). 파형 배열 없음.

## 8. 계약 변경
`core/models`·이 문서는 schema-architect만 바꾼다. 필요하면 최종 보고에 "계약 변경 요청: 무엇을 / 왜"를 적는다.

## 9. 구현 중 확정된 해석 (Orchestrator 승인, 모델 변경 없음)

**§2 adapters (parser-agent)**
- `suggest_sim_mapping`: 이름이 time/t/시간인 열은 `si_unit`이 None이어도 키에서 제외. 전류 열(`si_unit == "A"`)에 `vdd`·`vcc` 토큰이 있으면 `IDD` 역할 채널로 제안.
- `to_dc_sweep`: `x_quantity`/`y_quantity`는 열 `si_unit`(V/A)에서, 모르면 기본값. `SUSPICIOUS_RANGE`는 DC 스윕에도 적용(channel_id = 스윕 이름). `NON_MONOTONIC_AXIS`는 중복 x 제거 때만 — 내림차순 정렬 자체는 경고 없음.
- `to_waveforms`: 빈 채널 목록·중복 channel_id → `ValueError`.
- 헤더·데이터 모두 빈 열은 버린다. 자동 추정의 `data_start_row`가 `header_row + 1`이면 `None`으로 둔다.

**§3 analyzers (analysis-agent)**
- 기록 끝에서 잘려 출력 엣지를 못 찾은 입력 엣지도 `UNPAIRED_EDGES`로 센다.
- 엣지 0개 OUT: 기록 전체를 안정 구간으로 보고 중앙값 ≥ 논리 VDD/2면 `voh`, 아니면 `vol`만 값을 낸다. 나머지 OUT 지표는 `value=None` + `INSUFFICIENT_EDGES`.
- 기대 비트열이 있는데 CLK 상승 0개 → `match_rate` `value=None` + `INSUFFICIENT_EDGES` + `EXPECTED_LENGTH_MISMATCH`.
- 기능 사이클은 OUT 기록 시간 범위 안의 CLK 상승만 센다.
- 경로의 입력 또는 출력 채널 역할이 `UNUSED`면 그 경로는 건너뛴다.

**§4 judge (judge-agent)**
- 문구 4의 "경로 ≥ 2" = tplh·tphl 편차가 있는 경로가 2개 이상. 조건을 만족하는 경로가 여럿이면 경로 순서대로 각 한 줄.
- `SIM_DEVIATION` Notice의 대상 이름 = path가 있으면 경로 이름, 없으면 channel_id.
- `BANDWIDTH_LIMIT` Notice 문구 예: `"CH3 rise 평균 2.98 ns < 대역폭 한계 7.00 ns (2 × 0.35 / 100 MHz) → 실제 값은 더 짧을 수 있음"`. 공개 보조 함수 `core.judge.bandwidth_limit_s(bw: float) -> float` (= 2 × 0.35 / bw).
