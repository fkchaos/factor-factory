"""20日 Amihud 非流动性因子（amihud_illiquidity_20d）。

对应灵感池 i20260806-006：Amihud 非流动性 = 日均 |日收益| / 日成交额，衡量"每单位
成交额驱动的价格冲击"。20 日均值越高，流动性越差，未来 20 日收益越低（流动性溢价 /
非流动性补偿异象）。

实现：逐资产 ret=|pct_change(1)|，daily = ret / amount（amount=0 视为 NaN 防除零），
取 20 日滚动均值。全部算子向后看，无前视。
不读 market_cap 快照列，市值暴露由 harness 用 pit_float_mcap 剥离。
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from factors.interface import register_factor

WINDOW = 20


@register_factor
class AmihudIlliquidity20dFactor:
    name = "amihud_illiquidity_20d"
    fcode = "f0031a"
    universe_hint = None

    def compute(self, panel: pd.DataFrame, as_of_date, ctx=None) -> pd.Series:
        t = pd.Timestamp(as_of_date)
        sub = panel.sort_index()
        close = sub["close"]
        amount = sub["amount"]
        ret = close.groupby(level="asset").transform(lambda s: s.pct_change(1))
        daily = (ret.abs() / amount.replace(0, np.nan))
        illiq = daily.groupby(level="asset").transform(
            lambda s: s.rolling(WINDOW, min_periods=WINDOW).mean())
        return illiq.xs(t, level="date").dropna()


register_factor(AmihudIlliquidity20dFactor())
