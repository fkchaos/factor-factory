"""240 日平均换手率因子（avg_turnover_240d）。

逻辑（对应灵感池 i20260820-025，P0）：取每只股票截至 t 的
**前 240 个交易日换手率均值**，刻画长期（约一年）流动性基准水平：
    factor = mean(turnover_{t-239..t})

来源：迅投因子看板换手率类因子（IC=0.791, IR=0.390, 最大分位超额=42.42%,
最大分位换手=0.00%）。长窗口更平滑，反映"常态流动性"，与 10d/120d 短窗口
构成流动性期限结构。

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

WINDOW = 240


@register_factor
class AvgTurnover240dFactor:
    name = "avg_turnover_240d"
    fcode = "f0013a"
    universe_hint = "hs300"

    def compute(self, panel: pd.DataFrame, as_of_date, ctx=None) -> pd.Series:
        t = pd.Timestamp(as_of_date)
        sub = panel.sort_index()
        g = sub.groupby(level="asset")["turnover"]
        avg = g.transform(lambda s: s.rolling(WINDOW, min_periods=WINDOW).mean())
        return avg.xs(t, level="date").dropna()


register_factor(AvgTurnover240dFactor())
