"""Golden-test helpers: read the synthetic files directly with numpy/pandas (independent of core.adapters).

The files are read the same way a measurement would be (text rounding, noise and ringing included),
then turned into contract models (`Waveform`, `DCSweep`, `MeasurementSet`) by hand.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path as FsPath
from typing import Any

import numpy as np
import pandas as pd
import pytest

from core.models import (
    AnalysisResult,
    AnalysisSettings,
    ChannelInfo,
    ChannelMap,
    DCSweep,
    ExpectedPattern,
    MeasurementSet,
    Path,
    SessionInfo,
    Source,
    Waveform,
)

DATA = FsPath(__file__).resolve().parents[2] / "synth" / "data"


def _golden() -> dict[str, Any]:
    return json.loads((DATA / "golden.json").read_text(encoding="utf-8"))


def _setup(golden: dict[str, Any]) -> tuple[ChannelMap, list[Path]]:
    s = golden["setup"]
    cmap = ChannelMap(channels=[ChannelInfo(**c) for c in s["channel_map"]])
    paths = [Path(**p) for p in s["paths"]]
    return cmap, paths


def read_scope_csv(path: FsPath, golden: dict[str, Any]) -> list[Waveform]:
    """Scope CSV: 4 metadata lines, then header `Time(s),CH1(V),...,CH4(A)`."""
    df = pd.read_csv(path, skiprows=4, encoding="utf-8")
    cols = golden["setup"]["scope_columns"]
    t = df[cols["time"]].to_numpy(dtype=np.float64)
    out = []
    for ch in ("CH1", "CH2", "CH3", "CH4"):
        col = cols[ch]
        unit = col[col.index("(") + 1 : col.index(")")]
        out.append(
            Waveform(
                channel_id=ch,
                quantity=unit,
                time_s=t,
                values=df[col].to_numpy(dtype=np.float64),
                source_column=col,
                source_unit=unit,
            )
        )
    return out


def read_sim_wrdata(path: FsPath, golden: dict[str, Any]) -> list[Waveform]:
    """ngspice wrdata look-alike: whitespace separated, `time` repeated before every vector."""
    with path.open(encoding="utf-8") as fh:
        header = fh.readline().split()
    data = pd.read_csv(path, sep=r"\s+", skiprows=1, header=None).to_numpy(dtype=np.float64)
    assert data.shape[1] == len(header)
    t = data[:, 0]
    mapping = golden["setup"]["sim_mapping"]
    out = []
    for i, name in enumerate(header):
        if name == "time":
            # repeated time columns must equal the first one (dropped)
            np.testing.assert_allclose(data[:, i], t, rtol=1e-9, atol=0.0)
            continue
        out.append(
            Waveform(channel_id=mapping[name], quantity="V", time_s=t, values=data[:, i], source_column=name)
        )
    return out


def read_dmm_xlsx(path: FsPath, golden: dict[str, Any]) -> DCSweep:
    """DMM workbook: merged title row, blank row, header row 3 (`전압(V)`, `전류(µA)`)."""
    d = golden["setup"]["dmm"]
    df = pd.read_excel(path, sheet_name=d["sheet"], header=2)
    x = df[d["x_column"]].to_numpy(dtype=np.float64) * d["x_scale"]
    y = df[d["y_column"]].to_numpy(dtype=np.float64) * d["y_scale"]
    order = np.argsort(x)
    return DCSweep(name=d["sweep_name"], x=x[order], y=y[order], x_label=d["x_column"], y_label=d["y_column"])


@pytest.fixture(scope="session")
def golden() -> dict[str, Any]:
    return _golden()


@pytest.fixture(scope="session")
def settings(golden) -> AnalysisSettings:
    return AnalysisSettings(logic_vdd_v=golden["setup"]["logic_vdd_v"])


@pytest.fixture(scope="session")
def scope_waveforms(golden) -> list[Waveform]:
    return read_scope_csv(DATA / golden["files"]["scope"], golden)


@pytest.fixture(scope="session")
def scope_err_waveforms(golden) -> list[Waveform]:
    return read_scope_csv(DATA / golden["files"]["scope_err"], golden)


@pytest.fixture(scope="session")
def dmm_sweep(golden) -> DCSweep:
    return read_dmm_xlsx(DATA / golden["files"]["dmm"], golden)


@pytest.fixture(scope="session")
def scope_set(golden, scope_waveforms, dmm_sweep) -> MeasurementSet:
    """Normal scope file + DMM sweep (the demo measured set)."""
    cmap, paths = _setup(golden)
    return MeasurementSet(
        session=SessionInfo(source=Source.MEASURED, files=[golden["files"]["scope"], golden["files"]["dmm"]]),
        channel_map=cmap,
        paths=paths,
        waveforms=scope_waveforms,
        dc_sweeps=[dmm_sweep],
    )


@pytest.fixture(scope="session")
def scope_err_set(golden, scope_err_waveforms) -> MeasurementSet:
    cmap, paths = _setup(golden)
    return MeasurementSet(
        session=SessionInfo(source=Source.MEASURED, files=[golden["files"]["scope_err"]]),
        channel_map=cmap,
        paths=paths,
        waveforms=scope_err_waveforms,
    )


@pytest.fixture(scope="session")
def sim_set(golden) -> MeasurementSet:
    cmap, paths = _setup(golden)
    return MeasurementSet(
        session=SessionInfo(source=Source.SIM, files=[golden["files"]["sim"]]),
        channel_map=cmap,
        paths=paths,
        waveforms=read_sim_wrdata(DATA / golden["files"]["sim"], golden),
    )


@pytest.fixture(scope="session")
def expected(golden) -> ExpectedPattern:
    return ExpectedPattern(bits=golden["bits"])


@pytest.fixture(scope="session")
def scope_out(scope_set, settings, expected):
    from core.analyzers import analyze_all

    return analyze_all(scope_set, settings, expected)


@pytest.fixture(scope="session")
def scope_err_out(scope_err_set, settings, expected):
    from core.analyzers import analyze_all

    return analyze_all(scope_err_set, settings, expected)


@pytest.fixture(scope="session")
def sim_out(sim_set, settings):
    from core.analyzers import analyze_all

    return analyze_all(sim_set, settings, None)


@pytest.fixture(scope="session")
def pick() -> Callable[..., AnalysisResult]:
    """pick(results, metric_id, path=None, channel_id=None) -> the single matching result."""

    def _pick(results: list[AnalysisResult], metric_id: str, *, path: str | None = None,
              channel_id: str | None = None) -> AnalysisResult:
        found = [
            r for r in results
            if r.metric_id == metric_id
            and (path is None or r.path == path)
            and (channel_id is None or r.channel_id == channel_id)
        ]
        assert len(found) == 1, f"{metric_id}: expected exactly one result, got {len(found)}"
        return found[0]

    return _pick


@pytest.fixture(scope="session")
def check_answer() -> Callable[..., None]:
    """check_answer(measured, answer_dict, what) — asserts golden tolerance (rel_tol_pct and/or abs_tol)."""

    def _check(measured: float | None, answer: dict[str, Any], what: str) -> None:
        assert measured is not None, f"{what}: no value"
        target = float(answer["value"])
        if "abs_tol" in answer:
            assert abs(measured - target) <= answer["abs_tol"], (
                f"{what}: {measured!r} vs {target!r} (abs tol {answer['abs_tol']})"
            )
        if "rel_tol_pct" in answer and target != 0.0:
            err = abs(measured - target) / abs(target) * 100.0
            assert err <= answer["rel_tol_pct"], (
                f"{what}: {measured!r} vs {target!r} -> {err:.3f} % > {answer['rel_tol_pct']} %"
            )

    return _check
