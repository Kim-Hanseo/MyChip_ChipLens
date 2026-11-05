"""Preprocessing: level estimation, edge detection, optional smoothing (docs/contract.md section 3)."""

from .edges import detect_edges, detect_edges_array
from .filters import signal_values, smooth_values
from .levels import estimate_levels, estimate_levels_array, estimate_noise_sigma, rough_levels, stable_masks

__all__ = [
    "detect_edges",
    "detect_edges_array",
    "estimate_levels",
    "estimate_levels_array",
    "estimate_noise_sigma",
    "rough_levels",
    "signal_values",
    "smooth_values",
    "stable_masks",
]
