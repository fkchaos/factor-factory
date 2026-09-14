"""区间嵌套(inside-day)事件频率因子（inside_day_freq）。

对应灵感池 i20260914-004：个股 近 N 日「当日 OHLC 完全包含于前日区间」(inside bar)
频率 相对随机游走基线(~20%)显著偏离 → 未来 5 日收益呈均值回复（嵌套率异常高→转折→反向）。

实现（纯 OHLC，逐资产截至 t，全部向后看，无前视）：
    is_inside_t = (low_t  >= low_{t-1}) 且 (high_t <= high_{t-1})
    factor_t    = rolling(W).mean(is_inside)        # W=20 日嵌套率

PIT 安全：仅用 open/high/low/close；不引用 market_cap 快照列（市值暴露由 harness 剥离）。
纯函数，满足 assert_no_lookahead。
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from factors.interface import register_factor

W = 20


@register_factor
class InsideDayFreqFactor:
    name = "inside_day_freq"
    fcode = "f0084a"
    universe_hint = None

    def compute(self, panel: pd.DataFrame, as_of_date, ctx=None) -> pd.Series:
        t = pd.Timestamp(as_of_date)
        sub = panel.sort_index()
        prev_low = sub["low"].groupby(level="asset").shift(1)
        prev_high = sub["high"].groupby(level="asset").shift(1)
        is_inside = (prev_low <= sub["low"]) & (prev_high >= sub["high"])
        freq = is_inside.groupby(level="asset").transform(
            lambda s: s.rolling(W, min_periods=W // 2).mean()
        )
        return freq.xs(t, level="date").dropna().rename(self.name)


register_factor(InsideDayFreqFactor())
