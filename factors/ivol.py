"""特质波动率因子（Idiosyncratic Volatility, IVOL）。

A 股实证（北大 nsd 2025「昼伏夜出」等）：低 IVOL 存在稳健溢价（低波动异象），
且 IVOL 与隔夜/日内拆解负相关——本质是散户过度交易制造的高波动小票被定价过高。

因子定义（对齐研报）：
- 日收益 ret = close / close.shift(1) - 1
- 市场收益 ret_m = 窗口内所有资产等权日收益（剥离系统性波动）
- 对每只资产：ret_i = alpha + beta * ret_m + eps，IVOL = std(eps)（回归残差波动，即特质波动）
- 因子值 = -IVOL：做多低特质波动（低波动溢价，反向）

前视防护（关键）：
- compute 仅用 as_of_date 及之前的 close（slice_panel_to_date 双保险）
- 市场收益、回归窗口均取自 as_of 历史同窗口，不触碰未来
- 天然通过 assert_no_lookahead（CI 门禁）
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from factors.interface import Factor, register_factor, slice_panel_to_date


class IvolFactor:
    name = "ivol"
    fcode = "f0002a"  # 交付包代号（对齐 deliverables/factors/_REGISTRY.csv）
    universe_hint = "zz1000"  # 实测主场（2026-08-07 六池矩阵：RankIC 最高 +0.0510）

    def __init__(self, window: int = 20):
        self.window = window

    def compute(self, panel: pd.DataFrame, as_of_date, ctx=None) -> pd.Series:
        as_of = pd.Timestamp(as_of_date)
        sub = slice_panel_to_date(panel, as_of)  # 双保险：只留 as_of 及之前

        dates = sorted(sub.index.get_level_values("date").unique())
        if as_of not in dates:
            return pd.Series(dtype=float, name=self.name)
        idx = dates.index(as_of)
        w_dates = dates[max(0, idx - self.window + 1): idx + 1]
        if len(w_dates) < self.window:
            # 预热不足：返回 as_of 当日资产集合的 NaN（不造假信号）
            assets = sub.xs(as_of, level="date").index
            return pd.Series(np.nan, index=assets, name=self.name)

        win = sub.loc[sub.index.get_level_values("date").isin(w_dates)]
        closes = win["close"].unstack("asset")          # date x asset
        rets = closes.pct_change().dropna()             # 少一行（无前一日）
        if rets.shape[0] < 5:
            assets = sub.xs(as_of, level="date").index
            return pd.Series(np.nan, index=assets, name=self.name)

        mkt = rets.mean(axis=1)                          # 等权市场日收益（仅历史）
        assets = rets.columns
        ivols = {}
        for a in assets:
            ra = rets[a]
            df = pd.concat([ra, mkt], axis=1).dropna()
            df.columns = ["ra", "rm"]
            if len(df) < 5:
                ivols[a] = np.nan
                continue
            X = np.column_stack([np.ones(len(df)), df["rm"].values])
            y = df["ra"].values
            beta, *_ = np.linalg.lstsq(X, y, rcond=None)
            eps = y - X @ beta
            ivols[a] = float(np.std(eps))

        factor_val = -pd.Series(ivols)                  # 反向：低波动溢价
        return factor_val.rename(self.name)


# 注册默认实例（window=20）；注意注册的是实例，非类
register_factor(IvolFactor())
