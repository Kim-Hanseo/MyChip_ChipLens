"""Metric catalog (decisions D4). Order of METRICS = canonical result order."""

from __future__ import annotations

from pydantic import Field

from .base import ContractModel
from .enums import Aggregate, Category, Role, Target


class MetricDef(ContractModel):
    metric_id: str
    label: str  # Korean display name
    short_label: str  # compact name for cards/charts
    category: Category
    unit: str  # SI unit of `value` ("s", "V", "A", "W", "Hz", "%")
    display_unit: str  # e.g. "ns", "µA" (U+00B5)
    display_scale: float  # display = value * display_scale
    definition: str  # Korean tooltip text
    aggregate: Aggregate  # how `value` is chosen; MAX/MIN = worst direction
    target: Target
    roles: tuple[Role, ...] = ()  # channel roles the metric is computed for (CHANNEL target)
    has_stats: bool  # True -> AnalysisResult.stats is filled (per-edge distribution)
    sim_compare: bool  # True -> judge computes deviation vs sim
    family: str = Field(default="")  # card-3 de-duplication group; "" -> metric_id


def _m(**kw) -> MetricDef:
    d = MetricDef(**kw)
    if not d.family:
        d = d.model_copy(update={"family": d.metric_id})
    return d


_DEFS: list[MetricDef] = [
    _m(metric_id="rise_time", label="상승 시간", short_label="rise", category=Category.TIMING,
       unit="s", display_unit="ns", display_scale=1e9, aggregate=Aggregate.MAX, target=Target.CHANNEL,
       roles=(Role.OUT,), has_stats=True, sim_compare=True, family="edge_rate",
       definition="출력 상승 엣지의 10 %→90 % 시간. 10/90 %는 그 채널의 실측 low/high 레벨 기준. 엣지별 계산 후 최댓값으로 판정."),
    _m(metric_id="fall_time", label="하강 시간", short_label="fall", category=Category.TIMING,
       unit="s", display_unit="ns", display_scale=1e9, aggregate=Aggregate.MAX, target=Target.CHANNEL,
       roles=(Role.OUT,), has_stats=True, sim_compare=True, family="edge_rate",
       definition="출력 하강 엣지의 90 %→10 % 시간. 실측 low/high 레벨 기준. 엣지별 계산 후 최댓값으로 판정."),
    _m(metric_id="tplh", label="전파 지연 tpLH", short_label="tpLH", category=Category.TIMING,
       unit="s", display_unit="ns", display_scale=1e9, aggregate=Aggregate.MAX, target=Target.PATH,
       has_stats=True, sim_compare=True, family="prop_delay",
       definition="경로 입력 50 % 교차 → 출력 50 % 교차(출력 상승). 각 채널의 실측 레벨 기준 50 %. 엣지별 최댓값으로 판정."),
    _m(metric_id="tphl", label="전파 지연 tpHL", short_label="tpHL", category=Category.TIMING,
       unit="s", display_unit="ns", display_scale=1e9, aggregate=Aggregate.MAX, target=Target.PATH,
       has_stats=True, sim_compare=True, family="prop_delay",
       definition="경로 입력 50 % 교차 → 출력 50 % 교차(출력 하강). 엣지별 최댓값으로 판정."),
    _m(metric_id="tpd", label="전파 지연 tpd", short_label="tpd", category=Category.TIMING,
       unit="s", display_unit="ns", display_scale=1e9, aggregate=Aggregate.MAX, target=Target.PATH,
       has_stats=True, sim_compare=False, family="prop_delay",
       definition="max(tpLH 최댓값, tpHL 최댓값). 'tpd' 스펙은 이 지표로 판정."),
    _m(metric_id="period", label="클럭 주기", short_label="period", category=Category.TIMING,
       unit="s", display_unit="ns", display_scale=1e9, aggregate=Aggregate.MEAN, target=Target.CHANNEL,
       roles=(Role.CLK,), has_stats=True, sim_compare=True,
       definition="연속한 CLK 상승 50 % 교차 간격의 평균."),
    _m(metric_id="frequency", label="클럭 주파수", short_label="freq", category=Category.TIMING,
       unit="Hz", display_unit="MHz", display_scale=1e-6, aggregate=Aggregate.MEAN, target=Target.CHANNEL,
       roles=(Role.CLK,), has_stats=False, sim_compare=False,
       definition="1 / (주기 평균)."),
    _m(metric_id="duty_cycle", label="듀티 사이클", short_label="duty", category=Category.TIMING,
       unit="%", display_unit="%", display_scale=1.0, aggregate=Aggregate.MEAN, target=Target.CHANNEL,
       roles=(Role.CLK,), has_stats=True, sim_compare=True,
       definition="CLK high 구간(상승 50 % → 다음 하강 50 %) / 주기 × 100, 사이클 평균."),
    _m(metric_id="setup_slack", label="셋업 슬랙 (이 캡처)", short_label="setup", category=Category.TIMING,
       unit="s", display_unit="ns", display_scale=1e9, aggregate=Aggregate.MIN, target=Target.CHANNEL,
       roles=(Role.DATA, Role.OUT), has_stats=True, sim_compare=True, family="slack",
       definition="데이터 50 % 전이마다 (다음 CLK 상승 50 % − 전이 시각). 최솟값으로 판정. 이 캡처에서의 여유이며 실제 setup 마진(Shmoo)이 아님."),
    _m(metric_id="hold_slack", label="홀드 슬랙 (이 캡처)", short_label="hold", category=Category.TIMING,
       unit="s", display_unit="ns", display_scale=1e9, aggregate=Aggregate.MIN, target=Target.CHANNEL,
       roles=(Role.DATA, Role.OUT), has_stats=True, sim_compare=True, family="slack",
       definition="데이터 50 % 전이마다 (전이 시각 − 직전 CLK 상승 50 %). 최솟값으로 판정. 이 캡처에서의 여유."),
    _m(metric_id="voh", label="출력 High 전압", short_label="VOH", category=Category.DC,
       unit="V", display_unit="V", display_scale=1.0, aggregate=Aggregate.SINGLE, target=Target.CHANNEL,
       roles=(Role.OUT,), has_stats=False, sim_compare=True, family="output_level",
       definition="출력 high 안정 구간(엣지 주변 전이·링잉 제외)의 대표 전압(중앙값)."),
    _m(metric_id="vol", label="출력 Low 전압", short_label="VOL", category=Category.DC,
       unit="V", display_unit="V", display_scale=1.0, aggregate=Aggregate.SINGLE, target=Target.CHANNEL,
       roles=(Role.OUT,), has_stats=False, sim_compare=True, family="output_level",
       definition="출력 low 안정 구간(엣지 주변 제외)의 대표 전압(중앙값). 시뮬값이 0이면 편차를 계산하지 않음."),
    _m(metric_id="idd_avg", label="평균 공급 전류", short_label="IDD avg", category=Category.DC,
       unit="A", display_unit="µA", display_scale=1e6, aggregate=Aggregate.SINGLE, target=Target.CHANNEL,
       roles=(Role.IDD,), has_stats=False, sim_compare=False, family="supply",
       definition="IDD 채널 전체 기록의 평균 전류."),
    _m(metric_id="avg_power", label="평균 전력", short_label="P avg", category=Category.DC,
       unit="W", display_unit="µW", display_scale=1e6, aggregate=Aggregate.SINGLE, target=Target.CHANNEL,
       roles=(Role.IDD,), has_stats=False, sim_compare=False, family="supply",
       definition="VDD × IDD 평균. VDD 채널이 있으면 그 평균, 없으면 논리 VDD 설정값."),
    _m(metric_id="iddq", label="정적 전류 IDDQ", short_label="IDDQ", category=Category.DC,
       unit="A", display_unit="µA", display_scale=1e6, aggregate=Aggregate.SINGLE, target=Target.SWEEP,
       has_stats=False, sim_compare=False,
       definition="DC 스윕(V–I)을 논리 VDD에서 선형 보간한 전류."),
    _m(metric_id="match_rate", label="기능 일치율", short_label="match", category=Category.FUNCTIONAL,
       unit="%", display_unit="%", display_scale=1.0, aggregate=Aggregate.SINGLE, target=Target.CHANNEL,
       roles=(Role.OUT,), has_stats=False, sim_compare=False,
       definition="CLK 상승 50 % 시각에 출력을 논리 VDD/2로 샘플링한 비트와 기대 비트열의 일치 사이클 / 비교 사이클 × 100. 100 %면 PASS."),
]

METRICS: dict[str, MetricDef] = {d.metric_id: d for d in _DEFS}
METRIC_IDS: tuple[str, ...] = tuple(METRICS)
METRIC_INDEX: dict[str, int] = {mid: i for i, mid in enumerate(METRIC_IDS)}
