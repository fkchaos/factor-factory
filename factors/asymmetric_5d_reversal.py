"""非对称 5 日反转因子（asymmetric_5d_reversal）。

对应灵感池 i20260805-007：过去 5 日收益为负的股票，其反转强度（未来 5 日 vs 过去
5 日收益负相关斜率）大于收益为正的股票 → 非对称 5 日反转多空更高。

这里交付为纯粹的短窗口价格反转：factor = −(close[t]/close[t-5] − 1)。
"非对称"是经验性质（下跌股反转更强，由 harness 的 RankIC/分层回测实证），
因子本身是标准 5 日反转，与 f0049a(60日) / f0029a(连涨占比) 窗口与构造均不同。

实现（纯 close，向后看）：
    r5 = close[t]/close[t-5] - 1
    factor = -r5
正值 = 过去 5 日下跌较多的票（短期反转候选）。

PIT 安全：仅用 close；不读 market_cap 快照列（市值暴露由 harness 用 pit_float_mcap 剥离）。
C 级 groupby.shift；compute_panel 一次性向量化全序列（O(N)）。
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from factors.interface import register_factor

W = 5


class Asymmetric5dReversalFactor:
    """非对称 5 日价格反转：−(close[t]/close[t-5] − 1)。"""

    name = "asymmetric_5d_reversal"
    fcode = "f0050a"
    universe_hint = None

    def _full(self, panel: pd.DataFrame) -> pd.Series:
        sub = panel.sort_index()
        close = sub["close"]
        close_lag = close.groupby(level="asset").shift(W)
        with np.errstate(divide="ignore", invalid="ignore"):
            r5 = close / close_lag - 1.0
        return -r5

    def compute(self, panel: pd.DataFrame, as_of_date, ctx=None) -> pd.Series:
        t = pd.Timestamp(as_of_date)
        return self._full(panel).xs(t, level="date").dropna().rename(self.name)

    def compute_panel(self, panel: pd.DataFrame) -> pd.DataFrame:
        return self._full(panel).unstack(level="asset")


register_factor(Asymmetric5dReversalFactor())
