"""120 日平均换手率因子（avg_turnover_120d）。

逻辑（对应灵感池 i20260820-022，P0 第一名）：取每只股票截至 t 的
**前 120 个交易日换手率均值**，刻画中长期流动性水平/交易活跃度：
    factor = mean(turnover_{t-119..t})

来源：迅投因子看板（沪深300 / 近1年）换手率类因子中 IC/IR/超额/低换手
综合最强的一项（IC=0.767, IR=0.969, 最大分位超额=50.66%, 最大分位换手=0.01%）。
我方 PIT 口径下重测前，方向未知——卡片由 RankIC 符号自动判定
（高换手→低未来收益=反向，是常见"低流动性溢价"形态；也可能正向）。

PIT 安全：
- compute 仅消费 panel 中 t 及之前的数据（引擎已先行 slice_panel_to_date，
  且 rolling 窗口只向后看，对任意传入面板，.xs(t) 处滚动值只含 ≤t 行）。
- turnover 为 t 日当日可观测量（定义 = volume/流通股本），不含未来信息；
  不引用 close（前复权价含未来分红）亦不引用 market_cap 快照列。
- 纯函数（无实例状态），满足 assert_no_lookahead 一致性（全量面板 vs 切片面板
  在 t 处输出完全相同）。
- 中性化阶段的市值暴露由 harness 用 data/pit.py 现算 PIT 流通市值剥离，本模块不碰。
"""
from __future__ import annotations

import pandas as pd
import numpy as np

from factors.interface import register_factor

WINDOW = 120


@register_factor
class AvgTurnover120dFactor:
    name = "avg_turnover_120d"
    fcode = "f0011a"
    universe_hint = "hs300"

    def compute(self, panel: pd.DataFrame, as_of_date, ctx=None) -> pd.Series:
        t = pd.Timestamp(as_of_date)
        sub = panel.sort_index()
        g = sub.groupby(level="asset")["turnover"]
        avg = g.transform(lambda s: s.rolling(WINDOW, min_periods=WINDOW).mean())
        return avg.xs(t, level="date").dropna()


register_factor(AvgTurnover120dFactor())
