"""Sim column -> measured channel_id suggestion (D3 re-keying default for the mapping UI)."""

from __future__ import annotations

import re

from core.models import ChannelInfo, ChannelMap, ColumnInfo, Role

from .headers import is_time_like

_TOKEN_RE = re.compile(r"[^\W_]+")  # alphanumeric runs (Unicode, so Korean counts)
_ROLE_BY_TOKEN: dict[str, Role] = {r.value.lower(): r for r in Role if r is not Role.UNUSED}
_SUPPLY_TOKENS = frozenset({"vdd", "vcc"})  # i(vdd) = supply current -> IDD channel


def _tokens(text: str) -> list[str]:
    return [t.lower() for t in _TOKEN_RE.findall(text)]


def _contains(tokens: list[str], needle: list[str]) -> bool:
    k = len(needle)
    return k > 0 and any(tokens[i : i + k] == needle for i in range(len(tokens) - k + 1))


def _match_name(tokens: list[str], channels: list[ChannelInfo], taken: set[str]) -> str | None:
    """Rule 1: a token equals a channel_id or label (case-insensitive)."""
    for tok in tokens:
        for ch in channels:
            if ch.channel_id in taken:
                continue
            if tok == ch.channel_id.lower() or (ch.label and tok == ch.label.strip().lower()):
                return ch.channel_id
    for ch in channels:  # multi-token ids / labels, e.g. label "Data Out" vs "v(data_out)"
        if ch.channel_id in taken:
            continue
        for name in (ch.channel_id, ch.label or ""):
            needle = _tokens(name)
            if len(needle) > 1 and _contains(tokens, needle):
                return ch.channel_id
    return None


def _match_role(
    tokens: list[str], col: ColumnInfo, channels: list[ChannelInfo], taken: set[str]
) -> str | None:
    """Rule 2: a token equals a role name and exactly one channel has that role."""
    for tok in tokens:
        role = _ROLE_BY_TOKEN.get(tok)
        if col.si_unit == "A" and tok in _SUPPLY_TOKENS:
            role = Role.IDD
        if role is None:
            continue
        with_role = [ch for ch in channels if ch.role == role]
        if len(with_role) == 1 and with_role[0].channel_id not in taken:
            return with_role[0].channel_id
    return None


def suggest_sim_mapping(sim_columns: list[ColumnInfo], channel_map: ChannelMap) -> dict[str, str | None]:
    """Suggest the measured channel_id for each sim value column (None = no suggestion).

    Keys: numeric, non-time columns in input order. Matching on the base name's alphanumeric
    tokens: (1) token == channel_id or label, (2) token == role name ("v(clk)" -> the single CLK
    channel). Each measured channel is assigned to at most one column (earlier column wins);
    UNUSED channels are never suggested.
    """
    channels = [ch for ch in channel_map.channels if ch.role != Role.UNUSED]
    taken: set[str] = set()
    out: dict[str, str | None] = {}
    for col in sim_columns:
        if not col.numeric or is_time_like(col):
            continue
        tokens = _tokens(col.base_name)
        choice = _match_name(tokens, channels, taken) or _match_role(tokens, col, channels, taken)
        out[col.name] = choice
        if choice is not None:
            taken.add(choice)
    return out
