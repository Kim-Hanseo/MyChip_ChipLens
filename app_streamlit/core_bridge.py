"""Lazy access to ``core.adapters`` / ``core.pipeline`` (they may not exist yet during the mock stage).

Imports happen inside functions on every call, so as soon as parser-agent / judge-agent land their
modules the next rerun picks them up. Call sites use the contract signatures verbatim (section 2, 4.6).
"""

from __future__ import annotations

import importlib
import json
from types import ModuleType
from typing import Callable

import streamlit as st

from core.models import (
    AnalysisReport,
    AnalysisRequest,
    ChannelConversion,
    DCSweepBuildResult,
    RawTable,
    ReadOptions,
    TablePreview,
    TimeAxisSpec,
    WaveformBuildResult,
)

ADAPTER_FUNCS = ("preview_file", "read_table", "split_header_unit", "to_waveforms", "to_dc_sweep",
                 "suggest_sim_mapping")


def _import(name: str) -> tuple[ModuleType | None, str | None]:
    try:
        return importlib.import_module(name), None
    except ModuleNotFoundError as e:
        if e.name and (e.name == name or name.startswith(e.name + ".")):
            return None, f"준비 중 ({name} 없음)"
        return None, f"import 오류: {e}"
    except Exception as e:  # noqa: BLE001 - another agent's module may be mid-edit
        return None, f"import 오류: {e!r}"


def get_adapters() -> tuple[ModuleType | None, str | None]:
    """(core.adapters, None) when all 6 contract functions exist, else (None, Korean status)."""
    mod, msg = _import("core.adapters")
    if mod is None:
        return None, msg
    missing = [f for f in ADAPTER_FUNCS if not hasattr(mod, f)]
    if missing:
        return None, f"준비 중 (미구현: {', '.join(missing)})"
    return mod, None


def get_run_analysis() -> tuple[Callable[[AnalysisRequest], AnalysisReport] | None, str | None]:
    """(core.pipeline.run_analysis, None) or (None, Korean status)."""
    mod, msg = _import("core.pipeline")
    if mod is None:
        return None, msg
    fn = getattr(mod, "run_analysis", None)
    if fn is None:
        return None, "준비 중 (run_analysis 미구현)"
    return fn, None


# ---- cached adapter calls (keyed by file bytes + options JSON)


@st.cache_data(show_spinner=False, max_entries=64)
def cached_preview(data: bytes, file_name: str, options_json: str | None) -> TablePreview:
    """preview_file(bytes, name) when options_json is None, else preview_file(bytes, name, options)."""
    ad, msg = get_adapters()
    if ad is None:
        raise RuntimeError(msg)
    options = ReadOptions.model_validate_json(options_json) if options_json else None
    return ad.preview_file(data, file_name, options)


@st.cache_data(show_spinner=False, max_entries=32)
def cached_read_table(data: bytes, file_name: str, options_json: str) -> RawTable:
    """read_table(bytes, name, options)."""
    ad, msg = get_adapters()
    if ad is None:
        raise RuntimeError(msg)
    return ad.read_table(data, file_name, ReadOptions.model_validate_json(options_json))


@st.cache_data(show_spinner=False, max_entries=32)
def cached_to_waveforms(data: bytes, file_name: str, options_json: str, time_axis_json: str,
                        conversions_json: str) -> WaveformBuildResult:
    """to_waveforms(read_table(...), TimeAxisSpec, [ChannelConversion]) — cached so reruns stay cheap."""
    ad, msg = get_adapters()
    if ad is None:
        raise RuntimeError(msg)
    table = cached_read_table(data, file_name, options_json)
    convs = [ChannelConversion.model_validate(c) for c in json.loads(conversions_json)]
    return ad.to_waveforms(table, TimeAxisSpec.model_validate_json(time_axis_json), convs)


@st.cache_data(show_spinner=False, max_entries=32)
def cached_to_dc_sweep(data: bytes, file_name: str, options_json: str, x_column: str, y_column: str,
                       x_scale: float, y_scale: float, name: str) -> DCSweepBuildResult:
    """to_dc_sweep(read_table(...), x, y, x_scale=, y_scale=, name=) — cached."""
    ad, msg = get_adapters()
    if ad is None:
        raise RuntimeError(msg)
    table = cached_read_table(data, file_name, options_json)
    return ad.to_dc_sweep(table, x_column, y_column, x_scale=x_scale, y_scale=y_scale, name=name)


def conversions_json(conversions: list[ChannelConversion]) -> str:
    return json.dumps([c.model_dump(mode="json") for c in conversions])
