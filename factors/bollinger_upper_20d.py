"""布林带上轨位置因子（bollinger_upper_20d）。

对应灵感池 i20260820-018（P1）：取截至 t 的 20 日布林带，因子值定义为
价格相对布林带中轨的标准化偏离 z = (close - mid) / (2·std)（带符号，正=接近/突破上轨）。
迅投口径 IC=0.797 / IR=0.393。
PIT 安全：rolling(20) 只向后看；close 为已发生价格；不引用未来波动。
"""
from __future__ import annotations
import pandas as pd
import numpy as np
from factors.interface import register_factor

WINDOW = 20
K = 2.0


@register_factor
class BollingerUpper20dFactor:
    name = "bollinger_upper_20d"
    fcode = "f0025a"
    universe_hint = "hs300"

    def compute(self, panel: pd.DataFrame, as_of_date, ctx=None) -> pd.Series:
        t = pd.Timestamp(as_of_date)
        sub = panel.sort_index()

        def _boll(s: pd.Series) -> pd.Series:
            mid = s.rolling(WINDOW, min_periods=WINDOW).mean()
            std = s.rolling(WINDOW, min_periods=WINDOW).std()
            return (s - mid) / (2.0 * std)

        g = sub.groupby(level="asset")["close"]
        z = g.transform(_boll)
        return z.xs(t, level="date").dropna()


register_factor(BollingerUpper20dFactor())
