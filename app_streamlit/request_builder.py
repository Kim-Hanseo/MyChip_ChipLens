"""Turn UI inputs (editor rows, widget values) into contract models (pure, no streamlit import).

Only shape conversion + validation messages; no analysis. Spec values are entered in display units
and converted to SI with ``METRICS[id].display_scale`` (contract section 6).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import Any

import pandas as pd
from pydantic import ValidationError

from core.models import (
    METRICS,
    AnalysisRequest,
    AnalysisSettings,
    ChannelInfo,
    ChannelMap,
    DCSweep,
    ExpectedPattern,
    MeasurementSet,
    Path,
    Polarity,
    Role,
    SessionInfo,
    Source,
    Spec,
    Waveform,
)

POLARITY_OF = {"비반전": Polarity.NON_INVERTING, "반전": Polarity.INVERTING}
ALL = "(전체)"  # spec editor: path/channel applies to every target
NO_SPEC_METRICS = ("match_rate",)  # judged by the expected bit string, not by a spec (D5)


def metric_options() -> dict[str, str]:
    """Spec-editor option label -> metric_id, e.g. 'tpd · 전파 지연 tpd [ns]'."""
    return {
        f"{mid} · {m.label} [{m.display_unit}]": mid
        for mid, m in METRICS.items()
        if mid not in NO_SPEC_METRICS
    }


def metric_option_of() -> dict[str, str]:
    """metric_id -> option label (inverse of ``metric_options``)."""
    return {mid: label for label, mid in metric_options().items()}


def _blank(v: Any) -> bool:
    """None / NaN / pandas NA / empty string -> True (editor cells)."""
    if v is None:
        return True
    if isinstance(v, str):
        return not v.strip()
    try:
        return bool(pd.isna(v))
    except (TypeError, ValueError):
        return False


def _text(v: Any) -> str | None:
    return None if _blank(v) else str(v).strip()


def _target(v: Any) -> str | None:
    t = _text(v)
    return None if t == ALL else t


def _num(v: Any) -> float | None:
    if _blank(v):
        return None
    return float(v)


def _err(e: ValidationError) -> str:
    return "; ".join(str(x.get("msg", x)) for x in e.errors())


# ---------------------------------------------------------------- channel map / paths / specs


def build_channel_map(rows: Iterable[tuple[str, Role | str, str | None]]) -> ChannelMap:
    """(channel_id, role, label) in UI order -> ChannelMap."""
    return ChannelMap(channels=[
        ChannelInfo(channel_id=cid, role=Role(role), label=_text(label)) for cid, role, label in rows
    ])


def paths_from_rows(rows: Sequence[Mapping[str, Any]], channel_ids: Sequence[str], *,
                    check_channels: bool = True) -> tuple[list[Path], list[str]]:
    """Path-editor rows ('이름', '입력 채널', '출력 채널', '극성') -> Paths + Korean error messages.

    ``check_channels=False`` skips the "unknown channel" check (no measured file loaded yet)."""
    paths: list[Path] = []
    errors: list[str] = []
    known = set(channel_ids)
    for i, row in enumerate(rows, start=1):
        name, cin, cout = _text(row.get("이름")), _text(row.get("입력 채널")), _text(row.get("출력 채널"))
        if name is None and cin is None and cout is None:
            continue  # empty row added by the editor
        if name is None or cin is None or cout is None:
            errors.append(f"경로 {i}행: 이름·입력 채널·출력 채널을 모두 입력하세요")
            continue
        missing = [c for c in (cin, cout) if c not in known] if check_channels else []
        if missing:
            errors.append(f"경로 '{name}': 알 수 없는 채널 {', '.join(missing)}")
            continue
        if cin == cout:
            errors.append(f"경로 '{name}': 입력과 출력 채널이 같습니다")
            continue
        pol = POLARITY_OF.get(_text(row.get("극성")) or "비반전", Polarity.NON_INVERTING)
        paths.append(Path(name=name, input_channel=cin, output_channel=cout, polarity=pol))
    names = [p.name for p in paths]
    dup = sorted({n for n in names if names.count(n) > 1})
    if dup:
        errors.append(f"경로 이름이 중복됩니다: {', '.join(dup)}")
    return paths, errors


def specs_from_rows(rows: Sequence[Mapping[str, Any]]) -> tuple[list[Spec], list[str]]:
    """Spec-editor rows in display units -> SI Specs + Korean error messages."""
    options = metric_options()
    specs: list[Spec] = []
    errors: list[str] = []
    for i, row in enumerate(rows, start=1):
        label = _text(row.get("지표"))
        lo, hi = _num(row.get("최소")), _num(row.get("최대"))
        if label is None and lo is None and hi is None:
            continue
        if label is None or label not in options:
            errors.append(f"스펙 {i}행: 지표를 선택하세요")
            continue
        mid = options[label]
        if lo is None and hi is None:
            errors.append(f"스펙 {i}행 ({mid}): 최소 또는 최대 중 하나 이상 입력하세요")
            continue
        scale = METRICS[mid].display_scale
        try:
            specs.append(Spec(
                metric_id=mid, path=_target(row.get("경로")), channel_id=_target(row.get("채널")),
                min=None if lo is None else lo / scale, max=None if hi is None else hi / scale,
            ))
        except ValidationError as e:
            errors.append(f"스펙 {i}행 ({mid}): {_err(e)}")
    return specs, errors


def expected_from_text(text: str | None, channel_id: str | None) -> tuple[ExpectedPattern | None, str | None]:
    """Expected bit string (spaces, '_', ',' ignored) -> ExpectedPattern or a Korean error."""
    if text is None or not text.strip():
        return None, None
    try:
        return ExpectedPattern(bits=text, channel_id=channel_id), None
    except ValidationError:
        return None, "기대 비트열에는 0과 1만 쓸 수 있습니다 (공백·_·, 는 무시)"


def build_settings(
    *,
    logic_vdd_v: float,
    bandwidth_mhz: float | None,
    marginal_threshold_pct: float,
    sim_tolerance_pct: float,
    delay_offset_ns: float,
    edge_hysteresis_pct: float,
    min_pulse_width_ns: float,
    smoothing_points: int,
) -> AnalysisSettings:
    """UI units (MHz, ns) -> AnalysisSettings (SI)."""
    return AnalysisSettings(
        logic_vdd_v=logic_vdd_v,
        bandwidth_hz=None if not bandwidth_mhz else bandwidth_mhz * 1e6,
        marginal_threshold_pct=marginal_threshold_pct,
        sim_tolerance_pct=sim_tolerance_pct,
        delay_offset_s=(delay_offset_ns or 0.0) * 1e-9,
        edge_hysteresis_pct=edge_hysteresis_pct,
        min_pulse_width_s=(min_pulse_width_ns or 0.0) * 1e-9,
        smoothing_points=int(smoothing_points or 0),
    )


def build_request(
    *,
    channel_map: ChannelMap,
    paths: list[Path],
    waveforms: list[Waveform],
    dc_sweeps: list[DCSweep],
    sim_waveforms: list[Waveform],
    specs: list[Spec],
    expected: ExpectedPattern | None,
    settings: AnalysisSettings,
    chip_id: str | None = None,
    temperature_c: float | None = None,
    measured_files: Sequence[str] = (),
    sim_files: Sequence[str] = (),
) -> tuple[AnalysisRequest | None, list[str]]:
    """Assemble MeasurementSet x(1..2) + AnalysisRequest (contract section 6). Returns (request, errors)."""
    errors: list[str] = []
    if not waveforms and not dc_sweeps:
        errors.append("측정 파형이나 DC 스윕이 하나도 없습니다")
    used = [c for c in channel_map.channels if c.role != Role.UNUSED]
    if waveforms and not used:
        errors.append("모든 채널이 '사용 안 함'입니다 — ④에서 역할을 지정하세요")
    if errors:
        return None, errors

    def interval(ws: list[Waveform]) -> float | None:
        return ws[0].sample_interval_s if ws else None

    try:
        measured = MeasurementSet(
            session=SessionInfo(source=Source.MEASURED, chip_id=_text(chip_id), temperature_c=temperature_c,
                                vdd_v=settings.logic_vdd_v, sample_interval_s=interval(waveforms),
                                files=list(measured_files)),
            channel_map=channel_map, paths=paths, waveforms=waveforms, dc_sweeps=dc_sweeps,
        )
        sim = None
        if sim_waveforms:
            sim = MeasurementSet(
                session=SessionInfo(source=Source.SIM, sample_interval_s=interval(sim_waveforms),
                                    files=list(sim_files)),
                channel_map=channel_map, paths=paths, waveforms=sim_waveforms,
            )
        request = AnalysisRequest(measured=measured, sim=sim, specs=specs, expected=expected, settings=settings)
    except ValidationError as e:
        return None, [f"입력 검증 실패: {_err(e)}"]
    return request, []
