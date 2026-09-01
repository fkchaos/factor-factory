"""近 20 日已实现偏度因子（realized_skew_20d）。

对应灵感池 i20260827-001（P3）：个股近 20 个交易日日收益率的**已实现偏度**
（彩票型 / 右偏）越高，未来收益越低——A 股散户占比高，对"中大奖"型右偏收益
有系统性偏好，导致右偏票被高估、长期跑输（博彩偏好异象 / Lottery-demand anomaly）。

实现：逐资产对过去 WINDOW 个日收益（close 日频 pct_change）滚动计算偏度。
PIT 安全：compute 仅消费 as_of 及之前的 close，rolling 只向后看；不引用
market_cap 快照列，市值暴露由 harness 用 pit_float_mcap 剥离（与 f0011a–f0025a 同纪律）。
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from factors.interface import register_factor

WINDOW = 20


@register_factor
class RealizedSkew20dFactor:
    name = "realized_skew_20d"
    fcode = "f0027a"
    universe_hint = "zz1000"

    def compute(self, panel: pd.DataFrame, as_of_date, ctx=None) -> pd.Series:
        t = pd.Timestamp(as_of_date)
        sub = panel.sort_index()
        # 逐资产日收益 -> 滚动 WINDOW 偏度（含 as_of 当日已知 close，exec_lag 由 harness 负责）
        sk = (
            sub.groupby(level="asset")["close"]
            .transform(lambda s: s.pct_change(1).rolling(WINDOW, min_periods=WINDOW).skew())
        )
        return sk.xs(t, level="date").dropna()


register_factor(RealizedSkew20dFactor())
