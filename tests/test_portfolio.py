"""组合合成层测试：CompositeFactor 前视审计 + 引擎跑通。

无需联网（LocalProvider 确定性合成数据）。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

from data.providers import LocalProvider
from factors.overnight_intraday import OvernightIntradayFactor
from factors.ivol import IvolFactor
from factors.interface import assert_no_lookahead
from portfolio.combiner import CompositeFactor, combine_factors
from engine.engine_impl import WalkForwardEngine
from engine.interface import BacktestConfig, QuadraticCost


def test_composite_lookahead_clean():
    prov = LocalProvider(seed=7)
    comp = CompositeFactor([OvernightIntradayFactor(), IvolFactor()])
    panel = prov.get_panel(["open", "high", "low", "close", "volume", "amount"], None, None)
    t = panel.index.get_level_values("date").unique()[100]
    assert assert_no_lookahead(comp, panel, t) is True


def test_composite_engine_runs():
    prov = LocalProvider(seed=7)
    cfg = BacktestConfig(train_days=60, test_days=20, step_days=20, top_n=5,
                         cost_model="quadratic", execution="t1_open")
    comp = combine_factors([OvernightIntradayFactor(), IvolFactor()],
                           provider=prov, config=cfg, method="icir")
    eng = WalkForwardEngine(QuadraticCost())
    res = eng.run(comp, prov, cfg)
    assert len(res.equity_curve) > 0
    assert np.isfinite(res.metrics.get("total_return", np.nan))
    assert res.metrics["n_days"] > 0


def test_equal_vs_icir_weights_finite():
    prov = LocalProvider(seed=7)
    cfg = BacktestConfig(train_days=60, test_days=20, step_days=20, top_n=5)
    eq = combine_factors([OvernightIntradayFactor(), IvolFactor()], method="equal")
    ic = combine_factors([OvernightIntradayFactor(), IvolFactor()],
                         provider=prov, config=cfg, method="icir")
    assert np.all(np.isfinite(eq._weights))
    assert np.all(np.isfinite(ic._weights))
    assert abs(eq._weights.sum() - 1.0) < 1e-9
    assert abs(ic._weights.sum() - 1.0) < 1e-9
