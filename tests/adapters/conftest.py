"""Shared fixtures for adapter / synth tests."""

from __future__ import annotations

import json
from pathlib import Path as FsPath

import pytest

from synth import generate

SYNTH_FILES = ("synth_scope.csv", "synth_scope_err.csv", "synth_sim.csv", "synth_dmm.xlsx", "golden.json")


@pytest.fixture(scope="session")
def synth_dir(tmp_path_factory: pytest.TempPathFactory) -> FsPath:
    """synth/data if all five files exist, else a freshly generated copy."""
    d = generate.DEFAULT_OUT_DIR
    if all((d / f).is_file() for f in SYNTH_FILES):
        return d
    out = tmp_path_factory.mktemp("synth_data")
    generate.write_all(out)
    return out


@pytest.fixture(scope="session")
def golden(synth_dir: FsPath) -> dict:
    return json.loads((synth_dir / "golden.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def synth_bytes(synth_dir: FsPath) -> dict[str, bytes]:
    return {f: (synth_dir / f).read_bytes() for f in SYNTH_FILES}
