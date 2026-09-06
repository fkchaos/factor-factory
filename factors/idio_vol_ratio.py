"""特质波动率比率因子（idio_vol_ratio）。

对应灵感池 i20260820-038：特质波动率比率（近 20 日特质波动率 / 近 120 日特质波动率）越低 →
未来 20 日收益越高；近期特质波动相对长期抬升 = 个股特有信息冲击/噪声放大，未来走弱。

实现（纯 close，向后看）：
    ret = close 逐资产 pct_change(1)
    mkt = 每日跨资产等权平均收益（系统性代理）
    resid = ret - mkt（市值=1 近似的特质收益，行业暴露由 harness 中性化）
    idio_vol_s = resid 20 日滚动 std；idio_vol_l = resid 120 日滚动 std
    factor = idio_vol_s / idio_vol_l
>1 = 近期特质波动放大。

PIT 安全：仅用 close；不读 market_cap 快照列。
C 级 groupby.rolling.std；收益用 groupby.pct_change 防跨资产错位。
compute_panel 一次性向量化全序列（O(N)）。
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from factors.interface import register_factor

SHORT = 20
LONG = 120


class IdioVolRatioFactor:
    """特质波动率比率：20 日特质波动 / 120 日特质波动。"""

    name = "idio_vol_ratio"
    fcode = "f0046a"
    universe_hint = None

    def _full(self, panel: pd.DataFrame) -> pd.Series:
        sub = panel.sort_index()
        ret = sub["close"].groupby(level="asset").pct_change()
        mkt = ret.groupby(level="date").mean()
        mkt_aligned = pd.Series(
            ret.index.get_level_values("date").map(mkt), index=ret.index)
        resid = ret - mkt_aligned
        vol_s = (resid.groupby(level="asset").rolling(SHORT, min_periods=SHORT).std()
                 .reset_index(level=0, drop=True))
        vol_l = (resid.groupby(level="asset").rolling(LONG, min_periods=LONG).std()
                 .reset_index(level=0, drop=True))
        with np.errstate(divide="ignore", invalid="ignore"):
            ratio = vol_s / vol_l.replace(0.0, np.nan)
        return ratio

    def compute(self, panel: pd.DataFrame, as_of_date, ctx=None) -> pd.Series:
        t = pd.Timestamp(as_of_date)
        return self._full(panel).xs(t, level="date").dropna().rename(self.name)

    def compute_panel(self, panel: pd.DataFrame) -> pd.DataFrame:
        return self._full(panel).unstack(level="asset")


register_factor(IdioVolRatioFactor())
