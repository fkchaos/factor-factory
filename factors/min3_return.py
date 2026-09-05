"""最低 3 日收益因子（min3_return）。

对应灵感池 i20260806-001：行业+市值中性化后，过去 21 日日收益升序排列的最低 3 日
均值（MIN3）越低（即近期出现过更极端的单日大跌）→ 未来 20 日收益越高（短期反转）。

实现（纯 close，逐资产截至 t）：
    ret = close.pct_change()
    factor_t = mean( ret 在 trailing W=21 日内 最小的 3 个值 )
    （MIN3 越低 = 越负的极端日越多 → 反转预期越强，因子值与未来收益正相关）

PIT 安全：仅用 close；不引用 market_cap 快照列（市值暴露由 harness 剥离）。
纯函数，满足 assert_no_lookahead。
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from factors.interface import register_factor

W = 21


def _mean_bottom3(w):
    return np.sort(w)[:3].mean()


@register_factor
class Min3ReturnFactor:
    name = "min3_return"
    fcode = "f0040a"
    universe_hint = None

    def compute(self, panel: pd.DataFrame, as_of_date, ctx=None) -> pd.Series:
        t = pd.Timestamp(as_of_date)
        sub = panel.sort_index()
        rets = sub["close"].pct_change()
        min3 = rets.groupby(level="asset").transform(
            lambda s: s.rolling(W).apply(_mean_bottom3, raw=True)
        )
        return min3.xs(t, level="date").dropna().rename(self.name)


register_factor(Min3ReturnFactor())
