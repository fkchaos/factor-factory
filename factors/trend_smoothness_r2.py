"""趋势平滑度 R² 因子（trend_smoothness_r2）。

对应灵感池 i20260805-008：过去 60 日累计收益相同的股票中，日收益序列对时间回归
R²（趋势平滑度）越高 → 未来 20 日收益越低（趋势已过度延伸、均值回复压力更大）。

实现（纯 close，逐资产截至 t）：
    y = log(close)
    对每只股票取截至 t 的 trailing W=60 日窗口，回归 y 对时间索引，取 R²。
    R² 越大表示价格走势越接近一条直线（强趋势），越小表示震荡/无序。
    R² = cov(y,x)² / (var(x)·var(y))，其中 x 为窗口内 0..W-1 的时间序号，
    var(x) = (W²-1)/12 为常数，cov/var 用滚动均值向量化计算（无逐窗 python 循环）。

PIT 安全：
- compute 仅消费 sub（harness 已切片到 t）中的 close；不引用 market_cap 快照列，
  市值暴露由 harness 用 data/pit.py 现算 PIT 流通市值剥离。
- 纯函数（无实例状态），满足 assert_no_lookahead 一致性。
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from factors.interface import register_factor

W = 60
VAR_X = (W * W - 1) / 12.0  # 时间序号 0..W-1 的方差（常数）


@register_factor
class TrendSmoothnessR2Factor:
    name = "trend_smoothness_r2"
    fcode = "f0038a"
    universe_hint = None

    def compute(self, panel: pd.DataFrame, as_of_date, ctx=None) -> pd.Series:
        t = pd.Timestamp(as_of_date)
        sub = panel.sort_index()  # 已切片到 t

        df = pd.DataFrame(index=sub.index)
        df["y"] = np.log(sub["close"].clip(lower=1e-9))
        # 每只股票内从 0 递增的时间序号（窗口内即 0..W-1，绝对偏移不影响 cov）
        df["x"] = df.groupby(level="asset").cumcount().astype(float)
        df["xy"] = df["x"] * df["y"]
        df["y2"] = df["y"] ** 2

        g = df.groupby(level="asset")
        m_x = g["x"].transform(lambda s: s.rolling(W).mean())
        m_y = g["y"].transform(lambda s: s.rolling(W).mean())
        m_xy = g["xy"].transform(lambda s: s.rolling(W).mean())
        m_y2 = g["y2"].transform(lambda s: s.rolling(W).mean())

        var_y = m_y2 - m_y ** 2
        cov_xy = m_xy - m_x * m_y
        with np.errstate(divide="ignore", invalid="ignore"):
            r2 = (cov_xy ** 2) / (VAR_X * var_y)
        r2 = r2.clip(0.0, 1.0)

        return r2.xs(t, level="date").dropna().rename(self.name)


register_factor(TrendSmoothnessR2Factor())
