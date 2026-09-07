"""双过滤动量因子（dual_filter_momentum）。

对应灵感池 i20260820-034：相对动量（12 月剔除最近 1 月）前 20% 的股票中，同时满足
12 个月绝对收益 > 0 的子样本，未来 20 日收益高于绝对收益 < 0 的子样本；相对+绝对
双过滤组合的 20 日 IC 与分层回测最大回撤优于纯相对动量。

这里交付为连续版双过滤动量：
    mom12_1 = close[t-21] / close[t-252] - 1   （12-1 相对动量）
    abs12   = close[t]   / close[t-252] - 1   （12 个月绝对收益）
    factor  = mom12_1  if abs12 > 0  else -mom12_1
即：长趋势向上（abs12>0）时施加正向动量；长趋势向下时反向惩罚，剥离"下跌中的反弹型
伪动量"。与 f0035a(纯 12-1 动量) 的区别在于叠加了绝对收益方向门控。

实现（纯 close，向后看）。

PIT 安全：仅用 close；不读 market_cap 快照列（市值暴露由 harness 用 pit_float_mcap 剥离）。
C 级 groupby.shift；compute_panel 一次性向量化全序列（O(N)）。
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from factors.interface import register_factor

MOM = 252
SKIP = 21


class DualFilterMomentumFactor:
    """双过滤动量：12-1 相对动量，叠加 12 月绝对收益方向门控。"""

    name = "dual_filter_momentum"
    fcode = "f0052a"
    universe_hint = None

    def _full(self, panel: pd.DataFrame) -> pd.Series:
        sub = panel.sort_index()
        close = sub["close"]
        close_mom = close.groupby(level="asset").shift(SKIP)
        close_base = close.groupby(level="asset").shift(MOM)
        with np.errstate(divide="ignore", invalid="ignore"):
            mom12_1 = close_mom / close_base - 1.0
            abs12 = close / close_base - 1.0
        return mom12_1.where(abs12 > 0, -mom12_1)

    def compute(self, panel: pd.DataFrame, as_of_date, ctx=None) -> pd.Series:
        t = pd.Timestamp(as_of_date)
        return self._full(panel).xs(t, level="date").dropna().rename(self.name)

    def compute_panel(self, panel: pd.DataFrame) -> pd.DataFrame:
        return self._full(panel).unstack(level="asset")


register_factor(DualFilterMomentumFactor())
