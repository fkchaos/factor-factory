"""f0003a 组合包构建（第三条腿 c 类：组合/正交创新）。

把多个单因子值（同一 as_of 截面）合成一个组合因子，支持三种方法：
  - equal      : 各因子 z-score 后等权平均（最稳健）
  - icir       : 各因子 z-score 后按 ICIR 绝对值加权（需外部权重或 IC 序列）
  - orthogonal : 逐步正交化（Gram-Schmidt）去冗余后等权合成

前向防护：本模块只做截面组合，输入必须是已切片到 as_of 的因子值；
不引入任何未来数据。与 factors.interface 的预处理纪律一致（先 MAD 去极值再 z-score）。

暂不依赖 hs1800 缓存：组合数学用合成因子矩阵测试；缓存到位后由 build_deliverable
流水线喂入真实因子值即可产出 f0003a 包。
"""
from __future__ import annotations
import os
import sys
from typing import Optional, Sequence

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from factors.interface import winsorize_mad, zscore_cross_section


def _zscore_matrix(mat: pd.DataFrame) -> pd.DataFrame:
    """逐列做 MAD 去极值 + 截面 z-score，缺失列填 NaN。"""
    out = {}
    for c in mat.columns:
        s = mat[c].dropna()
        if len(s) == 0:
            out[c] = pd.Series(np.nan, index=mat.index)
            continue
        out[c] = zscore_cross_section(winsorize_mad(s)).reindex(mat.index)
    return pd.DataFrame(out)


def combine_equal(mat: pd.DataFrame) -> pd.Series:
    """等权组合：z-score 后逐资产平均。"""
    z = _zscore_matrix(mat)
    return z.mean(axis=1, skipna=True).rename("combo_equal")


def combine_icir(mat: pd.DataFrame, weights: Optional[Sequence[float]] = None) -> pd.Series:
    """ICIR 加权组合：各列 z-score 后按权重加权；未给权重则等权。"""
    z = _zscore_matrix(mat)
    if weights is None:
        w = np.ones(z.shape[1]) / max(z.shape[1], 1)
    else:
        w = np.array(weights, dtype=float)
        if w.sum() != 0:
            w = w / w.sum()
    combined = z.mul(w, axis=1).sum(axis=1, skipna=True)
    return combined.rename("combo_icir")


def _orthogonalize_components(mat: pd.DataFrame) -> pd.DataFrame:
    """Gram-Schmidt 逐步正交化：每列对其之前所有正交成分回归取残差。"""
    z = _zscore_matrix(mat)
    comps = {}
    basis = []
    for c in z.columns:
        v = z[c].copy()
        for b in basis:
            df = pd.concat([v, b], axis=1).dropna()
            if len(df) >= 5:
                X = np.column_stack([np.ones(len(df)), df.iloc[:, 1].values])
                beta, *_ = np.linalg.lstsq(X, df.iloc[:, 0].values, rcond=None)
                pred = X @ beta
                v = v.reindex(df.index) - pd.Series(pred, index=df.index)
        comps[c] = v
        basis.append(v)  # 用正交成分作后续基底
    return pd.DataFrame(comps)


def combine_orthogonal(mat: pd.DataFrame) -> pd.Series:
    """正交化组合：逐步去冗余后等权合成正交成分。"""
    comps = _orthogonalize_components(mat)
    return comps.mean(axis=1, skipna=True).rename("combo_orthogonal")
