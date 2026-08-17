"""Provider 契约测试：验证可插拔设计下单位/格式一致性的防火墙。

不依赖联网。用 LocalProvider（合成）与一个故意“不合规”的 FakeAkShare 验证：
- normalize_code 能统一各种代码写法为 6位.交易所；
- canonicalize_panel 能把 trade_date/asset 或含无后缀代码的面板规范掉；
- validate_panel 能拦住：索引名错、代码无后缀、单位错（手当股/千元当元/百分数当小数）、0 占位缺失。
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from data.contract import (
    normalize_code, canonicalize_panel, validate_panel, validate_returns,
    PANEL_FIELDS, assert_adj_policy, ADJ_POLICY,
)
from data.providers import LocalProvider, BaoStockProvider, AkShareProvider, TushareProvider


# ---- normalize_code ----
@pytest.mark.parametrize("raw,exp", [
    ("000001", "000001.SZ"),
    ("000001.SZ", "000001.SZ"),
    ("sz000001", "000001.SZ"),
    ("600000", "600000.SH"),
    ("600000.SH", "600000.SH"),
    ("sh600519", "600519.SH"),
    ("830000", "830000.BJ"),
    ("300750", "300750.SZ"),
    ("688981", "688981.SH"),
])
def test_normalize_code(raw, exp):
    assert normalize_code(raw) == exp


def test_normalize_code_unknown_passthrough():
    assert normalize_code("ABC") == "ABC"   # 无法识别原样返回，交由校验器报错


# ---- validate_panel 拦错 ----
def _panel(asset="000001.SZ", volume=1e6, amount=1e8, turnover=2.0, market_cap=1e11):
    idx = pd.MultiIndex.from_tuples([(pd.Timestamp("2024-01-02"), asset)], names=["date", "asset"])
    return pd.DataFrame(
        {"open": 10.0, "high": 10.5, "low": 9.8, "close": 10.2,
         "volume": volume, "amount": amount, "turnover": turnover, "market_cap": market_cap},
        index=idx,
    )


def test_validate_panel_ok():
    validate_panel(_panel(), "Test", ["close", "volume", "amount", "turnover", "market_cap"])


def test_validate_panel_rejects_bad_index_names():
    p = _panel()
    p.index = p.index.rename(["trade_date", "asset"])
    with pytest.raises(ValueError):
        validate_panel(p, "Bad")


def test_validate_panel_rejects_code_no_suffix():
    p = _panel(asset="000001")   # 无后缀
    with pytest.raises(ValueError):
        validate_panel(p, "Bad")


def test_validate_panel_rejects_zero_placeholder():
    # market_cap 用 0 占位（akshare 旧实现遗留）应被拦截
    p = _panel(market_cap=0.0)
    with pytest.raises(ValueError):
        validate_panel(p, "Bad")


def test_validate_panel_rejects_turnover_overflow():
    # turnover 软上限 1000：5000 只可能是单位错（典型 50% 被 ×100）
    p = _panel(turnover=5000.0)
    with pytest.raises(ValueError):
        validate_panel(p, "Bad")


def test_validate_panel_accepts_turnover_above_100():
    """反向锁：单日换手 >100% 是 A 股真实现象，不得当作单位错拒收。

    2026-08-07 六池回填因契约上限卡在 100、遇 hs1800 真实样例 106.48 直接中断。
    真数据被防火墙误杀比脏数据流进来更隐蔽——它让你以为"没数据"，而不是"数据错了"。
    """
    for real_turnover in (106.48, 250.0, 800.0):
        p = _panel(turnover=real_turnover)
        validate_panel(p, "RealSpike", ["close", "volume", "amount", "turnover", "market_cap"])


# ---- LocalProvider 自带合规 ----
def test_local_provider_conforms():
    lp = LocalProvider(seed=7, n_assets=10)
    panel = lp.get_panel(["open", "high", "low", "close", "volume", "amount", "turnover", "market_cap"],
                         "2023-01-01", "2023-06-30")
    validate_panel(panel, "Local", ["close", "volume", "amount", "turnover", "market_cap"])
    assert list(panel.index.names) == ["date", "asset"]


# ---- canonicalize_panel 修正无后缀 / 错误索引名 ----
def test_canonicalize_fixes_trade_date_and_suffix():
    raw = pd.DataFrame(
        {"open": 10.0, "close": 10.2, "volume": 1e6, "amount": 1e8,
         "turnover": 2.0, "market_cap": 1e11},
        index=pd.MultiIndex.from_tuples([(pd.Timestamp("2024-01-02"), "000001")],
                                        names=["trade_date", "asset"]),
    )
    fixed = canonicalize_panel(raw)
    assert list(fixed.index.names) == ["date", "asset"]
    assert fixed.index.get_level_values("asset")[0] == "000001.SZ"


# ---- validate_returns ----
def test_validate_returns_ok():
    s = pd.Series([0.01, -0.02, 0.005], index=pd.date_range("2024-01-02", periods=3))
    validate_returns(s, "Test")


def test_validate_returns_rejects_percent():
    s = pd.Series([1.0, -2.0], index=pd.date_range("2024-01-02", periods=2))  # 百分数当小数
    with pytest.raises(ValueError):
        validate_returns(s, "Bad")


# ---- adj_policy 防火墙：复权口径一致性（防"切换源结果悄悄变"）----
def test_adj_policy_conformance():
    """各 Provider 必须声明 adj_policy；符合契约 qfq 的源过防火墙，已知不一致的须显式放行。"""
    # 符合契约 ADJ_POLICY（qfq）的源
    assert BaoStockProvider.adj_policy == ADJ_POLICY == "qfq"
    assert AkShareProvider.adj_policy == ADJ_POLICY == "qfq"
    # 已知不一致（免费 token 只能 raw / 合成数据无公司行为），主流程须经防火墙显式放行
    assert TushareProvider.adj_policy == "raw"
    assert LocalProvider.adj_policy == "raw"


def test_assert_adj_policy_ok_and_block():
    # 一致：通过
    assert_adj_policy("qfq")
    assert_adj_policy(ADJ_POLICY)
    # 不一致 + 不放行：抛错（防止静默混入主流程污染因子）
    with pytest.raises(RuntimeError):
        assert_adj_policy("raw")
    # 不一致 + 显式放行：仅告警（诊断场景）
    with pytest.warns(UserWarning):
        assert_adj_policy("raw", allow_mismatch=True)


def test_local_provider_get_panel_canonicalized_sorted():
    """LocalProvider.get_panel 现在也过 canonicalize+validate 防火墙；输出须规范且按 (date,asset) 升序。"""
    lp = LocalProvider(seed=7, n_assets=10)
    panel = lp.get_panel(
        ["open", "high", "low", "close", "volume", "amount", "turnover", "market_cap"],
        "2023-01-01", "2023-06-30")
    validate_panel(panel, "Local", ["close", "volume", "amount", "turnover", "market_cap"])
    assert list(panel.index.names) == ["date", "asset"]
    # 升序校验
    idx = panel.index
    assert (idx.get_level_values("date").is_monotonic_increasing)
    # 代码均规范（6位.交易所）
    import re
    assert all(re.match(r"^\d{6}\.(SH|SZ|BJ)$", a) for a in idx.get_level_values("asset").unique())
