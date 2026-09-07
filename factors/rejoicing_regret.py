"""rejoicing-regret 度因子（rejoicing_regret，行为金融 DRR 代理）。

对应灵感池 i20260907-002：个股近 N 日 "rejoicing-regret 度"（上涨日频率×涨幅 −
未实现亏损日频率×亏损幅度）截面越高 → 未来 20 日收益越低（高 DRR 股被过度定价，
需补偿 anticipated regret）。

实现（纯 close，向后看，N=20）：
    R = 逐资产日收益
    up_freq = (R>0) 的 20 日滚动占比
    up_mag  = 上涨日收益之和 / 上涨日数（20 日窗口）
    dn_mag  = 下跌日 |收益| 之和 / 下跌日数（20 日窗口，近似 down_freq=1-up_freq）
    DRR     = up_freq*up_mag - (1-up_freq)*dn_mag
    factor  = -DRR     （越高过度定价 → 未来收益越低）
全向量化（unstack 矩阵 + rolling），O(N·A) 高效。

PIT 安全：仅用 close；不读 market_cap 快照列（市值暴露由 harness 用 pit_float_mcap 剥离）。
compute_panel 一次性向量化全序列。
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from factors.interface import register_factor

N = 20


class RejoicingRegretFactor:
    """rejoicing-regret 度：上涨日 rejoicing 减下跌日 regret，取负号。"""

    name = "rejoicing_regret"
    fcode = "f0053a"
    universe_hint = None

    def _full(self, panel: pd.DataFrame) -> pd.Series:
        sub = panel.sort_index()
        ret = sub["close"].groupby(level="asset").pct_change()
        R = ret.unstack(level="asset")                       # T x A

        pos = R.clip(lower=0.0)
        neg = (-R).clip(lower=0.0)
        up_flag = (R > 0)
        dn_flag = (R < 0)

        up_freq = up_flag.rolling(N).mean()
        up_mag = pos.rolling(N).sum() / up_flag.rolling(N).sum().replace(0, np.nan)
        dn_mag = neg.rolling(N).sum() / dn_flag.rolling(N).sum().replace(0, np.nan)

        drr = up_freq * up_mag - (1.0 - up_freq) * dn_mag
        factor = -drr
        return factor.stack().reindex(ret.index)

    def compute(self, panel: pd.DataFrame, as_of_date, ctx=None) -> pd.Series:
        t = pd.Timestamp(as_of_date)
        return self._full(panel).xs(t, level="date").dropna().rename(self.name)

    def compute_panel(self, panel: pd.DataFrame) -> pd.DataFrame:
        return self._full(panel).unstack(level="asset")


register_factor(RejoicingRegretFactor())
