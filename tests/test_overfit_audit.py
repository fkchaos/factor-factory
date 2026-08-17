"""DSR / PBO 过拟合审计单元测试（公式 sanity + 边界）。"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from validate.overfit_audit import (
    deflated_sharpe,
    probability_of_backtest_overfit,
    strategy_returns_from_factor,
    audit,
)


# ---- DSR ----
def test_dsr_strong_signal_high():
    rng = np.random.default_rng(42)
    r = rng.normal(0.001, 0.02, 500)  # 正漂移强信号
    assert deflated_sharpe(r, n_trials=5) > 0.90


def test_dsr_random_low():
    rng = np.random.default_rng(7)
    r = rng.normal(0.0, 0.02, 500)  # 随机噪声
    assert deflated_sharpe(r, n_trials=5) < 0.80


def test_dsr_n_trials_penalty():
    rng = np.random.default_rng(1)
    r = rng.normal(0.0005, 0.02, 500)  # 弱信号
    d1 = deflated_sharpe(r, n_trials=10)
    d2 = deflated_sharpe(r, n_trials=1000)
    assert d2 < d1  # 试得越多，门槛越高


def test_dsr_two_trials_no_deflation():
    # n_trials=2 → 基准 SR=0，退化为普通概率夏普（不返回 NaN）
    rng = np.random.default_rng(1)
    r = rng.normal(0.0005, 0.02, 500)
    d = deflated_sharpe(r, n_trials=2)
    assert np.isfinite(d) and 0 < d < 1


def test_dsr_short_series_nan():
    assert np.isnan(deflated_sharpe(np.random.default_rng(0).normal(0, 0.01, 10)))


# ---- PBO ----
def test_pbo_random_matrix_around_half():
    rng = np.random.default_rng(5)
    M = rng.normal(0.0, 0.02, (5, 400))  # 全随机：IS 最优无持续性
    pbo = probability_of_backtest_overfit(M, n_splits=12)
    # 随机矩阵下 PBO 围绕 0.5 波动（400 期×924 组合的抽样波动）；不偏离到极端即可
    assert 0.20 <= pbo <= 0.80


def test_pbo_one_dominant_strategy_low():
    rng = np.random.default_rng(3)
    M = rng.normal(0.0, 0.02, (5, 400))
    M[0] += 0.002  # 策略 0 真实最强 → IS 最优大概率就是它，OOS 持续 → PBO 低
    assert probability_of_backtest_overfit(M, n_splits=12) < 0.30


def test_pbo_too_short_nan():
    M = np.random.default_rng(0).normal(0, 0.01, (3, 30))
    assert np.isnan(probability_of_backtest_overfit(M))


def test_pbo_single_strategy_nan():
    M = np.random.default_rng(0).normal(0, 0.01, (1, 300))
    assert np.isnan(probability_of_backtest_overfit(M))


# ---- strategy_returns_from_factor ----
def test_strategy_returns_topn():
    dates = pd.date_range("2024-01-01", periods=5, freq="D")
    assets = ["000001.SZ", "000002.SZ", "000003.SZ", "000004.SZ", "000005.SZ"]
    fseries = {}
    fwd = {}
    for i, t in enumerate(dates):
        fv = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0], index=assets)
        fr = pd.Series([0.01, 0.02, 0.03, 0.04, 0.05], index=assets)
        fseries[t] = fv
        fwd[t] = fr
    s = strategy_returns_from_factor(fseries, fwd, top_n=2)
    assert len(s) == 5
    # top2 = 最后两只，平均收益 = (0.04+0.05)/2
    assert abs(s.iloc[0] - 0.045) < 1e-9


# ---- audit 综合 ----
def test_audit_verdict_strong():
    rng = np.random.default_rng(11)
    r = rng.normal(0.001, 0.02, 500)
    M = np.vstack([r, rng.normal(0.0, 0.02, 500)])
    res = audit(r, n_trials=5, pbo_matrix=M)
    assert res["verdict"] in ("PASS", "WARN")
    assert res["dsr"] is not None and res["pbo"] is not None


def test_audit_verdict_random_fail():
    rng = np.random.default_rng(12)
    r = rng.normal(0.0, 0.02, 500)
    M = rng.normal(0.0, 0.02, (4, 500))
    res = audit(r, n_trials=5, pbo_matrix=M)
    assert res["verdict"] == "FAIL"
