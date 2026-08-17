"""行业/市值中性化单元测试：剥离风格暴露的正确性。"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from factors.interface import neutralize, winsorize_mad, zscore_cross_section


def test_neutralize_removes_mktcap_correlation():
    """与市值强相关的因子，中性化后与市值相关性应显著下降。"""
    rng = np.random.default_rng(42)
    n = 200
    assets = [f"000{i:03d}.SZ" for i in range(1, n + 1)]
    mcap = rng.lognormal(mean=15, sigma=1.0, size=n)
    factor = 0.8 * np.log(mcap) + rng.normal(0, 0.1, n)  # 因子 ≈ 80% 市值暴露 + 噪声
    f = pd.Series(factor, index=assets)
    log_mc = pd.Series(np.log(mcap), index=assets)

    corr_before = f.rank().corr(log_mc.rank())
    resid = neutralize(f, None, log_mc)
    corr_after = resid.rank().corr(log_mc.rank())

    assert corr_before > 0.8          # 构造上强相关
    assert abs(corr_after) < 0.15     # 中性化后相关性大幅剥离


def test_neutralize_with_industry_dummies():
    """行业哑变量中性化：同一行业内部信号与行业间差异分离。"""
    rng = np.random.default_rng(7)
    n = 120
    assets = [f"000{i:03d}.SZ" for i in range(1, n + 1)]
    industry = [f"IND{i % 4}" for i in range(n)]          # 4 个行业
    dummies = pd.get_dummies(pd.Series(industry, index=assets)).astype(float)
    # 因子 = 行业固定效应(1,2,3,4) + 个体噪声
    fe = {"IND0": 1.0, "IND1": 2.0, "IND2": 3.0, "IND3": 4.0}
    factor = np.array([fe[industry[i]] for i in range(n)]) + rng.normal(0, 0.05, n)
    f = pd.Series(factor, index=assets)
    log_mc = pd.Series(np.log(rng.lognormal(15, 1, n)), index=assets)

    resid = neutralize(f, dummies, log_mc)
    # 残差的行业均值应≈0（行业效应被剥离）
    resid_by_ind = resid.groupby(pd.Series(industry, index=assets)).mean()
    assert resid_by_ind.abs().max() < 0.2


def test_neutralize_pipeline_with_zscore():
    """MAD -> 中性化 -> Z 完整链路可运行且输出有限。"""
    rng = np.random.default_rng(3)
    n = 100
    assets = [f"000{i:03d}.SZ" for i in range(1, n + 1)]
    raw = pd.Series(rng.normal(0, 1, n), index=assets)
    raw.iloc[:5] += 100.0  # 造 5 个极值
    log_mc = pd.Series(np.log(rng.lognormal(15, 1, n)), index=assets)
    out = zscore_cross_section(neutralize(winsorize_mad(raw), None, log_mc))
    assert np.isfinite(out).all()
    assert abs(out.mean()) < 0.01
