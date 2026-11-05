"""Color tokens for charts (pure data, no streamlit import).

Verdict colors are status colors: always shown together with a symbol + label (never color alone).
They are mode-invariant and readable on both light and dark surfaces. Categorical colors (channel
identity) have separate light/dark steps; pick them with ``palette(dark)``.
"""

from __future__ import annotations

from dataclasses import dataclass

from core.models import VERDICT_LABELS, VERDICT_SYMBOLS, Verdict

# Status palette (fixed, mode-invariant). MARGINAL = orange (warning), FAIL = red, no spec = gray.
VERDICT_COLORS: dict[Verdict | None, str] = {
    Verdict.PASS: "#0ca30c",
    Verdict.MARGINAL: "#f59f00",
    Verdict.FAIL: "#d03b3b",
    None: "#898781",
}

# Streamlit markdown color directive names (theme-aware text colors) for the same verdicts.
VERDICT_MD_COLORS: dict[Verdict | None, str] = {
    Verdict.PASS: "green",
    Verdict.MARGINAL: "orange",
    Verdict.FAIL: "red",
    None: "gray",
}

_CATEGORICAL_LIGHT = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
_CATEGORICAL_DARK = ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#008300", "#9085e9", "#e66767"]

# Neutral chrome that reads on both light and dark chart surfaces.
MUTED = "#898781"
SPEC_LINE = "#898781"
SHADE_ALPHA = 0.14


@dataclass(frozen=True)
class Palette:
    """Mode-specific chart colors."""

    categorical: tuple[str, ...]
    measured: str  # sim-comparison: measured series
    sim: str  # sim-comparison: sim series
    neutral_bar: str  # deviation bars inside tolerance
    band: str  # tolerance band fill (rgba)


def palette(dark: bool = False) -> Palette:
    """Categorical/series colors for the active theme (fixed slot order, never cycled by rank)."""
    cats = _CATEGORICAL_DARK if dark else _CATEGORICAL_LIGHT
    return Palette(
        categorical=tuple(cats),
        measured=cats[0],
        sim=cats[1],
        neutral_bar=cats[0],
        band="rgba(137,135,129,0.18)",
    )


def channel_color(index: int, dark: bool = False) -> str:
    """Color of the index-th channel (ChannelMap order). Past 8 channels fall back to muted gray."""
    cats = palette(dark).categorical
    return cats[index] if 0 <= index < len(cats) else MUTED


def hex_to_rgba(hex_color: str, alpha: float) -> str:
    """'#rrggbb' -> 'rgba(r,g,b,a)'."""
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"


def verdict_badge_text(verdict: Verdict | None) -> str:
    """'✓ PASS', '! MARGINAL', '✕ FAIL', '– 스펙 없음'."""
    return f"{VERDICT_SYMBOLS[verdict]} {VERDICT_LABELS[verdict]}"


def verdict_md(verdict: Verdict | None, text: str | None = None) -> str:
    """Streamlit markdown with theme-aware color: ':green[✓ PASS]'. Symbol always included."""
    body = text if text is not None else verdict_badge_text(verdict)
    return f":{VERDICT_MD_COLORS[verdict]}[{body}]"
