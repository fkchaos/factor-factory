"""隔夜跳空-波动扩张价差因子（overnight_gap_volexp_spread）。

对应灵感池 i20260820-035：近 60 日隔夜跳空率的标准化均值 − 近 20 日振幅相对前 20 日振幅的
扩张速度 z。隔夜跳空 = 跳空/恐慌风险，波动扩张 = 炒作/波动放大，二者相减刻画"跳空冲击 − 波动升温"
的净脆弱度。

实现（纯 open/close，向后看）：
    gap = open/prev_close - 1；gap60 = 每资产 60 日均值（时间序列）
    ret = close 逐资产 pct_change；vol_s = 20 日 std，vol_l = 40 日 std；volexp = vol_s/vol_l
    在截面 t 上对 gap60、volexp 各自做 z-score，factor = z(gap60) - z(volexp)
正值 = 隔夜跳空相对波动扩张更突出 → 跳空风险主导。

PIT 安全：仅用 open/close；不读 market_cap 快照列。
C 级 groupby.rolling；收益用 groupby.pct_change 防跨资产错位。
compute_panel 一次性向量化全序列（O(N)），截面 z 在 _full 内按日完成。
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from factors.interface import register_factor

GAP_W = 60
VOL_S = 20
VOL_L = 40


def _z(s: pd.Series) -> pd.Series:
    sd = s.std()
    if sd is None or sd == 0 or np.isnan(sd):
        return pd.Series(0.0, index=s.index)
    return (s - s.mean()) / sd


class OvernightGapVolexpSpreadFactor:
    """隔夜跳空-波动扩张价差：z(60日隔夜均值) − z(波动扩张)。"""

    name = "overnight_gap_volexp_spread"
    fcode = "f0048a"
    universe_hint = None

    def _full(self, panel: pd.DataFrame) -> pd.Series:
        sub = panel.sort_index()
        close = sub["close"]
        prev_close = close.groupby(level="asset").shift(1)
        with np.errstate(divide="ignore", invalid="ignore"):
            gap = sub["open"] / prev_close - 1.0
        gap60 = (gap.groupby(level="asset").rolling(GAP_W, min_periods=GAP_W).mean()
                 .reset_index(level=0, drop=True))
        ret = sub["close"].groupby(level="asset").pct_change()
        vol_s = (ret.groupby(level="asset").rolling(VOL_S, min_periods=VOL_S).std()
                 .reset_index(level=0, drop=True))
        vol_l = (ret.groupby(level="asset").rolling(VOL_L, min_periods=VOL_L).std()
                 .reset_index(level=0, drop=True))
        with np.errstate(divide="ignore", invalid="ignore"):
            volexp = vol_s / vol_l.replace(0.0, np.nan)
        # 截面 z-score（按日）
        g_z = gap60.groupby(level="date").transform(_z)
        v_z = volexp.groupby(level="date").transform(_z)
        return g_z - v_z

    def compute(self, panel: pd.DataFrame, as_of_date, ctx=None) -> pd.Series:
        t = pd.Timestamp(as_of_date)
        return self._full(panel).xs(t, level="date").dropna().rename(self.name)

    def compute_panel(self, panel: pd.DataFrame) -> pd.DataFrame:
        return self._full(panel).unstack(level="asset")


register_factor(OvernightGapVolexpSpreadFactor())
