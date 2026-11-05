"""Shared pydantic base class and the numpy array field type."""

from __future__ import annotations

from typing import Annotated, Any

import numpy as np
from pydantic import BaseModel, BeforeValidator, ConfigDict, PlainSerializer


class ContractModel(BaseModel):
    """Base for every contract model: unknown fields rejected, NaN/inf rejected."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


def _to_float_array(v: Any) -> np.ndarray:
    arr = np.asarray(v, dtype=np.float64)
    if arr.ndim != 1:
        raise ValueError("expected a 1-D array")
    if arr.size and not np.all(np.isfinite(arr)):
        raise ValueError("array contains NaN or inf")
    return arr


# 1-D float64 numpy array. Accepts lists/arrays; serialized to a JSON list only in JSON mode.
FloatArray = Annotated[
    np.ndarray,
    BeforeValidator(_to_float_array),
    PlainSerializer(lambda a: a.tolist(), return_type=list, when_used="json"),
]
