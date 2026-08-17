"""共享选股与调仓执行逻辑（WalkForwardEngine 与 ShadowAccount 共用）。

设计（见 ADR-0001 / 解耦原则）：
- select_targets：前视安全选股（T 日信号 -> T+1 开盘成交候选），过滤涨停买不进 / 跌停卖不出 / 停牌。
- execute_rebalance：在 T+1 开盘执行调仓（清仓不在目标的 + 等权买入目标），应用二次冲击成本与流动性约束。

两者复用 prepare_panel_for_factor（前视切片）与 QuadraticCost，保证 WF 与影子账户选股语义完全一致，
避免两套选股逻辑漂移（这也是 v61b 类"隐式约定"陷阱的来源，集中一处更易审计）。
"""
from __future__ import annotations
from typing import Any, Optional
import numpy as np
import pandas as pd
from factors.interface import Factor
from engine.interface import BacktestConfig, CostModel, QuadraticCost, prepare_panel_for_factor

_FIELDS = ["open", "high", "low", "close", "volume", "amount"]
_LIMIT_UP = 0.095
_LIMIT_DOWN = -0.095


def select_targets(provider, factor: Factor, as_of_date, dates, config: BacktestConfig,
                   ctx: dict, cost: Optional[CostModel] = None) -> dict[str, float]:
    """返回 {asset: t+1 开盘价}（已过滤停牌 / 涨停买不进 / 跌停卖不出）。

    as_of_date = T 日（信号日）；成交价取 T+1 开盘（合法假设，非前视）。
    因子计算只用 prepare_panel_for_factor 切到 as_of_date 的窗口。
    """
    cost = cost or QuadraticCost()
    panel_t = prepare_panel_for_factor(provider, factor, as_of_date, _FIELDS, ctx)
    fv = factor.compute(panel_t, as_of_date, ctx).dropna()
    univ = set(provider.list_universe(str(as_of_date)))
    ranked = fv[fv.index.isin(univ)].sort_values(ascending=False)
    picks = ranked.head(config.top_n).index.tolist()

    idx = dates.index(pd.Timestamp(as_of_date))
    if idx + 1 >= len(dates):
        return {}
    t1 = dates[idx + 1]
    open_t1 = provider.get_panel(["open"], str(t1), str(t1)).xs(t1, level="date")["open"]
    close_t = provider.get_panel(["close"], str(as_of_date), str(as_of_date)).xs(
        pd.Timestamp(as_of_date), level="date")["close"]
    target: dict[str, float] = {}
    for a in picks:
        if a not in open_t1.index:
            continue
        price = open_t1[a]
        if not np.isfinite(price) or price <= 0:
            continue
        prev_close = close_t.get(a, np.nan)
        if np.isfinite(prev_close) and prev_close > 0:
            gap = price / prev_close - 1.0
            if gap > _LIMIT_UP or gap < _LIMIT_DOWN:
                continue
        target[a] = price
    return target


def execute_rebalance(shares: dict[str, float], cash: float, target: dict[str, float],
                      t1, provider, cost: CostModel, capital0: float,
                      max_participation: float) -> tuple[dict[str, float], float, list[dict]]:
    """在 t1 开盘执行调仓：清仓不在 target 的、等权买入 target。

    返回 (new_shares, new_cash, trades)。应用二次冲击成本 + 单笔 <= max_participation*ADV 流动性约束。
    """
    trades: list[dict] = []
    open_t1 = provider.get_panel(["open"], str(t1), str(t1)).xs(t1, level="date")["open"]
    adv_t1 = provider.get_adv(str(t1))
    # 清仓不在目标的
    for a, sh in list(shares.items()):
        if a not in target:
            price = open_t1.get(a, np.nan)
            if np.isfinite(price) and price > 0:
                adv = adv_t1.get(a, np.nan)
                adv = adv if np.isfinite(adv) else 0.0
                c = cost.cost(sh, adv, "sell")
                cash += sh * price * (1.0 - c)
                trades.append({"date": str(t1), "asset": a, "side": "sell",
                               "price": float(price), "shares": float(sh), "cost": float(c)})
            del shares[a]
    # 等权买入目标
    if target:
        w = 1.0 / len(target)
        for a, price in target.items():
            adv = adv_t1.get(a, np.nan)
            adv = adv if np.isfinite(adv) else 0.0
            budget = capital0 * w
            vol = budget / price
            if adv > 0:
                vol = min(vol, max_participation * adv)
            if vol <= 0:
                continue
            c = cost.cost(vol, adv, "buy")
            cost_amt = vol * price * c
            if cost_amt >= cash:
                continue
            cash -= vol * price + cost_amt
            shares[a] = shares.get(a, 0.0) + vol
            trades.append({"date": str(t1), "asset": a, "side": "buy",
                           "price": float(price), "shares": float(vol), "cost": float(c)})
    return shares, cash, trades
