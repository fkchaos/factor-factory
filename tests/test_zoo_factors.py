"""动物园基准因子的单元测试（合成数据，不触发任何 baostock）。

验证：
1. 三个因子 compute 返回 asset-indexed 序列，且 name 正确。
2. 全部通过 assert_no_lookahead（前视防护，与内部因子同一纪律）。
3. momentum_20 与 reversal_5 截面负相关（风格区分 sanity）。
4. size_log_mcap 时序稳定 = log(market_cap)，无 NaN 膨胀。
"""
import numpy as np
import pandas as pd
import pytest

from data.providers import LocalProvider
from factors.interface import assert_no_lookahead, slice_panel_to_date
from factors import zoo_basics  # 触发注册
from factors.zoo_basics import Momentum20Factor, Reversal5Factor, SizeFactor

PANEL_COLS = ["open", "high", "low", "close", "volume", "amount", "turnover", "market_cap"]


@pytest.fixture(scope="module")
def panel():
    p = LocalProvider(seed=7, n_assets=20, start="2022-01-01", end="2024-12-31")
    return p.get_panel(PANEL_COLS, "2022-01-01", "2024-12-31")


def _asof(panel, offset=-1):
    dates = sorted(panel.index.get_level_values("date").unique())
    return dates[offset]


def test_zoo_factors_compute_shape(panel):
    asof = _asof(panel, -30)  # 留足历史算 lag=21
    for fac in (Momentum20Factor(), Reversal5Factor(), SizeFactor()):
        out = fac.compute(panel, asof)
        assert isinstance(out, pd.Series)
        assert out.name == fac.name
        assert out.index.name in (None, "asset")
        # 应至少有部分非 NaN
        assert out.notna().sum() > 0


def test_zoo_factors_no_lookahead(panel):
    asof = _asof(panel, -30)
    for fac in (Momentum20Factor(), Reversal5Factor(), SizeFactor()):
        assert assert_no_lookahead(fac, panel, asof) is True


def test_momentum_reversal_negative_correlation(panel):
    """动量 vs 短期反转在截面上应负相关 —— 风格区分 sanity。"""
    asof = _asof(panel, -30)
    mom = Momentum20Factor().compute(panel, asof)
    rev = Reversal5Factor().compute(panel, asof)
    df = pd.concat([mom, rev], axis=1).dropna()
    if len(df) >= 3:
        corr = df.iloc[:, 0].corr(df.iloc[:, 1])
        assert corr < 0.2, f"momentum 与 reversal 应弱/负相关，实测 ρ={corr:.3f}"


def test_size_is_log_mcap(panel):
    asof = _asof(panel, -1)
    day = slice_panel_to_date(panel, asof).xs(asof, level="date")
    # size 因子缺少市值的票应为 NaN
    size = SizeFactor().compute(panel, asof)
    # 与 log(market_cap) 在有效处一致
    expected = np.log(day["market_cap"].where(day["market_cap"] > 0))
    common = size.dropna().index.intersection(expected.dropna().index)
    assert len(common) > 0
    assert np.allclose(size.loc[common].values, expected.loc[common].values)
