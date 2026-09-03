"""20日成交量变异系数因子（volume_cv_20d）。

对应灵感池 i20260806-005：个股过去 20 日成交量标准差 / 均值（变异系数）越高，反映
交投不稳定、筹码松动，未来 20 日收益越低（行为金融：放量异动后倾向于回落）。

实现：逐资产 volume 的 20 日滚动 std / mean。全部算子向后看，无前视。
不读 market_cap 快照列，市值暴露由 harness 用 pit_float_mcap 剥离。
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from factors.interface import register_factor

WINDOW = 20


@register_factor
class VolumeCv20dFactor:
    name = "volume_cv_20d"
    fcode = "f0030a"
    universe_hint = None

    def compute(self, panel: pd.DataFrame, as_of_date, ctx=None) -> pd.Series:
        t = pd.Timestamp(as_of_date)
        sub = panel.sort_index()
        vol = sub["volume"]
        cv = vol.groupby(level="asset").transform(
            lambda s: s.rolling(WINDOW, min_periods=WINDOW).std()
            / s.rolling(WINDOW, min_periods=WINDOW).mean())
        return cv.xs(t, level="date").dropna()


register_factor(VolumeCv20dFactor())
