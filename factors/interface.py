"""Factor 接口契约 + 预处理三件套 + 注册表 + 前视防护。

设计要点（见 ADR-0001 / RESEARCH_LOG R2026-0804-02,04）：
- Factor 以"可调用接口"声明（对齐 Qlib 表达式思想），新增因子 = 实现接口 + 注册，零改核心。
- **as_of_date 是防前视的契约参数**：引擎保证传入的 panel 只含 as_of_date 及之前数据；
  因子实现不得自行取全样本（见 assert_no_lookahead，CI 强制）。
- 预处理三件套（MAD 去极值 -> 截面 Z-score -> 行业/市值中性化）逐截面日执行，
  禁止用全样本统计量（全局均值/标准差 = 回测作弊）。
"""
from __future__ import annotations
from typing import Protocol, runtime_checkable, Optional, Any
import pandas as pd
import numpy as np


# ---------- 面板工具：按日期切片（前视防护基础） ----------

def slice_panel_to_date(panel: pd.DataFrame, as_of_date) -> pd.DataFrame:
    """只保留 level='date' <= as_of_date 的行。面板为 MultiIndex(date, asset)。"""
    as_of_date = pd.Timestamp(as_of_date)
    dates = panel.index.get_level_values("date")
    return panel.loc[dates <= as_of_date]


# ---------- 预处理三件套（逐截面日，禁止全局统计） ----------

def winsorize_mad(s: pd.Series, n: float = 3.0) -> pd.Series:
    """MAD 去极值：比 3σ 更抗极端值。"""
    med = s.median()
    mad = (s - med).abs().median()
    if mad == 0 or np.isnan(mad):
        return s
    scale = 1.4826 * mad
    return s.clip(med - n * scale, med + n * scale)


def zscore_cross_section(s: pd.Series) -> pd.Series:
    """截面 Z-score：每个交易日 t 独立计算均值/标准差。"""
    std = s.std()
    if std == 0 or np.isnan(std):
        return pd.Series(0.0, index=s.index)
    return (s - s.mean()) / std


def neutralize(factor: pd.Series, industry_dummies: Optional[pd.DataFrame],
               log_mktcap: pd.Series) -> pd.Series:
    """行业 + 对数市值中性化：回归取残差，剥离风格暴露。

    industry_dummies 可为 None（仅市值中性化）；两者都缺时调用方应直接跳过。
    """
    parts = []
    if industry_dummies is not None and len(industry_dummies.columns):
        parts.append(industry_dummies)
    parts.append(log_mktcap.rename("log_mktcap"))
    parts.append(pd.Series(1.0, index=factor.index, name="const"))
    X = pd.concat(parts, axis=1).loc[factor.index]
    beta, *_ = np.linalg.lstsq(X.values, factor.values, rcond=None)
    return pd.Series(factor.values - X.values @ beta, index=factor.index)


# ---------- Factor 接口 + 注册表 ----------

_REGISTRY: dict[str, Any] = {}


@runtime_checkable
class Factor(Protocol):
    """因子接口。compute 必须用 as_of_date 及之前的数据。"""
    name: str
    # 可选：声明因子的"主场"池子（sz50/hs300/hs800/ALL 等）。
    # 由 scripts/factor_universe_matrix.py 校验声明与实测 IC 矩阵是否一致；
    # None = 未声明（矩阵跑完按实测结果回填）。
    universe_hint: Optional[str] = None

    def compute(self, panel: pd.DataFrame, as_of_date, ctx: Optional[dict] = None) -> pd.Series:
        """返回以 asset 为索引的因子值（已切片到 as_of_date）。"""
        ...


def register_factor(factor: Factor) -> Factor:
    _REGISTRY[factor.name] = factor
    return factor


def get_factor(name: str) -> Factor:
    return _REGISTRY[name]


def list_factors() -> list[str]:
    return list(_REGISTRY.keys())


# ---------- 前视防护：CI 强制校验 ----------

class LookaheadError(Exception):
    """因子在给定 as_of_date 时使用了未来数据。"""


def assert_no_lookahead(factor: Factor, panel: pd.DataFrame,
                        as_of_date, ctx: Optional[dict] = None) -> bool:
    """对因子做前视审计：分别用『全量面板』与『已切片面板』喂给 factor.compute，
    若输出不同，说明因子偷偷用了未来数据 -> 抛 LookaheadError。

    这是 CI 门禁：任何新因子合并前必须通过此测试（对应计划里的前视防护专项测试）。
    """
    out_full = factor.compute(panel, as_of_date, ctx)
    sliced = slice_panel_to_date(panel, as_of_date)
    out_sliced = factor.compute(sliced, as_of_date, ctx)
    common = out_full.index.intersection(out_sliced.index)
    if len(common) == 0:
        raise LookaheadError(f"Factor {getattr(factor, 'name', factor)}: no overlap after slicing")
    if not np.allclose(out_full.loc[common].values, out_sliced.loc[common].values, equal_nan=True):
        raise LookaheadError(
            f"Factor {getattr(factor, 'name', factor)} produced different output when "
            f"future data removed -> look-ahead bias detected"
        )
    return True
