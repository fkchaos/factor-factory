"""20 日资金流量因子（money_flow_ma_20d）。

对应灵感池 i20260820-016（P1）：资金流量 = 典型价 × 成交量，取截至 t 的 20 日均值。
典型价 = (high+low+close)/3，用面板已有 high/low/close/volume 现算（PIT 安全，全为 t 及之前可观测量）。
迅投口径 IC=0.837 / IR=0.109。
PIT 安全：rolling(20) 只向后看；high/low/close/volume 均为 t 日已发生数据。
"""
from __future__ import annotations
import pandas as pd
import numpy as np
from factors.interface import register_factor

WINDOW = 20


@register_factor
class MoneyFlowMa20dFactor:
    name = "money_flow_ma_20d"
    fcode = "f0024a"
    universe_hint = "hs300"

    def compute(self, panel: pd.DataFrame, as_of_date, ctx=None) -> pd.Series:
        t = pd.Timestamp(as_of_date)
        sub = panel.sort_index().copy()
        tp = (sub["high"] + sub["low"] + sub["close"]) / 3.0
        sub["_mf"] = tp * sub["volume"]
        g = sub.groupby(level="asset")["_mf"]
        mf_ma = g.transform(lambda s: s.rolling(WINDOW, min_periods=WINDOW).mean())
        return mf_ma.xs(t, level="date").dropna()


register_factor(MoneyFlowMa20dFactor())
