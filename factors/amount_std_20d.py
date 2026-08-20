"""20 日成交金额标准差因子（amount_std_20d）。

逻辑（对应灵感池 i20260820-026，P0）：取每只股票截至 t 的
**前 20 个交易日成交金额标准差**（对数金额更稳，正态化后再取 std）：
    log_amt = log(amount + 1)
    factor  = std(log_amt_{t-19..t})

来源：迅投因子看板（IC=0.710, IR=0.827, 最大分位超额=22.67%, 最大分位换手=0.04%）。
成交金额波动刻画"资金关注度/分歧度"——高波动常伴随事件驱动或主力进出。
方向未知，由 RankIC 符号自动判定。

PIT 安全：
- compute 仅消费 panel 中 t 及之前的数据；rolling 窗口只向后看，
  .xs(t) 处滚动值只含 ≤t 行。
- amount 为 t 日当日可观测量（成交额 = 成交量×均价），不含未来信息；
  不引用 close 前复权价亦不引用 market_cap 快照列。
- 纯函数，满足 assert_no_lookahead 一致性（全量 vs 切片面板在 t 处输出相同）。
- 市值暴露由 harness 用 data/pit.py 现算 PIT 流通市值剥离，本模块不碰。
"""
from __future__ import annotations

import pandas as pd
import numpy as np

from factors.interface import register_factor

WINDOW = 20


@register_factor
class AmountStd20dFactor:
    name = "amount_std_20d"
    universe_hint = "hs300"

    def compute(self, panel: pd.DataFrame, as_of_date, ctx=None) -> pd.Series:
        t = pd.Timestamp(as_of_date)
        sub = panel.sort_index().copy()
        log_amt = np.log(sub["amount"].clip(lower=0) + 1.0)
        g = log_amt.groupby(level="asset")
        std = g.transform(lambda s: s.rolling(WINDOW, min_periods=WINDOW).std())
        return std.xs(t, level="date").dropna()


register_factor(AmountStd20dFactor())
