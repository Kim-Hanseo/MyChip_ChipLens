"""Normalizer: RawTable columns -> SI Waveform / DCSweep, with adapter notices (B9)."""

from __future__ import annotations

import numpy as np

from core.models import (
    ChannelConversion,
    DCSweep,
    DCSweepBuildResult,
    Notice,
    Quantity,
    RawTable,
    TimeAxisSpec,
    Waveform,
    WaveformBuildResult,
    WarningCode,
)

SUSPICIOUS_LIMITS: dict[Quantity, float] = {Quantity.VOLTAGE: 100.0, Quantity.CURRENT: 10.0}  # |V|, |A|


def _numeric_column(table: RawTable, name: str, what: str) -> np.ndarray:
    info = table.column(name)
    if info is None or name not in table.data.columns:
        raise ValueError(f"{what} 열 '{name}'이(가) 표에 없습니다.")
    if not info.numeric:
        raise ValueError(f"{what} 열 '{name}'은(는) 숫자 열이 아닙니다.")
    arr = table.data[name].to_numpy(dtype=np.float64, copy=True)
    arr[~np.isfinite(arr)] = np.nan
    return arr


def _range_notice(values: np.ndarray, quantity: Quantity, channel_id: str) -> Notice | None:
    limit = SUSPICIOUS_LIMITS[quantity]
    peak = float(np.max(np.abs(values))) if values.size else 0.0
    if peak <= limit:
        return None
    unit = quantity.value
    return Notice(
        code=WarningCode.SUSPICIOUS_RANGE,
        channel_id=channel_id,
        message=(
            f"{channel_id}: 값 크기가 {peak:.4g} {unit}로 비정상적으로 큽니다(기준 {limit:g} {unit}). "
            "단위·프로브 배율을 확인하세요."
        ),
    )


def to_waveforms(
    table: RawTable, time_axis: TimeAxisSpec, channels: list[ChannelConversion]
) -> WaveformBuildResult:
    """Build SI Waveforms (one per conversion, same order).

    SI value = raw * scale * probe_factor; time = column * scale, or start_s + i * interval_s.
    Rows with NaN in time or any selected channel are dropped (NAN_DROPPED); rows whose time is not
    above the running maximum are dropped (NON_MONOTONIC_AXIS); |V| > 100 or |A| > 10 adds
    SUSPICIOUS_RANGE. Raises ValueError (Korean) for missing/non-numeric columns or < 2 valid rows.
    """
    if not channels:
        raise ValueError("변환할 채널을 하나 이상 선택해 주세요.")
    ids = [c.channel_id for c in channels]
    dup = sorted({i for i in ids if ids.count(i) > 1})
    if dup:
        raise ValueError(f"channel_id가 중복되었습니다: {', '.join(dup)}")
    n = len(table.data)
    notices: list[Notice] = []

    if time_axis.column is not None:
        if time_axis.scale <= 0:
            raise ValueError("시간 배율은 0보다 커야 합니다.")
        t = _numeric_column(table, time_axis.column, "시간") * time_axis.scale
    else:
        if time_axis.interval_s is None:  # pragma: no cover - TimeAxisSpec validates this
            raise ValueError("시간 열이 없으면 샘플 간격이 필요합니다.")
        t = time_axis.start_s + np.arange(n, dtype=np.float64) * time_axis.interval_s
    values = [_numeric_column(table, c.column, "채널") * c.scale * c.probe_factor for c in channels]

    valid = np.isfinite(t)
    for v in values:
        valid &= np.isfinite(v)
    n_nan = int(n - np.count_nonzero(valid))
    if n_nan:
        notices.append(
            Notice(
                code=WarningCode.NAN_DROPPED,
                message=f"빈 값 또는 숫자가 아닌 값이 있는 {n_nan}개 행을 제외했습니다.",
            )
        )
    t = t[valid]
    values = [v[valid] for v in values]

    if t.size:
        keep = np.ones(t.size, dtype=bool)
        keep[1:] = t[1:] > np.maximum.accumulate(t)[:-1]
        n_back = int(t.size - np.count_nonzero(keep))
        if n_back:
            notices.append(
                Notice(
                    code=WarningCode.NON_MONOTONIC_AXIS,
                    message=f"시간이 증가하지 않는(역행·중복) {n_back}개 행을 제외했습니다.",
                )
            )
            t = t[keep]
            values = [v[keep] for v in values]
    if t.size < 2:
        raise ValueError(f"유효한 행이 {t.size}개뿐이라 파형을 만들 수 없습니다(2개 이상 필요).")

    waveforms: list[Waveform] = []
    for conv, v in zip(channels, values, strict=True):
        info = table.column(conv.column)
        note = _range_notice(v, conv.quantity, conv.channel_id)
        if note is not None:
            notices.append(note)
        waveforms.append(
            Waveform(
                channel_id=conv.channel_id,
                quantity=conv.quantity,
                time_s=t.copy(),
                values=v,
                source_column=conv.column,
                source_unit=info.unit_text if info is not None else None,
                probe_factor=conv.probe_factor,
            )
        )
    return WaveformBuildResult(waveforms=waveforms, notices=notices)


