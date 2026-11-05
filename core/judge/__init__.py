"""Judge + Narrator (docs/contract.md section 4): spec verdicts, sim deviation, bandwidth warning,
summary cards and rule-based Korean summary lines. Pure functions, new objects (model_copy)."""

from .bandwidth import apply_bandwidth_check, bandwidth_limit_s
from .cards import build_cards
from .narrator import narrate
from .sim_compare import apply_sim_comparison
from .spec_margin import apply_specs, judge_value, match_spec

__all__ = [
    "match_spec",
    "judge_value",
    "apply_specs",
    "apply_sim_comparison",
    "apply_bandwidth_check",
    "bandwidth_limit_s",
    "build_cards",
    "narrate",
]
