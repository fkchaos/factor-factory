"""微观结构因子单元测试（合成日线面板，不依赖缓存）。

覆盖：隔夜跳空已知值、涨停封板三态（封死/曾打开/未涨停）、前视防护 CI。
"""
import numpy as np
import pandas as pd

from factors.microstructure import OvernightGapFactor, LimitUpSealFactor
from factors.interface import assert_no_lookahead


def make_micro_panel():
    dates = pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04"])
    rows = []
    # 前两日：所有资产 close=10（作为 as_of 的前收）
    for d in dates[:2]:
        for a in ["A", "B", "C"]:
            rows.append((d, a, 10.0, 10.0, 10.0, 10.0, 1e6, 1e7, 0.02, 1e9))
    # as_of (01-04):
    #   A: 高开+涨停封死 -> gap=0.1, seal=1
    #   B: 平开未涨停   -> gap=0,   seal=0
    #   C: 高开涨停但曾打开 -> gap=0.05, seal=0.5
    rows.append((dates[2], "A", 11.0, 11.0, 11.0, 11.0, 1e6, 1.1e7, 0.02, 1.1e9))
    rows.append((dates[2], "B", 10.0, 10.0, 10.0, 9.0, 1e6, 9e6, 0.02, 9e8))
    rows.append((dates[2], "C", 10.5, 11.5, 10.5, 11.0, 1e6, 1.1e7, 0.02, 1.1e9))
    df = pd.DataFrame(rows, columns=["date", "asset", "open", "high", "low",
                                     "close", "volume", "amount", "turnover", "market_cap"])
    return df.set_index(["date", "asset"]).sort_index()


def test_overnight_gap_known():
    panel = make_micro_panel()
    as_of = panel.index.get_level_values("date").max()
    s = OvernightGapFactor().compute(panel, as_of)
    assert abs(s["A"] - 0.1) < 1e-9
    assert abs(s["B"] - 0.0) < 1e-9
    assert abs(s["C"] - 0.05) < 1e-9


def test_limit_up_seal_three_states():
    panel = make_micro_panel()
    as_of = panel.index.get_level_values("date").max()
    s = LimitUpSealFactor().compute(panel, as_of)
    assert s["A"] == 1.0      # 封死
    assert s["B"] == 0.0      # 未涨停
    assert s["C"] == 0.5      # 曾打开


def test_no_lookahead_gap():
    panel = make_micro_panel()
    as_of = panel.index.get_level_values("date").max()
    assert assert_no_lookahead(OvernightGapFactor(), panel, as_of)


def test_no_lookahead_seal():
    panel = make_micro_panel()
    as_of = panel.index.get_level_values("date").max()
    assert assert_no_lookahead(LimitUpSealFactor(), panel, as_of)
