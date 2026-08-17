"""Walk-forward 回测引擎实现（WalkForwardEngine）。

对齐 engine.interface：Engine Protocol / BacktestConfig / QuadraticCost / BacktestResult。
成交假设默认 t1_open（下一可用价，禁止 T 日收盘即时成交的乐观假设）。
处理：point-in-time 股票池（停牌/退市自动剔除）、二次冲击成本、流动性约束（单笔 <= 10% ADV）。
涨停/跌停封板处理（近似）：t+1 开盘相对 t 收盘涨超 9.5% 视为涨停买不进，跌超 -9.5% 跌停卖不出。

说明：factor 为无训练参数因子（逻辑固定），walk-forward 的 train 窗口在此仅占位，
保留 WF 结构供未来 ML / 参数化因子复用例（见 docs/ARCHITECTURE.md）。
"""
from __future__ import annotations
from typing import Any

import numpy as np
import pandas as pd

from factors.interface import Factor
from engine.interface import (
    Engine, BacktestConfig, QuadraticCost, BacktestResult, CostModel,
)
from engine.selection import select_targets, execute_rebalance

_DEFAULT_FIELDS = ["open", "high", "low", "close", "volume", "amount"]
_LIMIT_UP = 0.095
_LIMIT_DOWN = -0.095


class WalkForwardEngine(Engine):
    def __init__(self, cost_model: CostModel | None = None):
        self._cost = cost_model or QuadraticCost()

    def _all_dates(self, provider, start=None, end=None):
        panel = provider.get_panel(_DEFAULT_FIELDS, start, end)
        return sorted(panel.index.get_level_values("date").unique())

    def run(self, factor: Factor, provider: Any, config: BacktestConfig) -> BacktestResult:
        dates = self._all_dates(provider)
        N = len(dates)
        if N < config.train_days + 2:
            return BacktestResult(pd.Series(dtype=float), pd.DataFrame(),
                                  {"error": "insufficient data"})

        capital0 = 1_000_000.0
        cash = capital0
        shares: dict[str, float] = {}
        equity_curve: list[tuple] = []
        trades: list[dict] = []

        rebal_freq = max(1, config.step_days)
        i = config.train_days  # 第一个选股日需 train 预热
        while i < N - 1:
            t = dates[i]
            ctx = {"start": str(dates[max(0, i - config.train_days)])}
            target = select_targets(provider, factor, t, dates, config, ctx, self._cost)
            # 成交日 = t+1 开盘
            j = i + 1
            t1 = dates[j]
            shares, cash, new_trades = execute_rebalance(
                shares, cash, target, t1, provider, self._cost, capital0, config.max_participation)
            trades.extend(new_trades)

            # 持有到下一 rebalance，期间每日按 close 估值
            next_i = min(i + rebal_freq, N - 1)
            for k in range(i, next_i + 1):
                tk = dates[k]
                closes = provider.get_panel(["close"], str(tk), str(tk)).xs(tk, level="date")["close"]
                pos_val = 0.0
                for a, sh in shares.items():
                    cp = closes.get(a, np.nan)
                    if np.isfinite(cp):
                        pos_val += sh * cp
                equity_curve.append((tk, cash + pos_val))
            i = next_i + 1

        eq = pd.Series(dict(equity_curve)).sort_index()
        eq.name = "equity"
        metrics = self._metrics(eq, capital0)
        return BacktestResult(eq, pd.DataFrame(trades), metrics)

    def _metrics(self, eq: pd.Series, capital0: float) -> dict:
        if len(eq) < 2:
            return {"total_return": np.nan, "sharpe": np.nan, "max_drawdown": np.nan, "n_days": 0}
        rets = eq.pct_change().dropna()
        total = eq.iloc[-1] / capital0 - 1.0
        sharpe = rets.mean() / rets.std() * np.sqrt(252) if rets.std() > 0 else np.nan
        dd = (eq - eq.cummax()) / eq.cummax()
        return {
            "total_return": float(total),
            "sharpe": float(sharpe) if np.isfinite(sharpe) else np.nan,
            "max_drawdown": float(dd.min()),
            "n_days": int(len(eq)),
        }
