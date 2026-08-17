"""标准因子动物园基准因子（相关性冗余度基准 · 见 PLAN_DELIVERABLES §3.3）。

用途：交付物的 correlation.csv 需要把内部因子（ivol / overnight_intraday / 组合）
对标到已知标准因子，揭示冗余度。本模块实现 3 个最常见的风格基准：

- momentum（20d 动量）：经典跳过 1 日的动量，close[t-1]/close[t-21] - 1
- reversal（5d 短期反转）：-(close[t-1]/close[t-6] - 1)，做空近期赢家
- size（规模）：log(总市值)，小盘为正（与 Fama-French SMB 同向）

前视防护：所有因子仅用 as_of_date 及之前的数据（close / market_cap），
天然通过 factors.interface.assert_no_lookahead（与内部因子同一套纪律）。
相关性计算时，动物园因子与内部因子在同一 as_of_date 切片下算，保证内部一致。
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from factors.interface import Factor, register_factor, slice_panel_to_date


def _close_at_lag(sub: pd.DataFrame, as_of, lag: int) -> pd.Series | None:
    """返回 as_of 往前数第 lag 个交易日的 close 序列（lag=1 → 前一交易日）。

    交易日历从 sub 中 <= as_of 的唯一日期排序得到；历史不足返回 None。
    """
    dates = sorted(d for d in sub.index.get_level_values("date").unique() if d <= as_of)
    if len(dates) <= lag:
        return None
    target = dates[-1 - lag]
    try:
        return sub.xs(target, level="date")["close"]
    except KeyError:
        return None


class Momentum20Factor:
    """20 交易日动量（跳过最近 1 日，规避 1 日微观结构污染）。

    信号 = close[t-1] / close[t-21] - 1。正值=过去 20 日上涨的票（动量赢家）。
    """

    name = "momentum_20"

    def compute(self, panel: pd.DataFrame, as_of_date, ctx=None) -> pd.Series:
        as_of = pd.Timestamp(as_of_date)
        sub = slice_panel_to_date(panel, as_of)
        try:
            day = sub.xs(as_of, level="date")
        except KeyError:
            return pd.Series(dtype=float, name=self.name)

        num = _close_at_lag(sub, as_of, 1)   # close[t-1]
        den = _close_at_lag(sub, as_of, 21) # close[t-21]
        if num is None or den is None:
            return pd.Series(np.nan, index=day.index, name=self.name)

        mom = num.reindex(day.index) / den.reindex(day.index) - 1.0
        return mom.rename(self.name)


class Reversal5Factor:
    """5 交易日短期反转（做空近期赢家）。

    信号 = -(close[t-1] / close[t-6] - 1)。正值=过去 5 日下跌的票（预期反转回升）。
    与 momentum 负相关，是短期反转风格的代表。
    """

    name = "reversal_5"

    def compute(self, panel: pd.DataFrame, as_of_date, ctx=None) -> pd.Series:
        as_of = pd.Timestamp(as_of_date)
        sub = slice_panel_to_date(panel, as_of)
        try:
            day = sub.xs(as_of, level="date")
        except KeyError:
            return pd.Series(dtype=float, name=self.name)

        num = _close_at_lag(sub, as_of, 1)  # close[t-1]
        den = _close_at_lag(sub, as_of, 6)  # close[t-6]
        if num is None or den is None:
            return pd.Series(np.nan, index=day.index, name=self.name)

        rev = -(num.reindex(day.index) / den.reindex(day.index) - 1.0)
        return rev.rename(self.name)


class SizeFactor:
    """规模因子：log(总市值)。

    与 Fama-French SMB 同向（小盘为正）。需要面板含 market_cap 列（元，契约口径）。
    缺失市值 → NaN（契约允许缺失用 NaN 而非 0）。
    """

    name = "size_log_mcap"

    def compute(self, panel: pd.DataFrame, as_of_date, ctx=None) -> pd.Series:
        as_of = pd.Timestamp(as_of_date)
        sub = slice_panel_to_date(panel, as_of)
        try:
            day = sub.xs(as_of, level="date")
        except KeyError:
            return pd.Series(dtype=float, name=self.name)

        if "market_cap" not in day.columns:
            return pd.Series(np.nan, index=day.index, name=self.name)

        mcap = day["market_cap"]
        # 契约：market_cap 单位=元，必须为正；非正/缺失 → NaN
        out = np.log(mcap.where(mcap > 0))
        return out.rename(self.name)


# 注册实例（供 get_factor 取用；与内部因子同一注册表）
register_factor(Momentum20Factor())
register_factor(Reversal5Factor())
register_factor(SizeFactor())
