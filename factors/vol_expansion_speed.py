"""波动率扩张速度因子（vol_expansion_speed）。

对应灵感池 i20260827-005：个股近 5 日波动率 / 前 20 日波动率的比值（波动率扩张速度）
截面越高，反映波动率在短期快速放大（恐慌/炒作升温），未来 20 日收益越低。

实现：逐资产日收益 ret=pct_change(1)；vol_short=ret 5 日滚动 std，vol_long=ret 20 日
滚动 std；ratio = vol_short / vol_long。全部算子向后看，无前视。
不读 market_cap 快照列，市值暴露由 harness 用 pit_float_mcap 剥离。
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from factors.interface import register_factor

SHORT = 5
LONG = 20


@register_factor
class VolExpansionSpeedFactor:
    name = "vol_expansion_speed"
    fcode = "f0032a"
    universe_hint = None

    def compute(self, panel: pd.DataFrame, as_of_date, ctx=None) -> pd.Series:
        t = pd.Timestamp(as_of_date)
        sub = panel.sort_index()
        close = sub["close"]
        ret = close.groupby(level="asset").transform(lambda s: s.pct_change(1))
        vol_short = ret.groupby(level="asset").transform(
            lambda s: s.rolling(SHORT, min_periods=SHORT).std())
        vol_long = ret.groupby(level="asset").transform(
            lambda s: s.rolling(LONG, min_periods=LONG).std())
        ratio = vol_short / vol_long
        return ratio.xs(t, level="date").dropna()


register_factor(VolExpansionSpeedFactor())
