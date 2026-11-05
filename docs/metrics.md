# ChipLens 지표 정의 (Phase 0 MVP)

> 사람용 정의서(B10 대응). 코드 원본은 `core/models/metrics.py`의 `METRICS`, 규칙 원본은 `docs/decisions.md` D4·D7·D8.
> 모든 값은 SI 단위(s, V, A, W, Hz), 비율은 퍼센트 숫자. 표시는 `display_unit`으로 유효숫자 3자리.

## 1. 공통 정의

| 용어 | 정의 |
|---|---|
| 레벨 (low / high) | 그 채널의 **실측** 레벨. 히스토그램 두 봉우리로 대략 구한 뒤 엣지 주변(전이·링잉 구간)을 뺀 안정 구간의 중앙값으로 정밀화. `Levels(low, high)`. |
| p % 기준 전압 | `low + (high − low) × p/100`. 10 %·50 %·90 %는 모두 **그 채널 자신의** low/high 기준. |
| 엣지 | 히스테리시스 임계(50 % ± `edge_hysteresis_pct`, 기본 40 %/60 %)를 넘어간 전이. 최소 펄스폭(`min_pulse_width_s`)보다 짧은 펄스는 무시. 교차 시각은 임계 교차점 **선형 보간**. `Edge(kind, t50_s, t10_s, t90_s)`. |
| 50 % 교차 시각 | 엣지 근처에서 50 % 기준 전압을 지나는 시각(선형 보간). 모든 타이밍 지표의 기준점. |
| 기능 샘플링 임계 | 유일한 예외: 논리 VDD/2 (`logic_vdd_v / 2`). 레벨 기준이 아님. |
| 경로 짝짓기 (D4) | 입력 엣지마다 기대 극성(`non_inverting`: 같은 방향, `inverting`: 반대 방향)의 **다음** 출력 엣지를 짝짓는다. 창 = "다음 입력 엣지 전" **그리고** "입력 엣지 간 최소 간격 × 0.5 이내". 창 밖이면 그 입력 엣지를 버린다(`UNPAIRED_EDGES`). |
| 통계 | 엣지(또는 사이클)별 값의 mean / min / max / std(모집단, ddof=0) / n. |
| 판정 값 (`value`) | 카탈로그 `aggregate`: `max`·`min` = 최악값(worst case), `mean` = 평균, `single` = 단일 값. 판정은 `value`, 시뮬 편차는 mean(= `stats.mean`, 없으면 `value`). |
| 시각 | 모든 시각은 그 파형 파일의 시간축 그대로(초). |

## 2. 지표 카탈로그

| metric_id | 이름 | 단위 → 표시 | 대상 | `value` | worst | stats | 시뮬 비교 |
|---|---|---|---|---|---|---|---|
| `rise_time` | 상승 시간 | s → ns | OUT 채널 | 엣지별 10 %→90 % 시간의 최댓값 | max | O | O |
| `fall_time` | 하강 시간 | s → ns | OUT 채널 | 엣지별 90 %→10 % 시간의 최댓값 | max | O | O |
| `tplh` | 전파 지연 tpLH | s → ns | 경로 | 입력 50 % → 출력 50 %(출력 상승), 엣지별 최댓값 | max | O | O (오프셋 보정) |
| `tphl` | 전파 지연 tpHL | s → ns | 경로 | 같은 방식(출력 하강) 최댓값 | max | O | O (오프셋 보정) |
| `tpd` | 전파 지연 tpd | s → ns | 경로 | max(tplh 최댓값, tphl 최댓값). stats는 두 방향 엣지 전체 | max | O | X |
| `period` | 클럭 주기 | s → ns | CLK | 연속 상승 50 % 교차 간격의 평균 | — (mean) | O | O |
| `frequency` | 클럭 주파수 | Hz → MHz | CLK | 1 / period 평균 | — | X | X |
| `duty_cycle` | 듀티 사이클 | % | CLK | (상승 50 % → 다음 하강 50 %) / 주기 × 100, 사이클 평균 | — (mean) | O | O |
| `setup_slack` | 셋업 슬랙 (이 캡처) | s → ns | DATA·OUT 채널 vs CLK 상승 | 데이터 50 % 전이마다 (다음 CLK 상승 − 전이), 최솟값 | min | O | O |
| `hold_slack` | 홀드 슬랙 (이 캡처) | s → ns | DATA·OUT 채널 vs CLK 상승 | 데이터 50 % 전이마다 (전이 − 직전 CLK 상승), 최솟값 | min | O | O |
| `voh` | 출력 High 전압 | V | OUT 채널 | high 안정 구간(엣지 주변 제외) 중앙값 | — | X | O |
| `vol` | 출력 Low 전압 | V | OUT 채널 | low 안정 구간 중앙값 | — | X | O (시뮬 0 → 편차 없음) |
| `idd_avg` | 평균 공급 전류 | A → µA | IDD 채널 | 기록 전체 평균 | — | X | X |
| `avg_power` | 평균 전력 | W → µW | IDD 채널 | VDD × idd_avg (VDD 채널 평균, 없으면 논리 VDD) | — | X | X |
| `iddq` | 정적 전류 IDDQ | A → µA | DC 스윕 | 스윕(V–I)을 논리 VDD에서 선형 보간한 전류 | — | X | X |
| `match_rate` | 기능 일치율 | % | 기능 대상 OUT | 일치 사이클 / 비교 사이클 × 100 (기대 비트열 있을 때만) | — | X | X |

