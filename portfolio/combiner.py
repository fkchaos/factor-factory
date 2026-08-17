"""组合合成层（portfolio）：多因子正交 + 加权 -> 组合因子。

设计（对齐 RESEARCH_LOG R2026-0804-02 与计划「先正交、再合成」）：
- CompositeFactor 实现 Factor 接口，可无缝接入 WalkForwardEngine（engine 调 compute）。
- 合成前先对每因子施加预处理三件套（MAD 去极值 -> 截面 Z），保证可比。
- 加权：等权（最稳健）或 ICIR 加权（用 validator 算各因子 ICIR 取绝对值作权重）。
- 正交化（去冗余）：可选对「基准因子」逐步回归取残差，剥离因子间相互暴露；
  首版提供 simple_orthogonalize（对首个因子回归残差），完整多因子逐步回归留作增强。

前视防护：CompositeFactor.compute 仅转发 engine 已切片到 as_of 的 panel 给子因子，
子因子各自通过 assert_no_lookahead；组合层不额外引入未来数据。
"""
from __future__ import annotations

from typing import Optional, Sequence

import numpy as np
import pandas as pd

from factors.interface import Factor, winsorize_mad, zscore_cross_section


class CompositeFactor:
    name = "composite"

    def __init__(self, factors: Sequence[Factor], weights: Optional[Sequence[float]] = None):
        self._factors = list(factors)
        if weights is None:
            weights = [1.0 / len(self._factors)] * len(self._factors)
        self._weights = np.array(weights, dtype=float)
        if self._weights.sum() != 0:
            self._weights = self._weights / self._weights.sum()

    def compute(self, panel: pd.DataFrame, as_of_date, ctx=None) -> pd.Series:
        scored = []
        for f in self._factors:
            s = f.compute(panel, as_of_date, ctx).dropna()
            if len(s) == 0:
                continue
            scored.append(zscore_cross_section(winsorize_mad(s)))

        if not scored:
            return pd.Series(dtype=float, name=self.name)

        common = scored[0].index
        for s in scored[1:]:
            common = common.intersection(s.index)
        if len(common) == 0:
            return pd.Series(dtype=float, name=self.name)

        combined = None
        for w, s in zip(self._weights, scored):
            v = s.reindex(common).fillna(0.0) * w
            combined = v if combined is None else combined + v
        return combined.rename(self.name)


def simple_orthogonalize(target: pd.Series, base: pd.Series) -> pd.Series:
    """对 base 回归取残差，剥离 target 对 base 的线性暴露（去冗余）。"""
    df = pd.concat([target, base], axis=1).dropna()
    df.columns = ["t", "b"]
    if len(df) < 5:
        return target
    X = np.column_stack([np.ones(len(df)), df["b"].values])
    y = df["t"].values
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    resid = y - X @ beta
    return pd.Series(resid, index=df.index)


def compute_weights_icir(factors: Sequence[Factor], provider, config) -> np.ndarray:
    """用 validator 算各因子 ICIR，取绝对值作权重（因子已反向定义，用 abs 避免方向抵消）。"""
    from validate.validator import validate_factor
    icirs = []
    for f in factors:
        try:
            m = validate_factor(f, provider, config)
            ic = m.get("icir", np.nan)
        except Exception:
            ic = np.nan
        icirs.append(abs(ic) if np.isfinite(ic) else 0.0)
    w = np.array(icirs, dtype=float)
    if w.sum() == 0:
        w = np.ones(len(factors))
    return w / w.sum()


def combine_factors(factors: Sequence[Factor], provider=None, config=None,
                    method: str = "equal") -> CompositeFactor:
    """合成组合因子。method='equal' 等权；method='icir' 用 ICIR 绝对值加权（需 provider+config）。"""
    if method == "icir" and provider is not None:
        w = compute_weights_icir(factors, provider, config)
        return CompositeFactor(factors, w)
    return CompositeFactor(factors)
