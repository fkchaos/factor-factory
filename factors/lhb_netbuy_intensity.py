"""龙虎榜净买入强度因子（lhb_netbuy_intensity, f0095a）。

对应灵感池 i20260818-003（龙虎榜净买入/封单结构）+ i20260806-011（上榜后超额）。
信号：近 20 日历日（上榜日）「龙虎榜净买额 / 流通市值」之和 —— 连续型，捕捉机构/游资持续净买入强度。
PIT 安全：龙虎榜于上榜日收盘后披露；compute 只用 t 及之前事件（预建面板已含此约束），
框架 exec_lag=1 再负责交易滞后期。未被龙虎榜覆盖的股票信号恒 0，排名时被丢弃。
数据：scripts/build_lhb_signals.py 预建 data/moneyflow_cache/lhb_netbuy_20d.parquet（date×asset）。
"""
from __future__ import annotations

import pandas as pd
from pathlib import Path

from factors.interface import register_factor

CACHE = Path("data/moneyflow_cache/lhb_netbuy_20d.parquet")
_CACHE: dict = {}


@register_factor
class LhbNetbuyIntensityFactor:
    name = "lhb_netbuy_intensity"
    fcode = "f0095a"
    universe_hint = "hs300"

    @classmethod
    def _load(cls) -> pd.DataFrame:
        if "netbuy" not in _CACHE:
            _CACHE["netbuy"] = pd.read_parquet(CACHE)
        return _CACHE["netbuy"]

    def compute_panel(self, panel: pd.DataFrame) -> pd.DataFrame:
        sig = self._load()
        dates = sorted(panel.index.get_level_values("date").unique())
        assets = panel.index.get_level_values("asset").unique()
        return sig.reindex(index=dates, columns=assets)

    def compute(self, panel: pd.DataFrame, as_of_date, ctx=None) -> pd.Series:
        sig = self._load()
        t = pd.Timestamp(as_of_date)
        row = sig.loc[t] if t in sig.index else pd.Series(dtype=float, index=sig.columns)
        return row.reindex(panel.index.get_level_values("asset").unique()).dropna()


register_factor(LhbNetbuyIntensityFactor())
