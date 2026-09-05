"""最大 5 日涨幅均值因子（max5_return）。

对应灵感池 i20260805-009：过去 20 日单日涨幅最大 5 天的平均涨幅（MAX5）越高 →
未来 20 日收益越低（彩票型/过度反应股票，短期被情绪推高后回落）。

实现（纯 close，逐资产截至 t）：
    ret = close.pct_change()
    factor_t = mean( ret 在 trailing W=20 日内 最大的 5 个值 )

PIT 安全：仅用 close；不引用 market_cap 快照列（市值暴露由 harness 剥离）。
纯函数，满足 assert_no_lookahead。
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from factors.interface import register_factor

W = 20


def _mean_top5(w):
    return np.sort(w)[-5:].mean()


@register_factor
class Max5ReturnFactor:
    name = "max5_return"
    fcode = "f0039a"
    universe_hint = None

    def compute(self, panel: pd.DataFrame, as_of_date, ctx=None) -> pd.Series:
        t = pd.Timestamp(as_of_date)
        sub = panel.sort_index()
        rets = sub["close"].pct_change()
        max5 = rets.groupby(level="asset").transform(
            lambda s: s.rolling(W).apply(_mean_top5, raw=True)
        )
        return max5.xs(t, level="date").dropna().rename(self.name)


register_factor(Max5ReturnFactor())
