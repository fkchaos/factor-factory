"""量价背离因子（price_volume_divergence）。

对应灵感池 i20260907-007：个股近 N 日价格创新高但成交量未同步放大（量价背离度 =
价格涨幅 z − 成交量涨幅 z）截面越高 → 未来 20 日收益越低（上涨动能衰竭，趋势易转折）。

这里用 20 日价格动量近似"价格创新高"，以量比（当日量/20 日均量）近似"成交量放大"，
二者均做截面 z 后相减得背离度：
    price_mom = close[t]/close[t-N] - 1
    vol_ratio = volume[t] / mean(volume, N) - 1
    pmz = price_mom 截面 z
    vrz = vol_ratio  截面 z
    divergence = pmz - vrz
    factor = -divergence      （价格涨而量未跟涨 → 背离越强 → 未来收益越低）
纯 close + volume，向后看；截面 z 逐日独立计算。

PIT 安全：仅用 close / volume；不读 market_cap 快照列（市值暴露由 harness 用 pit_float_mcap 剥离）。
compute_panel 一次性向量化全序列。
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from factors.interface import register_factor

N = 20


class PriceVolumeDivergenceFactor:
    """量价背离：价格动量 z 减量比 z，取负号。"""

    name = "price_volume_divergence"
    fcode = "f0055a"
    universe_hint = None

    def _full(self, panel: pd.DataFrame) -> pd.Series:
        sub = panel.sort_index()
        close = sub["close"]
        volume = sub["volume"]

        close_lag = close.groupby(level="asset").shift(N)
        with np.errstate(divide="ignore", invalid="ignore"):
            price_mom = close / close_lag - 1.0
        vol_ma = volume.groupby(level="asset").transform(
            lambda s: s.rolling(N).mean())
        vol_ratio = volume / vol_ma - 1.0

        pmz = price_mom.groupby(level="date").transform(
            lambda s: (s - s.mean()) / s.std())
        vrz = vol_ratio.groupby(level="date").transform(
            lambda s: (s - s.mean()) / s.std())
        return -(pmz - vrz)

    def compute(self, panel: pd.DataFrame, as_of_date, ctx=None) -> pd.Series:
        t = pd.Timestamp(as_of_date)
        return self._full(panel).xs(t, level="date").dropna().rename(self.name)

    def compute_panel(self, panel: pd.DataFrame) -> pd.DataFrame:
        return self._full(panel).unstack(level="asset")


register_factor(PriceVolumeDivergenceFactor())
