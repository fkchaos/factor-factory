"""触底反弹信号因子（bottom_rebound）。

对应灵感池 i20260903-007：个股定义"触底反弹"事件——收盘价创近 60 日新低后，5 日内
收复 5 日均线（止跌企稳、资金回流）。因子值 = 当前价相对 60 日最低点的反弹幅度
(close/low60 - 1)，仅在"近 5 日曾触及 60 日新低 且 当前价>5 日均线"时赋值，否则 NaN。

实现：全部算子向后看，无前视。touched / low60 / ma5 均在逐资产 transform 内基于同一
单资产序列 s 计算（避免跨索引比较）。
不读 market_cap 快照列，市值暴露由 harness 用 pit_float_mcap 剥离。
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from factors.interface import register_factor

LOW_WINDOW = 60
MA_WINDOW = 5
TOUCH_WINDOW = 5


@register_factor
class BottomReboundFactor:
    name = "bottom_rebound"
    fcode = "f0034a"
    universe_hint = None

    def compute(self, panel: pd.DataFrame, as_of_date, ctx=None) -> pd.Series:
        t = pd.Timestamp(as_of_date)
        sub = panel.sort_index()
        close = sub["close"]
        g = close.groupby(level="asset")

        def _touch(s: pd.Series) -> pd.Series:
            low60 = s.rolling(LOW_WINDOW, min_periods=20).min()
            # 近 5 日最低价曾触及 60 日最低点（容差 0.1%）
            return s.rolling(TOUCH_WINDOW).min() <= low60 * 1.001

        touched = g.transform(_touch)
        ma5 = g.transform(lambda s: s.rolling(MA_WINDOW, min_periods=MA_WINDOW).mean())
        low60 = g.transform(lambda s: s.rolling(LOW_WINDOW, min_periods=20).min())
        recovered = close > ma5
        val = (close / low60 - 1).where(touched & recovered)
        return val.xs(t, level="date").dropna()


register_factor(BottomReboundFactor())
