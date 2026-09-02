"""5 日平均换手率因子（avg_turnover_5d）。

对应灵感池 i20260820-013（P1）：取每只股票截至 t 的**前 5 个交易日换手率均值**，
刻画极短期交易活跃度。迅投口径 IC=0.996 / IR=0.12（极高 IC 但一致性弱），列为 P1。

PIT 安全：compute 仅消费 t 及之前数据，rolling 只向后看；turnover 为 t 日可观测量，
不引用 close（前复权含未来分红）/ market_cap 快照列。市值暴露由 harness 用 pit_float_mcap 剥离。
"""
from __future__ import annotations
import pandas as pd
import numpy as np
from factors.interface import register_factor

WINDOW = 5


@register_factor
class AvgTurnover5dFactor:
    name = "avg_turnover_5d"
    fcode = "f0017a"
    universe_hint = "hs300"

    def compute(self, panel: pd.DataFrame, as_of_date, ctx=None) -> pd.Series:
        t = pd.Timestamp(as_of_date)
        sub = panel.sort_index()
        g = sub.groupby(level="asset")["turnover"]
        avg = g.transform(lambda s: s.rolling(WINDOW, min_periods=WINDOW).mean())
        return avg.xs(t, level="date").dropna()


register_factor(AvgTurnover5dFactor())
