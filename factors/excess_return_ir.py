"""超额收益信息比率因子（excess_return_ir）。

对应灵感池 i20260907-005：个股近 60 日日超额（市场中性）收益序列的信息比率
（均值/标准差）截面越高 → 未来 20 日收益越高（收益"质量"/持续性强，非单纯动量或低波）。

实现（纯 close，向后看，WIN=60）：
    ret   = close 逐资产 pct_change(1)
    mkt   = 每日跨资产等权平均收益
    excess = ret - mkt                         （市场中性超额收益）
    IR    = excess.rolling(60).mean() / excess.rolling(60).std()
    factor = IR
全向量化（unstack 矩阵 + rolling），O(N·A) 高效。

PIT 安全：仅用 close；不读 market_cap 快照列（市值暴露由 harness 用 pit_float_mcap 剥离）。
compute_panel 一次性向量化全序列。
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from factors.interface import register_factor

WIN = 60


class ExcessReturnIRFactor:
    """超额收益信息比率：市场中性超额收益 60 日均值/标准差。"""

    name = "excess_return_ir"
    fcode = "f0054a"
    universe_hint = None

    def _full(self, panel: pd.DataFrame) -> pd.Series:
        sub = panel.sort_index()
        ret = sub["close"].groupby(level="asset").pct_change()
        mkt = ret.groupby(level="date").mean()
        mkt_aligned = pd.Series(
            ret.index.get_level_values("date").map(mkt), index=ret.index)
        excess = ret - mkt_aligned

        M = excess.unstack(level="asset")                    # T x A
        ir = M.rolling(WIN).mean() / M.rolling(WIN).std()
        return ir.stack().reindex(excess.index)

    def compute(self, panel: pd.DataFrame, as_of_date, ctx=None) -> pd.Series:
        t = pd.Timestamp(as_of_date)
        return self._full(panel).xs(t, level="date").dropna().rename(self.name)

    def compute_panel(self, panel: pd.DataFrame) -> pd.DataFrame:
        return self._full(panel).unstack(level="asset")


register_factor(ExcessReturnIRFactor())
