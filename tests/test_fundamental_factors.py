"""Phase 0 财报扩面因子单元测试（不联网）。

构造假的东财披露历史注入 PitFinancialsService._hist，验证：
1. 新字段映射（operate_profit/total_assets/ocf/...）经 _PIT_FIELD_MAP 正确取到值；
2. 各因子 _calc 比率计算正确（手算预期对照）；
3. 🔴 PIT 红线：as_of 早于公告日 NOTICE_DATE 时该股票不可见（无前视）。
"""
import numpy as np
import pandas as pd
import pytest

import factors.fundamentals as F
from data.providers import AkShareProvider
from data.pit_fundamentals import PitFinancialsService, _DEFAULT_PIT_FIELDS
from data.contract import normalize_code

CODE = "600519.SH"


@pytest.fixture
def fake_svc():
    # 轻量 mock provider：只提供 _PIT_FIELD_MAP（不构造 AkShareProvider 实例，避免联网）
    mock_provider = type(
        "MockAk", (), {"_PIT_FIELD_MAP": dict(AkShareProvider._PIT_FIELD_MAP)}
    )()
    svc = PitFinancialsService(mock_provider, [], _DEFAULT_PIT_FIELDS)
    # 一只股票、一个年报披露（statDate=2024-12-31, pubDate=2025-04-17）
    fake = pd.DataFrame([{
        "statDate": pd.Timestamp("2024-12-31"),
        "pubDate": pd.Timestamp("2025-04-17"),
        "OPERATE_INCOME": 1000.0, "OPERATE_COST": 300.0, "OPERATE_PROFIT": 400.0,
        "TOTAL_PROFIT": 380.0, "NETPROFIT": 300.0, "PARENT_NETPROFIT": 300.0,
        "DEDUCT_PARENT_NETPROFIT": 280.0, "BASIC_EPS": 10.0,
        "OPERATE_INCOME_YOY": 12.0, "PARENT_NETPROFIT_YOY": 15.0,
        "INVENTORY": 200.0, "ACCOUNTS_RECE": 100.0,
        "TOTAL_ASSETS": 2000.0, "TOTAL_EQUITY": 1000.0,
        "TOTAL_PARENT_EQUITY": 900.0, "NETCASH_OPERATE": 350.0,
    }])
    svc._hist[CODE] = fake
    return svc


@pytest.fixture
def panel():
    idx = pd.MultiIndex.from_tuples(
        [(pd.Timestamp("2025-04-30"), CODE)], names=["date", "asset"]
    )
    return pd.DataFrame(
        {"amount": [30000.0], "turnover": [1.0], "close": [100.0]}, index=idx
    )


# 年报口径（ann=1）：手算预期值
EXPECTED = {
    "f0060a": 300 / 900,        # roe
    "f0061a": 300 / 2000,       # roa
    "f0062a": (1000 - 300) / 1000,   # gross_margin
    "f0063a": 300 / 1000,       # net_margin
    "f0064a": 1000 / 2000,      # asset_turnover
    "f0065a": 400 / 1000,       # operate_profit_margin
    "f0066a": 2000 / 900,       # financial_leverage
    "f0067a": 350 / 300,        # cash_coverage
    "f0068a": (300 - 350) / 2000,    # accrual
    "f0069a": 280 / 300,        # deduct_ratio
    "f0070a": 300 / 3e6,        # ep (mcap=30000/(1.0/100)=3e6)
    "f0071a": 12.0,             # revenue_yoy
    "f0072a": 15.0,             # netprofit_yoy
}

FACTORS = {
    "f0060a": F.ROEFactor(), "f0061a": F.ROAFactor(),
    "f0062a": F.GrossMarginFactor(), "f0063a": F.NetMarginFactor(),
    "f0064a": F.AssetTurnoverFactor(), "f0065a": F.OperateProfitMarginFactor(),
    "f0066a": F.FinancialLeverageFactor(), "f0067a": F.CashCoverageFactor(),
    "f0068a": F.AccrualFactor(), "f0069a": F.DeductRatioFactor(),
    "f0070a": F.EPFactor(), "f0071a": F.RevenueYoyFactor(),
    "f0072a": F.NetProfitYoyFactor(),
}


@pytest.mark.parametrize("fcode", list(EXPECTED.keys()))
def test_factor_value(fake_svc, panel, fcode):
    fac = FACTORS[fcode]
    res = fac.compute(panel, "2025-05-01", ctx={"pit_service": fake_svc})
    assert CODE in res.index, f"{fcode}: 资产未出现在结果中"
    assert np.isclose(res[CODE], EXPECTED[fcode], rtol=1e-6), \
        f"{fcode}: 得到 {res[CODE]:.6f}，预期 {EXPECTED[fcode]:.6f}"


def test_pit_no_lookahead(fake_svc, panel):
    """as_of 早于公告日 → 该股票财报不可见（无前视）。"""
    res = F.ROEFactor().compute(panel, "2025-01-01", ctx={"pit_service": fake_svc})
    assert CODE not in res.index, "PIT 红线失效：公告日前财报可见（前视！）"


def test_all_13_registered():
    """13 个财报扩面因子全部注册到 interface（key=name）。"""
    from factors.interface import _REGISTRY
    names = {f.name for f in FACTORS.values()}
    for name in names:
        assert name in _REGISTRY, f"{name} 未注册"
