"""Input adapters (docs/contract.md section 2): file bytes -> preview -> RawTable -> Waveform/DCSweep.

Failures raise ValueError with a Korean message; minor issues are returned as Notice lists.
"""

from .headers import split_header_unit
from .normalize import to_dc_sweep, to_waveforms
from .sim_mapping import suggest_sim_mapping
from .table import preview_file, read_table

# TODO(Phase 1): instrument-specific scope CSV auto-detection; ngspice raw binary parser.

__all__ = [
    "preview_file",
    "read_table",
    "split_header_unit",
    "to_waveforms",
    "to_dc_sweep",
    "suggest_sim_mapping",
]
