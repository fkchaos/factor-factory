"""分歧度代理因子（dispersion_agent）。

对应灵感池 i20260805-006：分歧度代理 = 20 日换手率 z × 20 日特质波动率 z
（行业内标准化）越高 → 未来 20 日收益越低（高换手叠加高波动 = 分歧/博弈剧烈，
定价过度、后续走弱）。

实现（纯 close + turnover，逐资产截至 t）：
    to_z  = 个股自身换手率相对其近 60 日历史的 z 分数（trailing Wz 标准化）
    vol_z = 个股自身 20 日收益波动率相对其近 60 日历史的 z 分数
            （波动率用 total-return std 作 PIT 干净代理；系统性部分由 harness 中性化剥离）
    factor_t = to_z × vol_z
    两层 z 均为「时序 z」（该股票自身近期相对自身的反常程度），契合「分歧度」直觉；
    行业/市值暴露由 harness 中性化。

PIT 安全：仅用 close / turnover；不引用 market_cap 快照列（市值暴露由 harness 剥离）。
纯函数，满足 assert_no_lookahead。
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from factors.interface import register_factor

WV = 20    # 波动率 / 换手率滚动窗口
WZ = 60    # 时序 z 标准化窗口


@register_factor
class DispersionAgentFactor:
    name = "dispersion_agent"
    fcode = "f0042a"
    universe_hint = None

    def compute(self, panel: pd.DataFrame, as_of_date, ctx=None) -> pd.Series:
        t = pd.Timestamp(as_of_date)
        sub = panel.sort_index()

        # 时序 z：换手率
        to = sub["turnover"]
        to_m = sub.groupby(level="asset")["turnover"].transform(
            lambda s: s.rolling(WZ).mean()
        )
        to_s = sub.groupby(level="asset")["turnover"].transform(
            lambda s: s.rolling(WZ).std()
        )
        to_z = (to - to_m) / to_s

        # 时序 z：波动率（20 日收益 std 的滚动序列再做 60 日 z）
        rets = sub["close"].pct_change()
        vol_series = rets.groupby(level="asset").transform(
            lambda s: s.rolling(WV).std()
        )
        vol_m = vol_series.groupby(level="asset").transform(
            lambda s: s.rolling(WZ).mean()
        )
        vol_s = vol_series.groupby(level="asset").transform(
            lambda s: s.rolling(WZ).std()
        )
        vol_z = (vol_series - vol_m) / vol_s

        dispersion = to_z * vol_z
        return dispersion.xs(t, level="date").dropna().rename(self.name)


register_factor(DispersionAgentFactor())
