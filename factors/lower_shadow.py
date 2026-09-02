"""长下影线因子（lower_shadow）。

对应灵感池 i20260806-010：当日出现长下影线（下影线长度 ≥ 实体长度 × 2，且当日实体
涨跌幅绝对值 < 5%）的个股，后续有超跌反弹/逢低吸纳动能——技术面"探底回升"信号。
A 股散户主导、情绪化交易多，长下影常伴随盘中恐慌抛售后被承接，截面含增量信息。

实现（纯 OHLC，逐资产截至 t 的当日线）：
    lower_shadow = (min(open, close) − low) / (high − low + eps)
值越大表示下影越长（盘中下探后被拉回）。方向未知，由 RankIC 符号自动判定。

PIT 安全：compute 仅消费 panel 中 t 及之前的 open/high/low/close，逐日切片只含 ≤t 行；
不引用未来行、不引用 market_cap 快照列（市值暴露由 harness 用 pit_float_mcap 剥离）。
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from factors.interface import register_factor


@register_factor
class LowerShadowFactor:
    name = "lower_shadow"
    fcode = "f0028a"
    universe_hint = "hs300"

    def compute(self, panel: pd.DataFrame, as_of_date, ctx=None) -> pd.Series:
        t = pd.Timestamp(as_of_date)
        sub = panel.sort_index().copy()
        lo = sub[["open", "close"]].min(axis=1)
        ls = (lo - sub["low"]) / (sub["high"] - sub["low"] + 1e-9)
        return ls.xs(t, level="date").dropna()


register_factor(LowerShadowFactor())
