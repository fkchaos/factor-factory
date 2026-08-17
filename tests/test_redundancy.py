import pandas as pd

from data.providers import LocalProvider
from factors.overnight_intraday import OvernightIntradayFactor
from factors.ivol import IvolFactor
from engine.interface import BacktestConfig
from validate.redundancy import snapshot_factors, correlation_matrix, report_redundancy


def test_redundancy_snapshot_structure():
    prov = LocalProvider(seed=7)
    factors = [OvernightIntradayFactor(), IvolFactor()]
    cfg = BacktestConfig(train_days=60, test_days=20, step_days=20, top_n=5)
    snap = snapshot_factors(factors, prov, cfg)
    assert isinstance(snap, pd.DataFrame)
    assert set(snap.columns) == {"overnight_intraday", "ivol"}
    assert len(snap) > 0


def test_correlation_matrix_and_report():
    prov = LocalProvider(seed=7)
    factors = [OvernightIntradayFactor(), IvolFactor()]
    cfg = BacktestConfig(train_days=60, test_days=20, step_days=20, top_n=5)
    snap = snapshot_factors(factors, prov, cfg)
    mat = correlation_matrix(snap)
    assert isinstance(mat, pd.DataFrame)
    assert mat.shape == (2, 2)
    pairs = report_redundancy(mat, threshold=0.6)
    assert isinstance(pairs, list)  # 随机数据下可能为空，但接口须工作
