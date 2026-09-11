"""市场 beta（beta_market_60d）· f0083a。

对应灵感池 i20260910-003：个股对宽基（池内等权市场收益代理）的 60 日 beta 截面越低
→ 未来 20 日收益越高（Betting-Against-Beta 异象）。故因子值取 *负号* beta：
值越大 = beta 越低 = 预期未来收益越高（方向已对齐"因子值大→收益高"的内部惯例）。

实现（纯 close，向后看，无前视）：
    ret_i = close 逐资产 pct_change(1)
    mkt   = 每日跨资产等权平均收益（池内等权代理宽基，与 f0047a/f0058a 同口径）
    beta  = cov(ret_i, mkt) / var(mkt)，滚动 60 日（min_periods=30）
    factor = -beta

口径红线：仅用 close；不读面板 market_cap 快照列（市值暴露由 harness 用
pit_float_mcap 中性化剥离）。compute_panel 一次性矩阵化（参照 f0058a 的 rolling
cov/var 实现，避免逐资产 groupby 错位）。
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from factors.interface import register_factor

BETA_WIN = 60  # beta 滚动窗口（交易日）


class BetaMarket60dFactor:
    """60 日市场 beta（BAB 方向：取负号）。"""

    name = "beta_market_60d"
    fcode = "f0083a"
    universe_hint = None

    def _full(self, panel: pd.DataFrame) -> pd.Series:
        sub = panel.sort_index()
        close = sub["close"]
        R = close.unstack(level="asset").pct_change(fill_method=None)  # T x A 个股日收益
        mkt = R.mean(axis=1, skipna=True)                              # 等权市场日收益

        minp = max(20, BETA_WIN // 2)
        mkt_mat = pd.DataFrame(
            np.repeat(mkt.values[:, None], R.shape[1], axis=1),
            index=R.index, columns=R.columns).where(R.notna())
        e_im = (R * mkt_mat).rolling(BETA_WIN, min_periods=minp).mean()
        e_i = R.rolling(BETA_WIN, min_periods=minp).mean()
        e_m = mkt_mat.rolling(BETA_WIN, min_periods=minp).mean()
        var_m = (mkt_mat ** 2).rolling(BETA_WIN, min_periods=minp).mean() - e_m ** 2
        cov_im = e_im - e_i * e_m
        with np.errstate(divide="ignore", invalid="ignore"):
            beta = cov_im / var_m.where(var_m > 0)

        out = (-beta).replace([np.inf, -np.inf], np.nan)  # BAB：低 beta → 高值
        return out.stack().reindex(close.index)

    def compute(self, panel: pd.DataFrame, as_of_date, ctx=None) -> pd.Series:
        t = pd.Timestamp(as_of_date)
        return self._full(panel).xs(t, level="date").dropna().rename(self.name)

    def compute_panel(self, panel: pd.DataFrame) -> pd.DataFrame:
        return self._full(panel).unstack(level="asset")


register_factor(BetaMarket60dFactor())
