"""连涨占比短期反转因子（up_run_reversal）。

对应灵感池 i20260806-009：在过去 63 个交易日中"上涨日占比">60% 的个股（强连涨、
筹码拥挤的多头子样本）内，施加短期反转信号——取过去 5 日收益的负值（recent surge
预期回吐）。子样本外返回 NaN（不持信号）。

实现：逐资产对日收益（close 日频 pct_change）计算 63 日上涨日占比；该占比>0.6 时
因子值 = -pct_change(5)，否则 NaN。全部算子向后看（rolling / pct_change），compute
接收的 panel 已切片到 as_of_date，t 日值不依赖未来行，无前视。
不读 market_cap 快照列，市值暴露由 harness 用 pit_float_mcap 剥离。
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from factors.interface import register_factor

UP_WINDOW = 63
UP_RATIO_TH = 0.60
REV_WINDOW = 5


@register_factor
class UpRunReversalFactor:
    name = "up_run_reversal"
    fcode = "f0029a"
    universe_hint = None

    def compute(self, panel: pd.DataFrame, as_of_date, ctx=None) -> pd.Series:
        t = pd.Timestamp(as_of_date)
        sub = panel.sort_index()
        close = sub["close"]
        ret = close.groupby(level="asset").transform(lambda s: s.pct_change(1))
        up_day = (ret > 0)
        up_ratio = up_day.groupby(level="asset").transform(
            lambda s: s.rolling(UP_WINDOW, min_periods=UP_WINDOW).mean())
        ret5 = close.groupby(level="asset").transform(lambda s: s.pct_change(REV_WINDOW))
        # 子样本内：-近5日收益（反转）；子样本外：NaN
        val = (-ret5).where(up_ratio > UP_RATIO_TH)
        return val.xs(t, level="date").dropna()


register_factor(UpRunReversalFactor())
