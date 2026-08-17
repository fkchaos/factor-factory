"""因子冗余 / 正交化检查（组合流水线必要环节）。

设计（对齐计划「先正交、再合成」）：
- 对每个因子逐日截面因子值（经 MAD 去极值 + 截面 Z-score，与 validator 一致预处理）
- 取末日横截面对齐 -> Spearman 相关性矩阵
- |ρ| >= 0.6 视为高冗余，建议剔除其一（避免「10 个因子其实都是小市值」）

见 ADR-0001 / RESEARCH_LOG（防御过拟合：冗余剔除）。
"""
from __future__ import annotations
from typing import Any, Optional

import numpy as np
import pandas as pd

from factors.interface import Factor, winsorize_mad, zscore_cross_section
from engine.interface import BacktestConfig, prepare_panel_for_factor


def snapshot_factors(factors: list[Factor], provider: Any,
                     config: Optional[BacktestConfig] = None) -> pd.DataFrame:
    """收集各因子在末日的横截面因子值（与 validator 一致预处理），返回 asset×因子 DataFrame。"""
    config = config or BacktestConfig()
    fields = ["open", "high", "low", "close", "volume", "amount"]
    panel = provider.get_panel(fields, None, None)
    dates = sorted(panel.index.get_level_values("date").unique())
    if not dates:
        return pd.DataFrame()
    as_of = dates[-1]
    ctx = {"start": str(dates[max(0, len(dates) - config.train_days)])}
    cols = {}
    for f in factors:
        sub = prepare_panel_for_factor(provider, f, as_of, fields, ctx)
        fv = f.compute(sub, as_of, ctx).dropna()
        fv = zscore_cross_section(winsorize_mad(fv))
        cols[f.name] = fv
    return pd.DataFrame(cols)


def correlation_matrix(snapshot: pd.DataFrame) -> pd.DataFrame:
    """Spearman 相关系数矩阵（横截面相关性快照）。"""
    return snapshot.corr(method="spearman")


def report_redundancy(matrix: pd.DataFrame, threshold: float = 0.6) -> list[tuple]:
    """返回 |ρ| >= threshold 的因子对列表 [(name_a, name_b, rho)]。"""
    pairs = []
    cols = list(matrix.columns)
    for i in range(len(cols)):
        for j in range(i + 1, len(cols)):
            r = matrix.iloc[i, j]
            if np.isfinite(r) and abs(r) >= threshold:
                pairs.append((cols[i], cols[j], round(float(r), 3)))
    return pairs
