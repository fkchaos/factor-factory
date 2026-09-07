"""特质收益下尾 beta 因子（idio_tail_beta）。

对应灵感池 i20260806-002：每日先对个股收益剔除市场因子得特质收益，取全截面 10%
分位数构成"下尾序列"；个股对该序列日度变化的 250 日滚动 beta 越高，未来 20 日
收益越高（高 beta 组减低 beta 组月均超额 > 0）。即个股对市场-wide 特质崩 tail 越敏感，
越被定价为高风险、要求更高补偿。

实现（纯 close，向后看）：
    ret   = close 逐资产 pct_change(1)
    mkt   = 每日跨资产等权平均收益
    idio  = ret - mkt                       （特质收益）
    tail_ts[d] = quantile(idio[d], 0.1)    （市场-wide 特质下尾时间序列）
    beta_i = rolling250 Cov(idio_change_i, tail_change) / Var(tail_change)
    factor = beta_i
用 pandas 向量化 rolling.cov / var（C 级实现，O(N·A) 高效）。

PIT 安全：仅用 close；不读 market_cap 快照列（市值暴露由 harness 用 pit_float_mcap 剥离）。
compute_panel 一次性向量化全序列。
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from factors.interface import register_factor

W = 250
Q = 0.1


class IdioTailBetaFactor:
    """特质收益下尾 beta：个股 idio 对市场-wide 特质下尾变化的 250 日滚动 beta。"""

    name = "idio_tail_beta"
    fcode = "f0051a"
    universe_hint = None

    def _full(self, panel: pd.DataFrame) -> pd.Series:
        sub = panel.sort_index()
        ret = sub["close"].groupby(level="asset").pct_change()
        mkt = ret.groupby(level="date").mean()
        mkt_aligned = pd.Series(
            ret.index.get_level_values("date").map(mkt), index=ret.index)
        idio = ret - mkt_aligned

        tail_ts = idio.groupby(level="date").quantile(Q)        # date -> 下尾值
        idio_change = idio.groupby(level="asset").diff()

        M = idio_change.unstack(level="asset")                  # T x A
        xser = tail_ts.reindex(M.index)                         # T
        cov = M.rolling(W).cov(xser)                            # T x A
        var = xser.rolling(W).var()                             # T
        beta = cov.div(var, axis=0)
        return beta.stack().reindex(idio_change.index)

    def compute(self, panel: pd.DataFrame, as_of_date, ctx=None) -> pd.Series:
        t = pd.Timestamp(as_of_date)
        return self._full(panel).xs(t, level="date").dropna().rename(self.name)

    def compute_panel(self, panel: pd.DataFrame) -> pd.DataFrame:
        return self._full(panel).unstack(level="asset")


register_factor(IdioTailBetaFactor())
