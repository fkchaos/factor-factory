"""动量向上 + 缩量回调因子（momentum_volume_shrink_pullback）。

对应灵感池 i20260910-011：个股 20 日动量向上（close/close[20]-1>0）且出现单日缩量
（成交量 < 20 日均量×0.7）回调、收盘仍在 20 日线上 → 未来 20 日收益越高
（趋势惯性中健康的缩量回踩，后续续涨概率大）。

实现（纯 close / volume，逐资产截至 t）：
    - mom20 = close / close.shift(20) - 1
    - vol_shrink = volume < 0.7 × MA20(volume)
    - above_ma20 = close > MA20(close)
    因子值 = mom20.clip(lower=0) × vol_shrink × above_ma20
    （仅当"缩量 + 站上20日线 + 动量为正"时给分，分值为动量强度；其余为 0）

PIT 安全：仅用 close / volume（t 日及之前可观测量），不读 market_cap 快照列，
市值暴露由 harness 用 data/pit.pit_float_mcap 剥离。纯函数（无实例状态）。
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from factors.interface import register_factor

W = 20
SHRINK = 0.7


@register_factor
class MomentumVolumeShrinkPullbackFactor:
    name = "momentum_volume_shrink_pullback"
    fcode = "f0081a"
    universe_hint = None

    def compute(self, panel: pd.DataFrame, as_of_date, ctx=None) -> pd.Series:
        t = pd.Timestamp(as_of_date)
        sub = panel.sort_index()  # 已切片到 t

        df = pd.DataFrame(index=sub.index)
        df["close"] = sub["close"].astype(float)
        df["volume"] = sub["volume"].astype(float)

        g = df.groupby(level="asset")
        ma20_c = g["close"].transform(lambda s: s.rolling(W).mean())
        ma20_v = g["volume"].transform(lambda s: s.rolling(W).mean())
        mom20 = g["close"].transform(lambda s: s / s.shift(W) - 1.0)

        vol_shrink = df["volume"] < (SHRINK * ma20_v)
        above_ma20 = df["close"] > ma20_c

        f = mom20.clip(lower=0.0) * vol_shrink.astype(float) * above_ma20.astype(float)
        return f.xs(t, level="date").dropna().rename(self.name)


register_factor(MomentumVolumeShrinkPullbackFactor())
