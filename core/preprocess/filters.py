"""Optional smoothing and the shared "values used for analysis" helper."""

from __future__ import annotations

import numpy as np
from scipy.signal import savgol_filter

from core.models import AnalysisSettings, Waveform


def smooth_values(values: np.ndarray, points: int) -> np.ndarray:
    """Savitzky-Golay smoothing over an odd window of about `points` samples (< 3 = off).

    The window is clipped to the record length; polynomial order 2 (1 for 3-4 point windows).
    """
    n = int(values.shape[0])
    if points < 3 or n < 3:
        return values
    window = points if points % 2 == 1 else points + 1
    if window > n:
        window = n if n % 2 == 1 else n - 1
    if window < 3:
        return values
    order = 2 if window >= 5 else 1
    return savgol_filter(values, window, order, mode="interp")


def signal_values(wf: Waveform, settings: AnalysisSettings) -> np.ndarray:
    """Waveform values used by level estimation and edge detection (smoothed if enabled)."""
    return smooth_values(wf.values, settings.smoothing_points)
