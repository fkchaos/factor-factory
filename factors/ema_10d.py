"""10 日指数移动均线因子（ema_10d）。

对应灵感池 i20260820-027（P1）：取截至 t 的 10 日 EMA(close)。
迅投口径 IC=0.572 / IR=0.665（IR 最高，一致性好）。
PIT 安全：ewm(span=10, adjust=False) 对每个 asset 历史独立向后看；close 为已发生价格。
"""
from __future__ import annotations
import pandas as pd
import numpy as np
from factors.interface import register_factor

SPAN = 10


@register_factor
class Ema10dFactor:
    name = "ema_10d"
    fcode = "f0019a"
    universe_hint = "hs300"

    def compute(self, panel: pd.DataFrame, as_of_date, ctx=None) -> pd.Series:
        t = pd.Timestamp(as_of_date)
        sub = panel.sort_index()
        g = sub.groupby(level="asset")["close"]
        ema = g.transform(lambda s: s.ewm(span=SPAN, adjust=False).mean())
        return ema.xs(t, level="date").dropna()


register_factor(Ema10dFactor())
