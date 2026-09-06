"""60 日反转因子（reversal_60d）。

对应灵感池 i20260806-008：过去 60 日收益最低十分位的股票（近期弱势）相对全市场存在反转修复机会。
这里交付为纯粹的长窗口价格反转：factor = −(close[t]/close[t-60] − 1)，近期跌幅越大，反转预期越强。

实现（纯 close，向后看）：
    cum60 = close[t] / close[t-60] - 1
    factor = -cum60
正值 = 过去 60 日下跌较多的票（反转候选）。

PIT 安全：仅用 close；不读 market_cap 快照列。
C 级 groupby.shift；compute_panel 一次性向量化全序列（O(N)）。
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from factors.interface import register_factor

W = 60


class Reversal60dFactor:
    """60 日价格反转：−(close[t]/close[t-60] − 1)。"""

    name = "reversal_60d"
    fcode = "f0049a"
    universe_hint = None

    def _full(self, panel: pd.DataFrame) -> pd.Series:
        sub = panel.sort_index()
        close = sub["close"]
        close_lag = close.groupby(level="asset").shift(W)
        with np.errstate(divide="ignore", invalid="ignore"):
            cum = close / close_lag - 1.0
        return -cum

    def compute(self, panel: pd.DataFrame, as_of_date, ctx=None) -> pd.Series:
        t = pd.Timestamp(as_of_date)
        return self._full(panel).xs(t, level="date").dropna().rename(self.name)

    def compute_panel(self, panel: pd.DataFrame) -> pd.DataFrame:
        return self._full(panel).unstack(level="asset")


register_factor(Reversal60dFactor())
