"""Engine 接口契约 + 成本模型 + 回测配置。

设计要点（见 ADR-0001 / RESEARCH_LOG R2026-0804-02,05）：
- Engine 只认 Factor + DataProvider 接口；内部 walk-forward，调用 CostModel 算真实成本。
- 成交假设默认 t1_open（Next-Available-Price，对齐 Alphalens 规则），禁止 T 日收盘即时成交的乐观假设。
- 成本显式可配置：CostModel 为独立接口，引擎不得写死成本。
- 处理涨跌停封板、停牌、退市（对齐数据层 point-in-time 股票池）。
"""
from __future__ import annotations
from typing import Protocol, runtime_checkable, Any, Optional
from dataclasses import dataclass, field
import pandas as pd
from factors.interface import Factor, slice_panel_to_date


@runtime_checkable
class CostModel(Protocol):
    """交易成本模型接口。cost 返回单笔交易的成本比率（占成交额）。"""
    def cost(self, trade_volume: float, adv: float, side: str) -> float:
        ...


@dataclass
class QuadraticCost(CostModel):
    """二次冲击成本 + 最低佣金（默认实现）。

    成本 ~ (trade_vol / ADV)^2 * impact_coef + commission，并对单笔设最低佣金下限。
    低流动性小票（v61b 类）真实冲击远高于固定滑点，故用二次型。
    """
    impact_coef: float = 0.1
    commission: float = 0.0003
    min_commission: float = 5.0  # 元，单笔最低
    adv_window: int = 20

    def cost(self, trade_volume: float, adv: float, side: str) -> float:
        if adv <= 0:
            return self.commission
        particip_rate = trade_volume / adv
        impact = (particip_rate ** 2) * self.impact_coef
        return max(impact + self.commission, self.commission)


@dataclass
class BacktestConfig:
    train_days: int = 252
    test_days: int = 126
    step_days: int = 63
    top_n: int = 10
    cost_model: str = "quadratic"          # 由 CostModel 注册表解析
    execution: str = "t1_open"             # next-available-price
    max_participation: float = 0.10        # 单笔 <= 10% ADV（流动性约束）


@dataclass
class BacktestResult:
    equity_curve: pd.Series
    trades: pd.DataFrame
    metrics: dict


@dataclass
class ShadowConfig:
    """影子账户（方案 A：纯回测影子）配置。"""
    warmup_days: int = 252           # 因子数据预热起点
    train_days: int = 252            # 因子切片参考窗口（ctx.start）
    rebal_days: int = 5              # 调仓周期（交易日）
    top_n: int = 10
    cost_model: str = "quadratic"
    execution: str = "t1_open"
    max_participation: float = 0.10  # 单笔 <= 10% ADV
    capital0: float = 1_000_000.0


@dataclass
class ShadowResult:
    equity_curve: pd.Series
    holdings: list                    # list of (rebal_date, target_dict)
    turnover_log: list               # list of (rebal_date, turnover_ratio)
    metrics: dict


@runtime_checkable
class Engine(Protocol):
    def run(self, factor: Factor, provider: Any, config: BacktestConfig) -> BacktestResult:
        ...


def prepare_panel_for_factor(provider, factor: Factor, as_of_date, fields, ctx=None):
    """引擎内部：取全窗口面板，切到 as_of_date 再喂给 factor（前视防护第一道）。"""
    panel = provider.get_panel(fields, start=ctx.get("start") if ctx else None, end=str(as_of_date))
    return slice_panel_to_date(panel, as_of_date)
