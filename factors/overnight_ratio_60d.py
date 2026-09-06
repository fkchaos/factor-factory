"""隔夜收益占比因子（overnight_ratio_60d）。

对应灵感池 i20260805-004：过去 60 日隔夜收益占累计总收益比例越高 → 未来 20 日收益越高；
该比例为负（收益全靠日内）的股票未来偏弱。隔夜收益 = 开盘相对前收的跳空，反映隔夜信息消化。

实现（纯 open/close，逐资产，向后看）：
    overnight_t = open_t / close_{t-1} - 1；total_t = close_t / close_{t-1} - 1
    ratio = Σ_{60d} overnight / Σ_{60d} total
正值 = 个股收益主要由隔夜跳空驱动（信息在盘前释放、收盘未回吐）。

PIT 安全：仅用 open/close；不引用 market_cap 快照列（市值暴露由 harness 用 pit_float_mcap 剥离）。
C 级 groupby.rolling（避免 Python-lambda 逐组开销）；收益用 groupby.shift 防跨资产错位。
compute_panel 一次性向量化算出全序列（O(N)），供 build_deliverable 快路径使用。
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from factors.interface import register_factor

W = 60


class OvernightRatio60dFactor:
    """隔夜收益占比：60 日隔夜累计 / 60 日总累计。正值 = 收益靠隔夜跳空。"""

    name = "overnight_ratio_60d"
    fcode = "f0044a"
    universe_hint = None

    def _full(self, panel: pd.DataFrame) -> pd.Series:
        sub = panel.sort_index()
        close = sub["close"]
        prev_close = close.groupby(level="asset").shift(1)
        with np.errstate(divide="ignore", invalid="ignore"):
            overnight = sub["open"] / prev_close - 1.0
            total = close / prev_close - 1.0
        o_sum = (overnight.groupby(level="asset").rolling(W, min_periods=W).sum()
                 .reset_index(level=0, drop=True))
        t_sum = (total.groupby(level="asset").rolling(W, min_periods=W).sum()
                 .reset_index(level=0, drop=True))
        with np.errstate(divide="ignore", invalid="ignore"):
            ratio = o_sum / t_sum.replace(0.0, np.nan)
        return ratio

    def compute(self, panel: pd.DataFrame, as_of_date, ctx=None) -> pd.Series:
        t = pd.Timestamp(as_of_date)
        return self._full(panel).xs(t, level="date").dropna().rename(self.name)

    def compute_panel(self, panel: pd.DataFrame) -> pd.DataFrame:
        return self._full(panel).unstack(level="asset")


register_factor(OvernightRatio60dFactor())
