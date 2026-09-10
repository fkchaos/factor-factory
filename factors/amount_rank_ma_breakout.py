"""成交额前分位 + 均线突破因子（amount_rank_ma_breakout）。

对应灵感池 i20260910-009：个股当日成交额处全市场前分位（如前5%）且收盘>5日&10日均线
→ 未来20日收益越高（放量突破 / 资金聚焦 + 趋势确认）。

实现（纯 amount / close，逐资产截至 t）：
    - amount_pctrank：每个交易日 t 对全市场 amount 做截面百分位排名（0~1）。
    - above_ma：close > MA5 且 close > MA10。
    因子值 = amount_pctrank × above_ma（above_ma 为 0/1 掩码）。
    即：只有站上双均线且成交额处于全市场高位的股票才获得高分；单纯高成交但破位、
    或站上均线但成交平淡，均不计入。

PIT 安全：仅用 close / amount（均为 t 日及之前可观测量），不读 market_cap 快照列，
市值暴露由 harness 用 data/pit.pit_float_mcap 剥离。纯函数（无实例状态），满足
assert_no_lookahead 一致性。
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from factors.interface import register_factor

W5 = 5
W10 = 10


@register_factor
class AmountRankMABreakoutFactor:
    name = "amount_rank_ma_breakout"
    fcode = "f0080a"
    universe_hint = None

    def compute(self, panel: pd.DataFrame, as_of_date, ctx=None) -> pd.Series:
        t = pd.Timestamp(as_of_date)
        sub = panel.sort_index()  # 已切片到 t

        df = pd.DataFrame(index=sub.index)
        df["close"] = sub["close"].astype(float)
        df["amount"] = sub["amount"].astype(float)

        g = df.groupby(level="asset")
        ma5 = g["close"].transform(lambda s: s.rolling(W5).mean())
        ma10 = g["close"].transform(lambda s: s.rolling(W10).mean())

        # 截面百分位排名（按交易日，全市场 amount 排名）
        amt_rank = df["amount"].groupby(level="date").rank(pct=True)
        above = (df["close"] > ma5) & (df["close"] > ma10)

        f = amt_rank * above.astype(float)
        return f.xs(t, level="date").dropna().rename(self.name)


register_factor(AmountRankMABreakoutFactor())
