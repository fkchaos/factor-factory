"""120 日指数移动均线因子（ema_120d）。

对应灵感池 i20260820-025（P1）：取截至 t 的 120 日 EMA(close)。
迅投口径 IC=0.694 / IR=0.271。
PIT 安全：ewm(span=120, adjust=False) 对每个 asset 历史独立向后看；close 为已发生价格。
"""
from __future__ import annotations
import pandas as pd
import numpy as np
from factors.interface import register_factor

SPAN = 120


@register_factor
class Ema120dFactor:
    name = "ema_120d"
    fcode = "f0021a"
    universe_hint = "hs300"

    def compute(self, panel: pd.DataFrame, as_of_date, ctx=None) -> pd.Series:
        t = pd.Timestamp(as_of_date)
        sub = panel.sort_index()
        g = sub.groupby(level="asset")["close"]
        ema = g.transform(lambda s: s.ewm(span=SPAN, adjust=False).mean())
        return ema.xs(t, level="date").dropna()


register_factor(Ema120dFactor())
