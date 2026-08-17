"""f0003a 组合构建单元测试（合成因子矩阵，不依赖缓存）。

覆盖：三种方法输出形状/有限性、等权退化、ICIR 权重生效、正交化剔除共线因子。
"""
import numpy as np
import pandas as pd

from scripts.build_combo import (
    combine_equal, combine_icir, combine_orthogonal, _orthogonalize_components,
)


ASSETS = ["A", "B", "C", "D", "E"]
# f2 = 2*f1（共线），f3 独立
MAT = pd.DataFrame(
    {"f1": [1, 2, 3, 4, 5], "f2": [2, 4, 6, 8, 10], "f3": [5, 1, 4, 2, 3]},
    index=ASSETS,
)


def test_equal_shape_finite():
    s = combine_equal(MAT)
    assert s.index.tolist() == ASSETS
    assert s.notna().all()


def test_equal_collapsed_to_single():
    # f1 与 f2 共线 -> z-score 后相同 -> 等权组合 == zscore(f1)
    from factors.interface import zscore_cross_section, winsorize_mad
    z1 = zscore_cross_section(winsorize_mad(MAT["f1"]))
    s = combine_equal(MAT[["f1", "f2"]])
    assert np.allclose(s.values, z1.reindex(ASSETS).values, atol=1e-9)


def test_icir_weights_respected():
    # 权重 [1,0,0] -> 仅 f1 贡献 -> 等于 zscore(f1)
    from factors.interface import zscore_cross_section, winsorize_mad
    z1 = zscore_cross_section(winsorize_mad(MAT["f1"]))
    s = combine_icir(MAT, weights=[1, 0, 0])
    assert np.allclose(s.values, z1.reindex(ASSETS).values, atol=1e-9)


def test_orthogonal_removes_collinear():
    # f2 与 f1 共线 -> 正交化后 f2 成分应≈0
    comps = _orthogonalize_components(MAT)
    assert comps["f2"].abs().max() < 1e-9


def test_orthogonal_shape_finite():
    s = combine_orthogonal(MAT)
    assert s.index.tolist() == ASSETS
    assert s.notna().all()