- 슬랙은 "이 캡처에서의 여유"다. 실제 setup/hold 마진(Shmoo)은 Phase 1.
- `period`가 없는(상승 엣지 < 2) 경우 `period`·`frequency`·`duty_cycle`은 `value=None` + `INSUFFICIENT_EDGES`.
- I–V 곡선은 지표가 아니라 `DCSweep` 데이터 그 자체로 DC 탭에 그린다.

## 3. 근거(Evidence) 채우는 법 — 파형 마커·분포 차트용

`EdgeSample(t_s, value, t_start_s, t_end_s)` — `t_s` = 마커 시각, `value` = 그 엣지의 지표 값(SI), `t_start_s`–`t_end_s` = 음영/구간. `edges`는 `t_s` 오름차순.

| metric_id | `edges[].t_s` | `t_start_s` → `t_end_s` | `ref_levels_v` 키 | `worst_time_s` | `params` |
|---|---|---|---|---|---|
| `rise_time` | 출력 50 % 교차 | 10 % 교차 → 90 % 교차 | `low`, `high`, `v10`, `v90` | 최댓값 엣지의 t_s | — |
| `fall_time` | 출력 50 % 교차 | 90 % 교차 → 10 % 교차 | `low`, `high`, `v10`, `v90` | 최댓값 엣지 | — |
| `tplh` / `tphl` | 출력 50 % 교차 | 입력 50 % → 출력 50 % | `in_v50`, `out_v50` | 최댓값 엣지 | — |
| `tpd` | tplh·tphl 엣지 합집합 | 입력 50 % → 출력 50 % | `in_v50`, `out_v50` | 최댓값 엣지 | — |
| `period` | k번째 CLK 상승 50 % | 상승 k → 상승 k+1 | `v50` | None | — |
| `frequency` | (없음) | — | `v50` | None | — |
| `duty_cycle` | k번째 CLK 상승 50 % | 상승 k → 다음 하강 | `v50` | None | — |
| `setup_slack` | 데이터 50 % 전이 | 전이 → 다음 CLK 상승 | `clk_v50`, `data_v50` | 최솟값 엣지 | — |
| `hold_slack` | 데이터 50 % 전이 | 직전 CLK 상승 → 전이 | `clk_v50`, `data_v50` | 최솟값 엣지 | — |
| `voh` / `vol` | (없음) | — | `low`, `high` | None | — |
| `idd_avg` | (없음) | — | — | None | — |
| `avg_power` | (없음) | — | — | None | `vdd_v`, `idd_avg_a` |
| `iddq` | (없음) | — | — | None | `vdd_v` |
| `match_rate` | (없음, 상세는 `FunctionalDetail`) | — | `threshold_v` | None | — |

## 4. 기능 검증 (D7)

- 출력(기능 대상 OUT)을 CLK 상승 50 % 교차 시각마다 선형 보간으로 샘플링, 값 ≥ 논리 VDD/2 → '1', 아니면 '0'.
- 사이클 번호는 1부터: n번째 사이클 = 기록 안의 n번째 CLK 상승 엣지.
- 기대 비트열은 '0'/'1'만(공백·`_`·`,` 무시). min(두 길이)만큼 비교, 길이가 다르면 `EXPECTED_LENGTH_MISMATCH`.
- 일치율 100 %면 PASS, 아니면 FAIL(마진 없음).

## 5. 판정·편차 요약 (D5·D6·D8)

- 마진: 상한 `(max − v)/|max| × 100`, 하한 `(v − min)/|min| × 100`, 범위는 작은 쪽. 한계 0이면 마진 없이 PASS/FAIL.
- 등급: PASS ≥ 10 % · MARGINAL 0 ~ 10 % · FAIL < 0 (임계는 설정값).
- 시뮬 편차: `((측정 mean − offset) − 시뮬 mean) / |시뮬 mean| × 100`, offset은 tplh·tphl만. |편차| > 20 %(설정값) → `SIM_DEVIATION`.
- 대역폭: `rise_time`/`fall_time` mean < 2 × 0.35 / BW → `BANDWIDTH_LIMIT` (500 MHz → 1.4 ns, 100 MHz → 7 ns).
