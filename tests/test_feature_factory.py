"""特征工厂 C1 单元测试（合成面板，不依赖 baostock 缓存）。

覆盖：注册表规模、已知 mom_20 值、无前视（全量 vs 切片等价）、标准化、缺列安全、可复现。
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from factors.feature_factory import build_feature_matrix, list_features


def make_panel_from_closes(closes, start="2024-01-01"):
    """从 {asset: close_array} 构造合法面板（含 open/high/low/volume/amount/turnover/market_cap）。"""
    dates = pd.bdate_range(start, periods=max(len(v) for v in closes.values()))
    rows = []
    for a, cl in closes.items():
        n = len(cl)
        for i, d in enumerate(dates[:n]):
            c = cl[i]
            rows.append((d, a, c * 0.99, c * 1.02, c * 0.98, c,
                         1e6, 1e6 * c, 0.02, 1e6 * c * 100))
    df = pd.DataFrame(rows, columns=["date", "asset", "open", "high", "low",
                                     "close", "volume", "amount", "turnover", "market_cap"])
    df["date"] = pd.to_datetime(df["date"])
    return df.set_index(["date", "asset"]).sort_index()


def test_registry_size():
    assert len(list_features()) >= 15


def test_mom_20_known_value():
    # 资产 A：每 20 交易日价格翻倍 -> mom_20 应≈1.0；资产 B 平盘 -> ≈0
    closes = {"A": 10 * (2 ** (np.arange(30) / 20)), "B": np.full(30, 10.0)}
    panel = make_panel_from_closes(closes)
    as_of = panel.index.get_level_values("date").max()
    mat = build_feature_matrix(panel, as_of, standardize=False)
    assert abs(mat.loc["A", "mom_20"] - 1.0) < 1e-6
    assert abs(mat.loc["B", "mom_20"] - 0.0) < 1e-9


def test_no_lookahead():
    closes = {"A": 10 * (2 ** (np.arange(30) / 20)), "B": np.full(30, 10.0)}
    panel = make_panel_from_closes(closes)
    as_of = panel.index.get_level_values("date").max()
    mat1 = build_feature_matrix(panel, as_of, standardize=False)
    # 追加 as_of 之后的未来数据（仅 A 多一行）
    last = panel.xs("A", level="asset").index.get_level_values("date")[-1]
    nxt = last + pd.Timedelta(days=1)
    fut = panel.xs("A", level="asset").iloc[[-1]].copy()
    fut.index = pd.MultiIndex.from_tuples([(nxt, "A")], names=["date", "asset"])
    panel2 = pd.concat([panel, fut])
    mat2 = build_feature_matrix(panel2, as_of, standardize=False)
    common = mat1.index.intersection(mat2.index)
    assert np.allclose(mat1.loc[common].values, mat2.loc[common].values, equal_nan=True)


def test_standardize_shape_and_zscore():
    rng = np.random.default_rng(42)
    closes = {f"S{i:02d}": 10 + np.cumsum(rng.normal(0, 0.3, 80)) for i in range(20)}
    panel = make_panel_from_closes(closes)
    as_of = panel.index.get_level_values("date").max()
    mat = build_feature_matrix(panel, as_of, standardize=True)
    assert mat.shape[0] == 20
    for c in mat.columns:
        vals = mat[c].dropna()
        if len(vals) > 1:
            assert abs(vals.mean()) < 1e-9


def test_missing_column_safe():
    # 去掉 open 列，gap 特征应返回 NaN 而不崩溃；mom_20 仍正常
    closes = {"A": np.linspace(10, 20, 40), "B": np.full(40, 10.0)}
    panel = make_panel_from_closes(closes).drop(columns=["open"])
    as_of = panel.index.get_level_values("date").max()
    mat = build_feature_matrix(panel, as_of, feature_names=["gap_overnight", "mom_20"])
    assert "gap_overnight" in mat.columns
    assert mat["gap_overnight"].isna().all()
    assert not mat["mom_20"].isna().all()


def test_reproducible():
    closes = {"A": np.linspace(10, 20, 40), "B": np.full(40, 10.0)}
    panel = make_panel_from_closes(closes)
    as_of = panel.index.get_level_values("date").max()
    m1 = build_feature_matrix(panel, as_of)
    m2 = build_feature_matrix(panel, as_of)
    assert np.allclose(m1.values, m2.values, equal_nan=True)
