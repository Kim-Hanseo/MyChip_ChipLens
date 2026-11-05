"""suggest_sim_mapping rules: id/label tokens, role names, uniqueness, UNUSED, column order."""

from __future__ import annotations

from core.adapters import suggest_sim_mapping
from core.models import ChannelInfo, ChannelMap, ColumnInfo


def _col(name: str, si_unit: str | None = "V", numeric: bool = True) -> ColumnInfo:
    return ColumnInfo(name=name, header=name, base_name=name, si_unit=si_unit, numeric=numeric)


def _cmap(*items: tuple[str, str, str | None]) -> ChannelMap:
    return ChannelMap(channels=[ChannelInfo(channel_id=c, role=r, label=lbl) for c, r, lbl in items])


STD = _cmap(("CH1", "CLK", None), ("CH2", "IN", None), ("CH3", "OUT", None), ("CH4", "IDD", None))


def test_roles_map_clk_in_out_idd():
    cols = [_col("time", None), _col("v(clk)"), _col("v(in)"), _col("v(out)"), _col("i(idd)", "A")]
    assert suggest_sim_mapping(cols, STD) == {"v(clk)": "CH1", "v(in)": "CH2", "v(out)": "CH3", "i(idd)": "CH4"}


def test_time_and_non_numeric_columns_are_not_keys():
    cols = [_col("Time", "s"), _col("t", None), _col("note", None, numeric=False), _col("v(out)")]
    assert suggest_sim_mapping(cols, STD) == {"v(out)": "CH3"}


def test_channel_id_and_label_tokens_win_over_roles():
    cmap = _cmap(("CH1", "CLK", None), ("CH2", "OUT", "WL0"), ("CH3", "OUT", "WL1"))
    cols = [_col("v(wl1)"), _col("v(wl0)"), _col("v(out)"), _col("ch1_probe")]
    # two OUT channels -> "out" is ambiguous -> None
    assert suggest_sim_mapping(cols, cmap) == {"v(wl1)": "CH3", "v(wl0)": "CH2", "v(out)": None, "ch1_probe": "CH1"}


def test_each_channel_assigned_once_earlier_column_wins():
    cols = [_col("v(clk)"), _col("v(clk_buf)"), _col("v(xclk)")]
    assert suggest_sim_mapping(cols, STD) == {"v(clk)": "CH1", "v(clk_buf)": None, "v(xclk)": None}


def test_unused_channels_never_suggested():
    cmap = _cmap(("CH1", "UNUSED", None), ("CH2", "OUT", None))
    assert suggest_sim_mapping([_col("ch1"), _col("v(out)")], cmap) == {"ch1": None, "v(out)": "CH2"}


def test_supply_current_maps_to_idd_and_multi_token_label():
    cmap = _cmap(("CH1", "VDD", None), ("CH2", "IDD", None), ("CH3", "OUT", "Data Out"))
    cols = [_col("i(vdd)", "A"), _col("v(vdd)"), _col("v(data_out)")]
    assert suggest_sim_mapping(cols, cmap) == {"i(vdd)": "CH2", "v(vdd)": "CH1", "v(data_out)": "CH3"}
