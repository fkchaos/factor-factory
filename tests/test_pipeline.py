"""Phase 2 端到端冒烟测试：LocalProvider + OvernightIntradayFactor + WalkForwardEngine + Validator。

无需联网、无第三方行情依赖（LocalProvider 生成确定性合成数据）。
验证：前视防护通过、回测不报错且净值合理、因子产出有限 RankIC。
"""
import os
import sys

# 确保 factor-factory 根在 sys.path（无论 pytest 配置如何）
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pandas as pd

from data.providers import LocalProvider
from factors.overnight_intraday import OvernightIntradayFactor
from factors.interface import assert_no_lookahead
from engine.engine_impl import WalkForwardEngine
from engine.interface import BacktestConfig, QuadraticCost
from validate.validator import validate_factor


def test_lookahead_clean_in_pipeline():
    prov = LocalProvider(seed=7)
    f = OvernightIntradayFactor()
    panel = prov.get_panel(["open", "high", "low", "close", "volume", "amount"], None, None)
    t = panel.index.get_level_values("date").unique()[100]
    assert assert_no_lookahead(f, panel, t) is True


def test_engine_runs_and_produces_equity():
    prov = LocalProvider(seed=7)
    f = OvernightIntradayFactor()
    cfg = BacktestConfig(train_days=60, test_days=20, step_days=20, top_n=5,
                         cost_model="quadratic", execution="t1_open")
    eng = WalkForwardEngine(QuadraticCost())
    res = eng.run(f, prov, cfg)
    assert len(res.equity_curve) > 0
    assert res.equity_curve.notna().all()
    assert np.isfinite(res.metrics.get("total_return", np.nan))
    assert res.metrics["n_days"] > 0


def test_validator_produces_metrics():
    prov = LocalProvider(seed=7)
    f = OvernightIntradayFactor()
    cfg = BacktestConfig(train_days=60, test_days=20, step_days=20, top_n=5)
    m = validate_factor(f, prov, cfg)
    assert "rank_ic" in m
    assert np.isfinite(m["rank_ic"])
    assert m["n_obs"] > 0
    assert len(m["quantile_returns"]) == 5


def test_ivol_lookahead_clean():
    from factors.ivol import IvolFactor
    prov = LocalProvider(seed=7)
    f = IvolFactor()
    panel = prov.get_panel(["open", "high", "low", "close", "volume", "amount"], None, None)
    t = panel.index.get_level_values("date").unique()[100]
    assert assert_no_lookahead(f, panel, t) is True


def test_ivol_engine_runs():
    from factors.ivol import IvolFactor
    prov = LocalProvider(seed=7)
    f = IvolFactor()
    cfg = BacktestConfig(train_days=60, test_days=20, step_days=20, top_n=5,
                         cost_model="quadratic", execution="t1_open")
    eng = WalkForwardEngine(QuadraticCost())
    res = eng.run(f, prov, cfg)
    assert len(res.equity_curve) > 0
    assert np.isfinite(res.metrics.get("total_return", np.nan))
    assert res.metrics["n_days"] > 0
