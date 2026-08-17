"""微观结构因子（第三条腿 d 类：A股特色，从交易机制推导）。

纯日线可得（open/high/low/close），无需另类数据。A股独有的涨跌停 / T+1 机制在美股
不存在，因此论文里也没有现成因子，我们反而有"地利"。本期实现两个可交付因子：

  - overnight_gap  : 隔夜跳空 = open / prev_close - 1
                     （T+1 机制下隔夜与盘中是两类资金，隔夜跳空是独立信号）
  - limit_up_seal  : 涨停封板代理（±10% 限制）
                     封死=1.0，曾打开=0.5，未涨停=0.0
                     （日线无封单量，用"最高价是否等于收盘"近似"是否封死"）

前向防护：compute 仅用 as_of 及之前数据（slice_panel_to_date 双保险），
与内部因子同一套纪律；返回原始截面值，中性化由下游 validator/engine 统一处理。
"""
from __future__ import annotations
import numpy as np
import pandas as pd

from factors.interface import Factor, register_factor, slice_panel_to_date


def _prev_close(sub: pd.DataFrame, as_of) -> pd.Series | None:
    """返回 as_of 前一交易日的 close 截面（严格小于 as_of）。历史不足返回 None。"""
    dates = sorted(d for d in sub.index.get_level_values("date").unique() if d < as_of)
    if len(dates) == 0:
        return None
    try:
        return sub.xs(dates[-1], level="date")["close"]
    except KeyError:
        return None


class OvernightGapFactor:
    """隔夜跳空因子：open / 前收 - 1。正值=隔夜跳空高开。"""
    name = "overnight_gap"
    universe_hint = None

    def compute(self, panel: pd.DataFrame, as_of_date, ctx=None) -> pd.Series:
        as_of = pd.Timestamp(as_of_date)
        sub = slice_panel_to_date(panel, as_of)
        try:
            day = sub.xs(as_of, level="date")
        except KeyError:
            return pd.Series(dtype=float, name=self.name)
        if "open" not in day.columns or "close" not in day.columns:
            return pd.Series(np.nan, index=day.index, name=self.name)
        prev_close = _prev_close(sub, as_of)
        if prev_close is None:
            return pd.Series(np.nan, index=day.index, name=self.name)
        gap = day["open"].reindex(day.index) / prev_close.reindex(day.index) - 1.0
        return gap.rename(self.name)


class LimitUpSealFactor:
    """涨停封板代理：A股 ±10% 限制下的封板强度。

    日线无封单量，用"最高价是否等于收盘"近似是否封死：
      - 收盘达到涨停价且最高价==收盘 -> 封死 (1.0)
      - 收盘达到涨停价但最高价>收盘 -> 曾打开 (0.5)
      - 未涨停 -> 0.0
    """
    name = "limit_up_seal"
    universe_hint = None
    LIMIT = 1.098  # 近似涨停阈值（±10%，留 0.2% 容差）

    def compute(self, panel: pd.DataFrame, as_of_date, ctx=None) -> pd.Series:
        as_of = pd.Timestamp(as_of_date)
        sub = slice_panel_to_date(panel, as_of)
        try:
            day = sub.xs(as_of, level="date")
        except KeyError:
            return pd.Series(dtype=float, name=self.name)
        needed = {"close", "high"}
        if not needed.issubset(day.columns):
            return pd.Series(np.nan, index=day.index, name=self.name)
        prev_close = _prev_close(sub, as_of)
        if prev_close is None:
            return pd.Series(np.nan, index=day.index, name=self.name)
        limit_price = prev_close.reindex(day.index) * self.LIMIT
        is_limit = day["close"] >= limit_price * 0.999
        sealed = is_limit & (day["high"] <= day["close"] + 1e-9)
        opened = is_limit & (day["high"] > day["close"] + 1e-9)
        out = np.where(sealed, 1.0, np.where(opened, 0.5, 0.0))
        return pd.Series(out, index=day.index, name=self.name)


register_factor(OvernightGapFactor())
register_factor(LimitUpSealFactor())
