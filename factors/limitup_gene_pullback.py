"""涨停基因回踩因子（limitup_gene_pullback）。

对应灵感池 i20261005-009：雪球"量化思维下的 A 股短线暴利"(2026) 实战规律——高波动股
（近 10 日 ≥2 次涨停）回踩 5/10 日线不破前日最低 → 隔日尾盘低吸次日冲高止盈。

A 股落地口径（纯 OHLCV，无前视）：
    1) limit_up = 日收益(close/prev_close−1) ≥ 0.095  （主板 ~10% 涨停近似；忽略 ST 5% 档）
    2) gene     = 近 10 日涨停次数（rolling sum）
    3) ma5/ma10 = close 5/10 日均值；prev_low = 前日最低价 low.shift(1)
    4) pullback_ok = (close ≥ ma5) & (close ≥ ma10) & (close ≥ prev_low)
       （回踩不破均线、且不破前日最低 = 健康缩量回踩，非破位）
    5) 因子 = gene × pullback_ok     （有涨停基因且处健康回踩 → 信号；否则 0）

经济含义：近期频繁涨停（量化资金主战场、强动量基因）且回踩不破位的个股，隔日脉冲
收益更高。区别于第二阶段突破(f0087a，纯趋势+基底突破)与强势股+板块共振(i20260921-010)——
本因子强调"涨停频次基因 + 缩量回踩不破"的隔日事件型脉冲。

PIT 安全：仅用 open/high/low/close（均为 t 日及之前可观测量）；不引用 market_cap 快照列
（市值暴露由 harness 用 pit_float_mcap 剥离）。
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from factors.interface import register_factor

W_GENE = 10       # 涨停基因统计窗口（交易日）
LIMIT_TH = 0.095  # 涨停近似阈值（主板 ~10%）


@register_factor
class LimitupGenePullbackFactor:
    """涨停基因回踩：近 10 日涨停次数 × 健康回踩条件。"""

    name = "limitup_gene_pullback"
    fcode = "f0091a"
    universe_hint = None

    def compute(self, panel: pd.DataFrame, as_of_date, ctx=None) -> pd.Series:
        t = pd.Timestamp(as_of_date)
        f = self._factor_panel(panel)
        return f.xs(t, level="date").dropna().rename(self.name)

    def compute_panel(self, panel: pd.DataFrame) -> pd.DataFrame:
        f = self._factor_panel(panel)
        return f.unstack(level="asset")  # date × asset

    def _factor_panel(self, panel: pd.DataFrame) -> pd.DataFrame:
        sub = panel.sort_index()
        g = sub.groupby(level="asset")
        close = sub["close"]
        low = sub["low"]
        ret = close.pct_change()
        limit_up = (ret >= LIMIT_TH).astype(float)
        gene = limit_up.groupby(level="asset").transform(
            lambda s: s.rolling(W_GENE, min_periods=W_GENE).sum())
        ma5 = g["close"].transform(lambda s: s.rolling(5, min_periods=5).mean())
        ma10 = g["close"].transform(lambda s: s.rolling(10, min_periods=10).mean())
        prev_low = low.groupby(level="asset").shift(1)
        pullback_ok = ((close >= ma5) & (close >= ma10) & (close >= prev_low)).astype(float)
        factor = gene * pullback_ok
        return factor


register_factor(LimitupGenePullbackFactor())
