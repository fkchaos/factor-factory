"""相对市场收益偏离因子（return_deviation_mkt）。

对应灵感池 i20260824-002：个股日收益率相对市场/行业均值的标准化偏离幅度（|r_i − r_mkt| 截面 z）
越高 → 个股独立行情越强。这里取有符号版本 = 个股相对市场的超额收益（相对强度代理），
5 日累计，正值 = 个股持续跑赢市场。

实现（纯 close，向后看）：
    ret = close 逐资产 pct_change(1)
    mkt = 每日跨资产等权平均收益
    dev = ret - mkt（相对市场偏离）
    factor = dev 5 日滚动求和（持续超越强 → 值越大）
行业暴露由 harness 中性化。

PIT 安全：仅用 close；不读 market_cap 快照列。
C 级 groupby.rolling；收益用 groupby.pct_change 防跨资产错位。
compute_panel 一次性向量化全序列（O(N)）。
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from factors.interface import register_factor

WIN = 5


class ReturnDeviationMktFactor:
    """相对市场收益偏离：5 日累计(r_i − r_mkt)。正值 = 持续跑赢。"""

    name = "return_deviation_mkt"
    fcode = "f0047a"
    universe_hint = None

    def _full(self, panel: pd.DataFrame) -> pd.Series:
        sub = panel.sort_index()
        ret = sub["close"].groupby(level="asset").pct_change()
        mkt = ret.groupby(level="date").mean()
        mkt_aligned = pd.Series(
            ret.index.get_level_values("date").map(mkt), index=ret.index)
        dev = ret - mkt_aligned
        return (dev.groupby(level="asset").rolling(WIN, min_periods=WIN).sum()
                .reset_index(level=0, drop=True))

    def compute(self, panel: pd.DataFrame, as_of_date, ctx=None) -> pd.Series:
        t = pd.Timestamp(as_of_date)
        return self._full(panel).xs(t, level="date").dropna().rename(self.name)

    def compute_panel(self, panel: pd.DataFrame) -> pd.DataFrame:
        return self._full(panel).unstack(level="asset")


register_factor(ReturnDeviationMktFactor())
