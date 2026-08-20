"""10 日平均换手率因子（avg_turnover_10d）。

逻辑（对应灵感池 i20260820-023，P0）：取每只股票截至 t 的
**前 10 个交易日换手率均值**，刻画短期交易活跃度/流动性脉冲：
    factor = mean(turnover_{t-9..t})

来源：迅投因子看板换手率类因子（IC=0.887, IR=0.550, 最大分位超额=31.71%,
最大分位换手=0.03%）。短窗口对情绪/流动性突变更敏感，是"近期是否异常放量"
的朴素代理。

PIT 安全：
- compute 仅消费 panel 中 t 及之前的数据；rolling 窗口只向后看，
  .xs(t) 处滚动值只含 ≤t 行。
- turnover 为 t 日当日可观测量，不含未来信息；不引用 close（前复权含未来分红）
  亦不引用 market_cap 快照列。
- 纯函数，满足 assert_no_lookahead 一致性（全量 vs 切片面板在 t 处输出相同）。
- 市值暴露由 harness 用 data/pit.py 现算 PIT 流通市值剥离，本模块不碰。
"""
from __future__ import annotations

import pandas as pd
import numpy as np

from factors.interface import register_factor

WINDOW = 10


@register_factor
class AvgTurnover10dFactor:
    name = "avg_turnover_10d"
    universe_hint = "hs300"

    def compute(self, panel: pd.DataFrame, as_of_date, ctx=None) -> pd.Series:
        t = pd.Timestamp(as_of_date)
        sub = panel.sort_index()
        g = sub.groupby(level="asset")["turnover"]
        avg = g.transform(lambda s: s.rolling(WINDOW, min_periods=WINDOW).mean())
        return avg.xs(t, level="date").dropna()


register_factor(AvgTurnover10dFactor())
