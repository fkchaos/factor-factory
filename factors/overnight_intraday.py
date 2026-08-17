"""隔夜-日内因子（Overnight / Intraday Decomposition）。

A 股实证（中信建投 2025-11 等）：overnight 收益显著为负、intraday 为正，两者负相关（"拔河效应"）。
本因子刻画该微观结构异象，**零新增数据源**（只需日 K 的 open / close，LocalProvider 已具备）。

前视防护（关键）：compute 仅用 as_of_date 当日 open/close 与上一交易日 close，
不依赖全样本横截面排名——天然通过 assert_no_lookahead（见 factors/interface.py）。

**符号约定（2026-08-05 真实数据复核，见 TEST_LOG / RESEARCH_LOG R2026-0805-02）**：
- 因子值 = `overnight - intraday`（**不做多日内强、隔夜弱**）。
- 拆解实证（SZ300 2020 起）：overnight 成分 RankIC +0.024（正信号）、intraday 成分 -0.028（日内反转负信号）；
  因子 `-(overnight - intraday)`（旧版方向）RankIC -0.040（**方向反了**）；
  翻转后 `(overnight - intraday)` RankIC **+0.040 / ICIR 11.6**（1日）/+0.030 / ICIR 9.0（5日）。
- 经济含义：做多"隔夜高开 + 日内冲高回落"的票（冲高回落 → 次日修复 + 隔夜延续），
  实质是**日内反转 + 隔夜延续**的合成信号；换手极高，成本敏感（组合回测必须含成本）。
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from factors.interface import Factor, register_factor, slice_panel_to_date


class OvernightIntradayFactor:
    name = "overnight_intraday"
    fcode = "f0001a"  # 交付包代号（对齐 deliverables/factors/_REGISTRY.csv）
    universe_hint = "zz1000"  # 实测主场（2026-08-07 六池矩阵：RankIC 最高 +0.0309）

    def compute(self, panel: pd.DataFrame, as_of_date, ctx=None) -> pd.Series:
        as_of = pd.Timestamp(as_of_date)
        sub = slice_panel_to_date(panel, as_of)  # 双保险：只留 as_of 及之前
        try:
            day = sub.xs(as_of, level="date")
        except KeyError:
            return pd.Series(dtype=float, name=self.name)

        prev_dates = [d for d in sub.index.get_level_values("date").unique() if d < as_of]
        if not prev_dates:
            # 没有历史交易日，无法算 overnight（需前一日 close）
            return pd.Series(np.nan, index=day.index, name=self.name)

        prev_close = sub.xs(prev_dates[-1], level="date")["close"]
        o = day["open"]
        c = day["close"]
        overnight = o / prev_close - 1.0
        intraday = c / o - 1.0
        # 因子：做多"隔夜高开 + 日内冲高回落"（overnight - intraday；符号经真实数据复核翻转）
        factor_val = overnight - intraday
        return factor_val.rename(self.name)


# 注册实例（供 get_factor 取用；注意注册的是实例，非类）
register_factor(OvernightIntradayFactor())
