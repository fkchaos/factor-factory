"""隔夜-日内分解因子（overnight_intraday_decomp）。

对应灵感池 i20260805-003：过去 20 日累计隔夜收益高、累计日内收益低的股票 → 未来 20 日收益更高
（相对两段和的相对结构，而非 f0001a 的反转方向）。隔夜 = 盘前信息定价，日内 = 盘中博弈。

实现（纯 open/close，向后看）：
    overnight_cum = Σ_{20d}(open/prev_close - 1)；intraday_cum = Σ_{20d}(close/open - 1)
    factor = overnight_cum - intraday_cum
正值 = 收益更多来自隔夜跳空而非盘中追涨，信息效率更高。

PIT 安全：仅用 open/close；不读 market_cap 快照列。
C 级 groupby.rolling；compute_panel 一次性向量化全序列（O(N)）。
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from factors.interface import register_factor

W = 20


class OvernightIntradayDecompFactor:
    """隔夜-日内分解：20 日隔夜累计 − 20 日日内累计。"""

    name = "overnight_intraday_decomp"
    fcode = "f0045a"
    universe_hint = None

    def _full(self, panel: pd.DataFrame) -> pd.Series:
        sub = panel.sort_index()
        close = sub["close"]
        prev_close = close.groupby(level="asset").shift(1)
        with np.errstate(divide="ignore", invalid="ignore"):
            overnight = sub["open"] / prev_close - 1.0
            intraday = close / sub["open"] - 1.0
        o_cum = (overnight.groupby(level="asset").rolling(W, min_periods=W).sum()
                 .reset_index(level=0, drop=True))
        i_cum = (intraday.groupby(level="asset").rolling(W, min_periods=W).sum()
                 .reset_index(level=0, drop=True))
        return o_cum - i_cum

    def compute(self, panel: pd.DataFrame, as_of_date, ctx=None) -> pd.Series:
        t = pd.Timestamp(as_of_date)
        return self._full(panel).xs(t, level="date").dropna().rename(self.name)

    def compute_panel(self, panel: pd.DataFrame) -> pd.DataFrame:
        return self._full(panel).unstack(level="asset")


register_factor(OvernightIntradayDecompFactor())
