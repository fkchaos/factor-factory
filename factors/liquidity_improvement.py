"""流动性改善度因子（liquidity_improvement）。

对应灵感池 i20260820-031：控制 20 日动量后，流动性改善度（近 20 日 Amihud 非流动性
/ 前 20 日 Amihud 非流动性）越高，反映流动性在恶化（冲击成本上升），未来收益越低；
比值<1 表示流动性正在改善，属正向信号。本因子直接取该比值（未做动量控制，动量暴露
由 harness 中性化剥离），方向交由 IC 实测。

实现：逐资产 daily=|pct_change(1)|/amount；rec = 20 日滚动均值（截至 t），
prior = 20 日滚动均值再 shift(20)（截至 t-20 的前窗）；ratio = rec / prior。
shift 向后看，无前视。amount=0 视为 NaN 防除零。
不读 market_cap 快照列，市值暴露由 harness 用 pit_float_mcap 剥离。
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from factors.interface import register_factor

WINDOW = 20


@register_factor
class LiquidityImprovementFactor:
    name = "liquidity_improvement"
    fcode = "f0033a"
    universe_hint = None

    def compute(self, panel: pd.DataFrame, as_of_date, ctx=None) -> pd.Series:
        t = pd.Timestamp(as_of_date)
        sub = panel.sort_index()
        close = sub["close"]
        amount = sub["amount"]
        ret = close.groupby(level="asset").transform(lambda s: s.pct_change(1))
        daily = (ret.abs() / amount.replace(0, np.nan))
        rec = daily.groupby(level="asset").transform(
            lambda s: s.rolling(WINDOW, min_periods=WINDOW).mean())
        prior = daily.groupby(level="asset").transform(
            lambda s: s.rolling(WINDOW, min_periods=WINDOW).mean().shift(WINDOW))
        ratio = rec / prior
        return ratio.xs(t, level="date").dropna()


register_factor(LiquidityImprovementFactor())
