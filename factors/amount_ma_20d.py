"""20 日成交金额移动平均因子（amount_ma_20d）。

对应灵感池 i20260820-021（P1）：取截至 t 的 20 日成交额(amount)均值，
刻画中期资金参与规模。迅投口径 IC=0.769 / IR=0.245。
PIT 安全：rolling(20) 只向后看；amount 为 t 日当日成交额（已发生）。
"""
from __future__ import annotations
import pandas as pd
import numpy as np
from factors.interface import register_factor

WINDOW = 20


@register_factor
class AmountMa20dFactor:
    name = "amount_ma_20d"
    universe_hint = "hs300"

    def compute(self, panel: pd.DataFrame, as_of_date, ctx=None) -> pd.Series:
        t = pd.Timestamp(as_of_date)
        sub = panel.sort_index()
        g = sub.groupby(level="asset")["amount"]
        ma = g.transform(lambda s: s.rolling(WINDOW, min_periods=WINDOW).mean())
        return ma.xs(t, level="date").dropna()


register_factor(AmountMa20dFactor())
