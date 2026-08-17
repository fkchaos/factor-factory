"""ShadowAccount（方案 A：纯回测影子账户）测试。"""
import numpy as np
import pandas as pd
from data.providers import LocalProvider
from factors.overnight_intraday import OvernightIntradayFactor
from factors.ivol import IvolFactor
from portfolio.combiner import combine_factors
from engine.interface import BacktestConfig, ShadowConfig
from engine.engine_impl import WalkForwardEngine
from engine.selection import select_targets
from portfolio.shadow_account import ShadowAccount


def _dates(provider):
    return sorted(provider.get_panel(["close"], None, None).index.get_level_values("date").unique())


def test_select_targets_returns_valid_dict():
    prov = LocalProvider(seed=7)
    f = OvernightIntradayFactor()
    cfg = ShadowConfig(warmup_days=60, top_n=5)
    dates = _dates(prov)
    t = dates[60]
    target = select_targets(prov, f, t, dates, cfg, {"start": str(dates[0])})
    assert isinstance(target, dict)
    assert 0 < len(target) <= cfg.top_n
    assert all(np.isfinite(p) and p > 0 for p in target.values())


def test_shadow_account_runs_and_metrics_finite():
    prov = LocalProvider(seed=7)
    comp = combine_factors(
        [OvernightIntradayFactor(), IvolFactor()],
        provider=prov,
        config=BacktestConfig(train_days=60, test_days=20, step_days=20, top_n=5),
        method="icir",
    )
    cfg = ShadowConfig(warmup_days=60, rebal_days=5, top_n=5)
    res = ShadowAccount().run(comp, prov, cfg)
    assert len(res.equity_curve) > 0
    assert np.isfinite(res.metrics["total_return"])
    assert np.isfinite(res.metrics["sharpe"])
    assert res.metrics["n_rebalances"] > 0
    assert res.metrics["avg_turnover"] >= 0.0
    assert len(res.holdings) == res.metrics["n_rebalances"]


def test_shadow_and_wf_both_run():
    prov = LocalProvider(seed=7)
    f = OvernightIntradayFactor()
    cfg_bt = BacktestConfig(train_days=60, test_days=20, step_days=20, top_n=5)
    cfg_sh = ShadowConfig(warmup_days=60, rebal_days=20, top_n=5)
    wf = WalkForwardEngine().run(f, prov, cfg_bt)
    sh = ShadowAccount().run(f, prov, cfg_sh)
    assert np.isfinite(wf.metrics["sharpe"])
    assert np.isfinite(sh.metrics["sharpe"])
    assert len(wf.equity_curve) > 0
    assert len(sh.equity_curve) > 0
