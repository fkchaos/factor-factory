"""影子账户（方案 A：纯回测影子，不接券商）。

语义：固定因子参数（已冻结），滚动调仓持有（rebal_days），模拟真实持仓跟踪。
不重新训练（区别于 WalkForwardEngine 的 train/test 结构），更贴近实盘持仓观察与 1-3 月跟踪。

复用 engine.selection 的 select_targets + execute_rebalance，保证选股 / 成交语义与回测一致。
外部券商环境（QMT / PTrade 模拟盘，方案 B）就绪后再扩展（见 docs/dev/HANDOFF.md 待决策清单）。

前视防护：ShadowAccount 信任 factor.compute 遵守 as_of_date 契约（由 Factor 接口 + CI 审计保证），
自身不再重复审计，避免与因子层职责重叠。
"""
from __future__ import annotations
from typing import Any, Optional
import numpy as np
import pandas as pd
from factors.interface import Factor
from engine.interface import ShadowConfig, ShadowResult, QuadraticCost, CostModel
from engine.selection import select_targets, execute_rebalance


class ShadowAccount:
    def __init__(self, cost_model: Optional[CostModel] = None):
        self._cost = cost_model or QuadraticCost()

    def run(self, factor: Factor, provider: Any, config: ShadowConfig) -> ShadowResult:
        dates = sorted(provider.get_panel(["close"], None, None).index.get_level_values("date").unique())
        N = len(dates)
        if N < config.warmup_days + 2:
            return ShadowResult(pd.Series(dtype=float), [], [], {"error": "insufficient data"})
        capital0 = config.capital0
        cash = capital0
        shares: dict[str, float] = {}
        equity_curve: list[tuple] = []
        holdings: list[tuple] = []
        turnover_log: list[tuple] = []
        trades: list[dict] = []

        i = config.warmup_days
        while i < N - 1:
            t = dates[i]
            ctx = {"start": str(dates[max(0, i - config.train_days)])}
            target = select_targets(provider, factor, t, dates, config, ctx, self._cost)
            j = i + 1
            t1 = dates[j]
            shares, cash, new_trades = execute_rebalance(
                shares, cash, target, t1, provider, self._cost, capital0, config.max_participation)
            trades.extend(new_trades)
            # 换手率（该期单边近似）：买卖总额 / 组合市值
            traded = sum(abs(tr["price"] * tr["shares"]) for tr in new_trades)
            turnover = traded / (2.0 * capital0) if capital0 > 0 else 0.0
            turnover_log.append((str(t1), float(turnover)))
            holdings.append((str(t1), dict(target)))
            # 持有到下次调仓，每日估值
            next_i = min(i + config.rebal_days, N - 1)
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
        metrics = self._metrics(eq, capital0, turnover_log, provider,
                                dates[config.warmup_days], dates[-1])
        return ShadowResult(eq, holdings, turnover_log, metrics)

    @staticmethod
    def _metrics(eq, capital0, turnover_log, provider, start, end):
        if len(eq) < 2:
            return {"total_return": np.nan, "sharpe": np.nan, "max_drawdown": np.nan,
                    "n_days": 0, "avg_turnover": 0.0, "n_rebalances": len(turnover_log),
                    "benchmark_return": np.nan}
        rets = eq.pct_change().dropna()
        total = eq.iloc[-1] / capital0 - 1.0
        sharpe = rets.mean() / rets.std() * np.sqrt(252) if rets.std() > 0 else np.nan
        dd = (eq - eq.cummax()) / eq.cummax()
        avg_to = float(np.mean([x[1] for x in turnover_log])) if turnover_log else 0.0
        # benchmark（指数对比，缺失则降级为 None，不阻塞）
        try:
            bench = provider.get_index_returns(str(start), str(end))
            if bench is not None and len(bench) > 1 and bench.iloc[0] != 0:
                bench_ret = float(bench.iloc[-1] / bench.iloc[0] - 1.0)
            else:
                bench_ret = np.nan
        except Exception:
            bench_ret = np.nan
        return {
            "total_return": float(total),
            "sharpe": float(sharpe) if np.isfinite(sharpe) else np.nan,
            "max_drawdown": float(dd.min()),
            "n_days": int(len(eq)),
            "avg_turnover": avg_to,
            "n_rebalances": len(turnover_log),
            "benchmark_return": bench_ret if np.isfinite(bench_ret) else np.nan,
        }
