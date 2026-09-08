"""超跌反弹分因子（oversold_rebound_score）· f0057a。

对应灵感池 i20260907-008（forum，集思录「抓反弹」叙事，置信度 low）：
个股超跌反弹分（近 60 日最大回撤深度 z × 近 5 日反弹幅度 z 的合成）截面越高
→ 未来 20 日收益越高。

实现（纯 close，向后看）
------------------------
    dd_depth_t = 1 − close_t / max(close[t−59 … t])      （近 60 日最大回撤深度，正值=跌得深）
    reb_5d_t   = close_t / close[t−5] − 1                （近 5 日反弹幅度）
    factor     = zscore_cs(dd_depth) × zscore_cs(reb_5d) （zscore_cs = 当日截面标准化）

截面 z 在**每个交易日的横截面内**计算（不跨期），因此不引入任何未来信息。

⚠️ 构造固有缺陷（如实声明，不做"修正"）
----------------------------------------
两个 z 相乘时，**双负象限**（回撤浅 + 近期下跌）同样得到正的高分，与"超跌后反弹"
的经济含义相反。这是原假设"z × z 合成"的字面属性，本因子如实实现并在此声明，
而不是私自改成 z 相加或截断负值——那会变成另一条假设，须另开条目重走漏斗。
出包后若 RankIC 接近 0，这个象限混合极可能是主因，属于**对该灵感的证伪证据**。

冗余提示
--------
与 f0034a（触底反弹信号：创 60 日新低后收复 5 日线，二元事件）同族但本因子是
**连续打分**。原条目已要求「先测相关性 >0.8 应合并」，见交付包 correlation.csv。
另与 f0049a（60 日反转）、f0050a（非对称 5 日反转）在窗口上有重叠，须一并核对。

PIT 安全：仅用 close；不读 market_cap 快照列（市值暴露由 harness 用
pit_float_mcap 中性化剥离）。compute_panel 一次性向量化全序列。
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from factors.interface import register_factor

DD_WIN = 60   # 最大回撤深度窗口
REB_WIN = 5   # 反弹幅度窗口


def _zscore_cs(wide: pd.DataFrame) -> pd.DataFrame:
    """逐行（=每个交易日截面）z-score；截面内不足 2 个有效值时整行 NaN。"""
    mu = wide.mean(axis=1, skipna=True)
    sd = wide.std(axis=1, skipna=True, ddof=1)
    sd = sd.where(sd > 0)
    return wide.sub(mu, axis=0).div(sd, axis=0)


class OversoldReboundScoreFactor:
    """超跌反弹分：z(60日最大回撤深度) × z(5日反弹幅度)。"""

    name = "oversold_rebound_score"
    fcode = "f0057a"
    universe_hint = None

    def _full(self, panel: pd.DataFrame) -> pd.Series:
        sub = panel.sort_index()
        close = sub["close"]
        M = close.unstack(level="asset")                       # T x A

        run_max = M.rolling(DD_WIN, min_periods=DD_WIN // 2).max()
        with np.errstate(divide="ignore", invalid="ignore"):
            dd_depth = 1.0 - M / run_max                       # 正值=距高点回撤幅度
            reb = M / M.shift(REB_WIN) - 1.0

        score = _zscore_cs(dd_depth) * _zscore_cs(reb)
        score = score.replace([np.inf, -np.inf], np.nan)
        return score.stack().reindex(close.index)

    def compute(self, panel: pd.DataFrame, as_of_date, ctx=None) -> pd.Series:
        t = pd.Timestamp(as_of_date)
        return self._full(panel).xs(t, level="date").dropna().rename(self.name)

    def compute_panel(self, panel: pd.DataFrame) -> pd.DataFrame:
        return self._full(panel).unstack(level="asset")


register_factor(OversoldReboundScoreFactor())
