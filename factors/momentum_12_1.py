"""12-1 动量因子（momentum_12_1）。

对应灵感池 i20260820-039：12 个月剔除最近 1 个月的累计收益（12-1 动量）越高 →
未来 20 日收益越高，且该正向关系显著。

经典 Jegadeesh-Titman 动量，跳过最近 1 个月以规避 1 月短期反转污染。
实现（纯 close，逐资产截至 t）：
    mom_12_1 = close[t-21] / close[t-252] - 1
（t-21 ≈ 1 个月前锚点，t-252 ≈ 12 个月前；用 t-21 而非 t-1 即"剔除最近 1 月"，
与 f0006a 的 20 日动量形成不同持有期、不同前视剔除窗口的互补视角。）

PIT 安全：compute 仅消费 t 及之前的 close，切片只含 ≤t 行；
不引用未来行、不引用 market_cap 快照列（市值暴露由 harness 用 pit_float_mcap 剥离）。
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from factors.interface import register_factor, slice_panel_to_date


def _close_at_lag(sub: pd.DataFrame, as_of, lag: int):
    """返回 as_of 往前数第 lag 个交易日的 close 序列（lag=1 → 前一交易日）。"""
    dates = sorted(d for d in sub.index.get_level_values("date").unique() if d <= as_of)
    if len(dates) <= lag:
        return None
    target = dates[-1 - lag]
    try:
        return sub.xs(target, level="date")["close"]
    except KeyError:
        return None


class Momentum121Factor:
    """12-1 动量：close[t-21] / close[t-252] - 1。正值 = 过去约 11 个月上涨的票。"""

    name = "momentum_12_1"
    fcode = "f0035a"  # 交付包代号（对齐 deliverables/factors/_REGISTRY.csv）
    universe_hint = "hs300"

    def compute(self, panel: pd.DataFrame, as_of_date, ctx=None) -> pd.Series:
        as_of = pd.Timestamp(as_of_date)
        sub = slice_panel_to_date(panel, as_of)
        try:
            day = sub.xs(as_of, level="date")
        except KeyError:
            return pd.Series(dtype=float, name=self.name)

        num = _close_at_lag(sub, as_of, 21)   # close[t-21]（约 1 个月前）
        den = _close_at_lag(sub, as_of, 252)  # close[t-252]（约 12 个月前）
        if num is None or den is None:
            return pd.Series(np.nan, index=day.index, name=self.name)

        mom = num.reindex(day.index) / den.reindex(day.index) - 1.0
        return mom.rename(self.name)


register_factor(Momentum121Factor())
