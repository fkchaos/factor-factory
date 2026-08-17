"""前视防护专项测试。

对应计划里"前视防护在接口层强制"与 CI 门禁。任何新因子合并前必须通过本测试。
- test_slice_drops_future：切片工具正确丢弃未来行。
- test_clean_factor_passes：合规因子在"全量 vs 切片"下输出一致 -> 通过。
- test_leaky_factor_raises / test_global_stat_raises：违规因子输出不一致 -> 抛 LookaheadError。
"""
import pandas as pd
import pytest
from factors.interface import assert_no_lookahead, slice_panel_to_date, LookaheadError
from tests.conftest import PANEL, CleanFactor, LeakyFactor, GlobalStatFactor


def test_slice_drops_future():
    d = pd.Timestamp("2024-01-03")
    s = slice_panel_to_date(PANEL, d)
    assert s.index.get_level_values("date").max() <= d


def test_clean_factor_passes():
    d = pd.Timestamp("2024-01-05")
    assert assert_no_lookahead(CleanFactor(), PANEL, d) is True


def test_leaky_factor_raises():
    d = pd.Timestamp("2024-01-05")
    with pytest.raises(LookaheadError):
        assert_no_lookahead(LeakyFactor(), PANEL, d)


def test_global_stat_raises():
    d = pd.Timestamp("2024-01-05")
    with pytest.raises(LookaheadError):
        assert_no_lookahead(GlobalStatFactor(), PANEL, d)
