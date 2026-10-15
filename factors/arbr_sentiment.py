"""ARBR 人气意愿指标因子（arbr_sentiment, f0099a）。

对应灵感 i20261015-009（雪球实战）：ARBR 人气意愿指标，散户扎堆的人气指标常领先见顶，
情绪冰点（低 ARBR）反转 → 未来收益更高（反向）。属技术情绪类，方向为反向。

实现（纯 OHLCV，逐资产截至 t）：
    AR = Σ_N (H-O) / Σ_N (O-L) * 100          # 人气指标（买卖意愿对比）
    BR = Σ_N (H-YC) / Σ_N (YC-L) * 100        # 意愿指标（多空对抗，YC=昨收）
    ARBR = (AR + BR) / 2
    N = 26（经典参数）
PIT 安全：仅用 OHLCV；不引用 market_cap 快照列。市值暴露由 harness 中性化剥离。
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from factors.interface import register_factor

N = 26


@register_factor
class ArbrSentimentFactor:
    name = "arbr_sentiment"
    fcode = "f0099a"
    universe_hint = None

    def compute_panel(self, panel, ctx=None) -> pd.DataFrame:
        asset = panel.index.get_level_values("asset")
        close = panel["close"].astype(float)
        open_ = panel["open"].astype(float)
        high = panel["high"].astype(float)
        low = panel["low"].astype(float)
        prev_close = close.groupby(asset).shift(1)

        ar_up = (high - open_).clip(lower=0.0)
        ar_dn = (open_ - low).clip(lower=0.0)
        br_up = (high - prev_close).clip(lower=0.0)
        br_dn = (prev_close - low).clip(lower=0.0)

        def rsum(s):
            return s.groupby(asset).transform(lambda x: x.rolling(N).sum())

        ar = rsum(ar_up) / rsum(ar_dn).replace(0, np.nan)
        br = rsum(br_up) / rsum(br_dn).replace(0, np.nan)
        arbr = ((ar + br) / 2.0) * 100.0

        mat = arbr.unstack("asset")
        if mat.index.name != "date":
            mat = mat.T
        return mat

    def compute(self, panel, as_of_date, ctx=None) -> pd.Series:
        full = self.compute_panel(panel, ctx)
        t = pd.Timestamp(as_of_date)
        if t in full.index:
            return full.loc[t].dropna().rename(self.name)
        return pd.Series(dtype=float, name=self.name)


register_factor(ArbrSentimentFactor())
