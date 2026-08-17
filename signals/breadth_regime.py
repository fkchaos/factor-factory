"""广度 Regime 信号（Breadth Regime Signal）。

v75 复盘核心洞察：最优策略表现来自「广度过滤 = regime 选择器」——
它让策略只在因子有效的市场状态下交易。本信号直接把"市场广度"做成时序状态判断。

定义：
- raw（连续值）：每日 (上涨家数 − 下跌家数) / 总数，范围 [-1, 1]。
  零新增数据源，只需日 K 的 close（BaoStockProvider 缓存已具备）。
- 状态（离散，在交付/验证阶段由 20 日 MA 平滑后阈值化）：
  breadth_MA20 > 0 → risk_on（多头环境，因子可放手）；≤ 0 → risk_off（防御，减仓/空仓）。

前视防护：compute 仅用 as_of_date 当日 close 与上一交易日 close，
返回当日广度标量（不做 MA 平滑——平滑由交付阶段对有序序列滚动计算，
天然只用历史，无前视）。天然通过 assert_no_lookahead。
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from signals.interface import Signal, register_signal, slice_panel_to_date


class BreadthRegimeSignal:
    name = "breadth_regime"
    scode = "s0001x"  # 交付包代号（对齐 deliverables/signals/_REGISTRY.csv）
    universe_hint = "hs800"  # 用沪深800测广度（宽域，代表性好；ALL 更全但更重）
    state_def = ("raw = 每日(上涨家数-下跌家数)/总数；状态 = breadth_MA20 > 0 → risk_on，"
                 "否则 risk_off（20日窗口、阈值0，交付卡片说明）")
    caveat = ("广度在极端流动性枯竭 / 涨跌停潮时会失真（涨跌家数被停牌与封板锁死），"
              "且同期 Sharpe 2.68 远高于滞后口径 0.94，说明高度依赖当日信息——"
              "必须按 exec_lag=1 消费，需结合其他 regime 信号交叉验证。")

    def compute(self, panel: pd.DataFrame, as_of_date, ctx=None) -> float:
        as_of = pd.Timestamp(as_of_date)
        sub = slice_panel_to_date(panel, as_of)  # 双保险：只留 as_of 及之前
        try:
            day = sub.xs(as_of, level="date")
        except KeyError:
            return float("nan")

        prev_dates = [d for d in sub.index.get_level_values("date").unique() if d < as_of]
        if not prev_dates:
            return float("nan")  # 无前一日，无法算涨跌

        prev_close = sub.xs(prev_dates[-1], level="date")["close"]
        prev_close = prev_close.reindex(day.index).dropna()
        if len(prev_close) < 5:
            return float("nan")

        close = day["close"].reindex(prev_close.index)
        adv = float((close > prev_close).sum())
        dec = float((close < prev_close).sum())
        total = float(len(close))
        breadth = (adv - dec) / total if total > 0 else float("nan")
        return float(breadth)


# 注册实例（供 get_signal 取用）
register_signal(BreadthRegimeSignal())
