"""特异度占比因子（idiosyncratic_share）。

对应灵感池 i20260820-037：特异度 = 个股近 60 日日收益对市场 + 行业收益回归的
1 − R²（即特质性波动占比）越高 → 未来 20 日收益越高（公司特有信息处理溢价 /
与系统性波动脱钩的个股更被有效定价）。

实现（纯 close，逐资产截至 t）：
    ret = close.pct_change()
    mkt = 每日跨资产等权平均收益（系统性成分代理）
    对每只股票，trailing W=60 日窗口内 regress ret_i 对 mkt，得 R²
    factor_t = 1 − R²   （特质性占比越高 = 该股票越多收益来自公司自身）
    注：面板无行业列，仅用等权市场收益作系统性代理；行业暴露由 harness 中性化。

PIT 安全：仅用 close；不引用 market_cap 快照列（市值暴露由 harness 剥离）。
纯函数，满足 assert_no_lookahead。
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from factors.interface import register_factor

W = 60


@register_factor
class IdiosyncraticShareFactor:
    name = "idiosyncratic_share"
    fcode = "f0043a"
    universe_hint = None

    def compute(self, panel: pd.DataFrame, as_of_date, ctx=None) -> pd.Series:
        t = pd.Timestamp(as_of_date)
        sub = panel.sort_index()

        rets = sub["close"].pct_change()
        # 系统性代理：每日等权市场收益（与资产无关，仅随日期变化）
        mkt = rets.groupby(level="date").mean()
        mkt_aligned = pd.Series(
            rets.index.get_level_values("date").map(mkt), index=rets.index
        )

        df = pd.DataFrame(index=rets.index)
        df["ra"] = rets
        df["mkt"] = mkt_aligned
        df["ra_mkt"] = df["ra"] * df["mkt"]

        g = df.groupby(level="asset")
        m_ra = g["ra"].transform(lambda s: s.rolling(W).mean())
        m_mkt = g["mkt"].transform(lambda s: s.rolling(W).mean())
        m_ra_mkt = g["ra_mkt"].transform(lambda s: s.rolling(W).mean())
        var_ra = g["ra"].transform(lambda s: s.rolling(W).var())
        var_mkt = g["mkt"].transform(lambda s: s.rolling(W).var())

        cov = m_ra_mkt - m_ra * m_mkt
        with np.errstate(divide="ignore", invalid="ignore"):
            r2 = (cov ** 2) / (var_ra * var_mkt)
        r2 = r2.clip(0.0, 1.0)
        idio = 1.0 - r2

        return idio.xs(t, level="date").dropna().rename(self.name)


register_factor(IdiosyncraticShareFactor())
