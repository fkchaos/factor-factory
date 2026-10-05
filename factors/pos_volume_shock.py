"""正面成交量冲击因子（pos_volume_shock）。

对应灵感池 i20261005-002：Wang (2026) 发现近 1 个月"正面成交量冲击"（异常放量强度）
截面越高的股票未来 1 个月收益越高（high volume return premium），且受货币政策状态调节。

A 股落地口径（纯 OHLCV，无前视）：
    1) ret      = close 逐资产 pct_change(1)
    2) vol_ma   = 逐资产 20 日成交量滚动均值（基准量）
    3) vol_ratio= volume / vol_ma                       （当日放量程度，异常放量>1）
    4) excess   = (ret > 0) ? (vol_ratio − 1) : 0       （只在上涨日用放量强度）
    5) shock    = 逐资产 20 日滚动均值(excess)            （近 1 月正面成交量冲击强度）

经济含义：放量集中在上涨日的股票，反映买盘主动、筹码向上换手，未来短期收益更高。
与量价背离(f0055a)/流动性改善(f0033a)/低位放量(f0041a) 视角不同——本因子专刻画
"上涨日的放量强度"而非量价关系或低位异常。

PIT 安全：仅用 close / volume（均为 t 日及之前可观测量）；不引用 market_cap 快照列
（市值暴露由 harness 用 pit_float_mcap 剥离）。
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from factors.interface import register_factor

W_VOL = 20  # 基准量窗口 + 冲击滚动窗口（≈1 个月交易日）


@register_factor
class PosVolumeShockFactor:
    """正面成交量冲击：近 20 日上涨日异常放量强度。"""

    name = "pos_volume_shock"
    fcode = "f0089a"
    universe_hint = None

    def compute(self, panel: pd.DataFrame, as_of_date, ctx=None) -> pd.Series:
        t = pd.Timestamp(as_of_date)
        sub = panel.sort_index()
        g = sub.groupby(level="asset")
        ret = sub["close"].pct_change()
        vol = sub["volume"]
        vol_ma = g["volume"].transform(lambda s: s.rolling(W_VOL, min_periods=10).mean())
        with np.errstate(divide="ignore", invalid="ignore"):
            vol_ratio = (vol / vol_ma).fillna(1.0)
        excess = (ret > 0).astype(float) * (vol_ratio - 1.0)
        shock = excess.groupby(level="asset").transform(
            lambda s: s.rolling(W_VOL, min_periods=10).mean())
        return shock.xs(t, level="date").dropna().rename(self.name)

    def compute_panel(self, panel: pd.DataFrame) -> pd.DataFrame:
        """向量化全序列（date×asset），与 compute 同口径；滚动均为因果算子。"""
        sub = panel.sort_index()
        g = sub.groupby(level="asset")
        ret = sub["close"].pct_change()
        vol = sub["volume"]
        vol_ma = g["volume"].transform(lambda s: s.rolling(W_VOL, min_periods=10).mean())
        with np.errstate(divide="ignore", invalid="ignore"):
            vol_ratio = (vol / vol_ma).fillna(1.0)
        excess = (ret > 0).astype(float) * (vol_ratio - 1.0)
        shock = excess.groupby(level="asset").transform(
            lambda s: s.rolling(W_VOL, min_periods=10).mean())
        return shock.unstack(level="asset")  # date × asset


register_factor(PosVolumeShockFactor())
