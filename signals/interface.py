"""Signal 接口契约 + 注册表 + 前视防护（时序信号线）。

设计要点（与 factors/interface.py 平行，见 docs/PLAN_SIGNAL_LINE.md）：
- Signal 以"可调用接口"声明（对齐 Factor 思想），新增信号 = 实现接口 + 注册，零改核心。
- **as_of_date 是防前视的契约参数**：引擎保证传入的 panel 只含 as_of_date 及之前数据；
  信号实现不得自行取全样本。
- 与 Factor 的关键差异：Signal.compute 返回**市场级状态标量**（对所有 asset 聚合后的单一值），
  而非逐 asset 的因子值。这是"时序信号 vs 横截面因子"的本质分界。
"""
from __future__ import annotations
from typing import Protocol, runtime_checkable, Optional, Any
import pandas as pd
import numpy as np


# ---------- 面板工具：按日期切片（前视防护基础，与因子线共用逻辑） ----------

def slice_panel_to_date(panel: pd.DataFrame, as_of_date) -> pd.DataFrame:
    """只保留 level='date' <= as_of_date 的行。面板为 MultiIndex(date, asset)。"""
    as_of_date = pd.Timestamp(as_of_date)
    dates = panel.index.get_level_values("date")
    return panel.loc[dates <= as_of_date]


# ---------- Signal 接口 + 注册表 ----------

_REGISTRY: dict[str, Any] = {}


@runtime_checkable
class Signal(Protocol):
    """时序信号接口。compute 必须用 as_of_date 及之前的数据，返回市场级状态标量。"""
    name: str
    # 可选：信号主场池（计算状态用的股票池，如 hs800 / ALL）。
    universe_hint: Optional[str] = None
    # 可选：状态定义（连续值 → 离散状态的阈值说明，交付卡片引用）。
    state_def: Optional[str] = None

    def compute(self, panel: pd.DataFrame, as_of_date, ctx: Optional[dict] = None) -> float:
        """返回 as_of_date 当日的**市场级状态标量**。

        实现内对当日 panel 做横截面聚合（如涨跌家数占比、指数 vs MA），
        必须只使用 as_of_date 及之前的数据（防前视）。
        """
        ...


def register_signal(signal: Signal) -> Signal:
    _REGISTRY[signal.name] = signal
    return signal


def get_signal(name: str) -> Signal:
    return _REGISTRY[name]


def list_signals() -> list[str]:
    return list(_REGISTRY.keys())


# ---------- 前视防护：CI 强制校验（与因子线同机制） ----------

class LookaheadError(Exception):
    """信号在给定 as_of_date 时使用了未来数据。"""


def assert_no_lookahead(signal: Signal, panel: pd.DataFrame,
                        as_of_date, ctx: Optional[dict] = None) -> bool:
    """对信号做前视审计：分别用『全量面板』与『已切片面板』喂给 signal.compute，
    若输出不同，说明信号偷偷用了未来数据 -> 抛 LookaheadError。

    CI 门禁：任何新信号合并前必须通过此测试。
    """
    out_full = signal.compute(panel, as_of_date, ctx)
    sliced = slice_panel_to_date(panel, as_of_date)
    out_sliced = signal.compute(sliced, as_of_date, ctx)
    if not np.isfinite(out_full) or not np.isfinite(out_sliced):
        # 标量信号：至少 NaN 一致性要保住（全量/切片都 NaN 视为通过）
        if np.isnan(out_full) and np.isnan(out_sliced):
            return True
        raise LookaheadError(
            f"Signal {getattr(signal, 'name', signal)}: NaN 不一致（全量={out_full}, 切片={out_sliced}）"
        )
    if not np.isclose(out_full, out_sliced, equal_nan=True):
        raise LookaheadError(
            f"Signal {getattr(signal, 'name', signal)} produced different output when "
            f"future data removed -> look-ahead bias detected"
        )
    return True
