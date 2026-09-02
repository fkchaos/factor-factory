"""5 日简单移动均线因子（ma_5d）。

对应灵感池 i20260820-023（P1）：取截至 t 的 5 日 MA(close)。
迅投口径 IC=0.759 / IR=0.311。
PIT 安全：rolling(5) 只向后看；close 为已发生价格。
"""
from __future__ import annotations
import pandas as pd
import numpy as np
from factors.interface import register_factor

WINDOW = 5


@register_factor
class Ma5dFactor:
    name = "ma_5d"
    fcode = "f0022a"
    universe_hint = "hs300"

    def compute(self, panel: pd.DataFrame, as_of_date, ctx=None) -> pd.Series:
        t = pd.Timestamp(as_of_date)
        sub = panel.sort_index()
        g = sub.groupby(level="asset")["close"]
        ma = g.transform(lambda s: s.rolling(WINDOW, min_periods=WINDOW).mean())
        return ma.xs(t, level="date").dropna()


register_factor(Ma5dFactor())