def _quantity_of(table: RawTable, column: str, default: Quantity) -> Quantity:
    info = table.column(column)
    if info is not None and info.si_unit in (Quantity.VOLTAGE.value, Quantity.CURRENT.value):
        return Quantity(info.si_unit)
    return default


def to_dc_sweep(
    table: RawTable,
    x_column: str,
    y_column: str,
    *,
    x_scale: float = 1.0,
    y_scale: float = 1.0,
    name: str = "DC",
) -> DCSweepBuildResult:
    """Two columns -> DCSweep (x * x_scale, y * y_scale), NaN rows dropped, sorted by x, duplicate
    x keep the first row. No valid row -> sweep=None."""
    x = _numeric_column(table, x_column, "X") * x_scale
    y = _numeric_column(table, y_column, "Y") * y_scale
    notices: list[Notice] = []
    valid = np.isfinite(x) & np.isfinite(y)
    n_nan = int(x.size - np.count_nonzero(valid))
    if n_nan:
        notices.append(
            Notice(
                code=WarningCode.NAN_DROPPED,
                channel_id=name,
                message=f"{name}: 빈 값 또는 숫자가 아닌 값이 있는 {n_nan}개 행을 제외했습니다.",
            )
        )
    x, y = x[valid], y[valid]
    if x.size == 0:
        return DCSweepBuildResult(sweep=None, notices=notices)
    order = np.argsort(x, kind="stable")
    x, y = x[order], y[order]
    first = np.ones(x.size, dtype=bool)
    first[1:] = x[1:] != x[:-1]
    n_dup = int(x.size - np.count_nonzero(first))
    if n_dup:
        notices.append(
            Notice(
                code=WarningCode.NON_MONOTONIC_AXIS,
                channel_id=name,
                message=f"{name}: X 값이 중복된 {n_dup}개 행을 제외했습니다(처음 행만 사용).",
            )
        )
        x, y = x[first], y[first]
    x_q = _quantity_of(table, x_column, Quantity.VOLTAGE)
    y_q = _quantity_of(table, y_column, Quantity.CURRENT)
    for vals, q in ((x, x_q), (y, y_q)):
        note = _range_notice(vals, q, name)
        if note is not None:
            notices.append(note)
    x_info, y_info = table.column(x_column), table.column(y_column)
    sweep = DCSweep(
        name=name,
        x=x,
        y=y,
        x_quantity=x_q,
        y_quantity=y_q,
        x_label=(x_info.header or x_info.name) if x_info else x_column,
        y_label=(y_info.header or y_info.name) if y_info else y_column,
    )
    return DCSweepBuildResult(sweep=sweep, notices=notices)
