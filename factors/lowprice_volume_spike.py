"""低位放量事件因子（lowprice_volume_spike）。

对应灵感池 i20260820-036：低位放量事件（收盘价处于近 60 日价格分位 < 20% 且
当日成交量 / 近 20 日均量显著放大）→ 此类「恐慌抛售后的地量见底」形态，
未来 20 日收益更高（底部放量、下跌动能衰竭）。

实现（纯 close + volume，逐资产截至 t）：
    price_pct = close_t 在 trailing 60 日中的分位排名（0~1）
    vol_ratio = volume_t / mean(volume trailing 20)
    factor_t  = vol_ratio  （仅当 price_pct < 0.2 时赋值，否则 NaN = 非事件日）
    → 事件日赋予其放量强度，非事件日留空，使因子为「纯净事件」信号。

PIT 安全：仅用 close / volume；不引用 market_cap 快照列（市值暴露由 harness 剥离）。
纯函数，满足 assert_no_lookahead。
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from factors.interface import register_factor

WP = 60   # 价格分位窗口
WV = 20   # 成交量均值窗口
THRESH = 0.2


@register_factor
class LowPriceVolumeSpikeFactor:
    name = "lowprice_volume_spike"
    fcode = "f0041a"
    universe_hint = None

    def compute(self, panel: pd.DataFrame, as_of_date, ctx=None) -> pd.Series:
        t = pd.Timestamp(as_of_date)
        sub = panel.sort_index()

        price_pct = sub.groupby(level="asset")["close"].transform(
            lambda s: s.rolling(WP).rank(pct=True)
        )
        vol_mean = sub.groupby(level="asset")["volume"].transform(
            lambda s: s.rolling(WV).mean()
        )
        vol_ratio = sub["volume"] / vol_mean

        factor = vol_ratio.where(price_pct < THRESH)
        return factor.xs(t, level="date").dropna().rename(self.name)


register_factor(LowPriceVolumeSpikeFactor())
