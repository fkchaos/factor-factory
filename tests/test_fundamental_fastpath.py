"""财报因子快路径（compute_panel）正确性验证（不联网）。

背景（2026-09-09）：13 个财报因子最初只有逐日 compute，被 build_deliverable 判为
慢路径（O(交易日×资产)=45 万次全表切片）→ 单因子出包 >1 小时、9 个因子全部超时。
改为事件驱动快路径（每票只在公告日算一次 + 阶梯 ffill）。

🔴 本测试的存在理由：快路径重算了全序列，若与慢路径口径不一致，交付卡片上的
RankIC/回测就会是"快但错"的数字——比慢更糟。故强制两条路径逐日对齐。
"""
import numpy as np
import pandas as pd
import pytest

import factors.fundamentals as F
from data.providers import AkShareProvider
from data.pit import pit_float_mcap
from data.pit_fundamentals import PitFinancialsService, _DEFAULT_PIT_FIELDS

A, B = "600519.SH", "000001.SZ"

# 交易日轴：2025-01-02 起 180 个交易日（≈到 9 月中，须覆盖 4/17 与 8/20 两次披露）
DATES = pd.bdate_range("2025-01-02", periods=180)


def _disc(code, rows):
    """构造单票披露历史：rows = [(statDate, pubDate, 字段字典)]。"""
    recs = []
    for sd, pub, vals in rows:
        r = {"statDate": pd.Timestamp(sd), "pubDate": pd.Timestamp(pub)}
        r.update(vals)
        recs.append(r)
    return pd.DataFrame(recs)


@pytest.fixture
def svc():
    mock_provider = type("MockAk", (), {"_PIT_FIELD_MAP": dict(AkShareProvider._PIT_FIELD_MAP)})()
    s = PitFinancialsService(mock_provider, [], _DEFAULT_PIT_FIELDS)
    s._hist[A] = _disc(A, [
        ("2024-12-31", "2025-04-17", {          # 年报
            "OPERATE_INCOME": 1000.0, "OPERATE_COST": 300.0, "OPERATE_PROFIT": 400.0,
            "TOTAL_PROFIT": 380.0, "NETPROFIT": 300.0, "PARENT_NETPROFIT": 300.0,
            "DEDUCT_PARENT_NETPROFIT": 280.0, "BASIC_EPS": 10.0,
            "OPERATE_INCOME_YOY": 12.0, "PARENT_NETPROFIT_YOY": 15.0,
            "INVENTORY": 200.0, "ACCOUNTS_RECE": 100.0,
            "TOTAL_ASSETS": 2000.0, "TOTAL_EQUITY": 1000.0,
            "TOTAL_PARENT_EQUITY": 900.0, "NETCASH_OPERATE": 350.0,
        }),
        ("2025-06-30", "2025-08-20", {          # 中报
            "OPERATE_INCOME": 600.0, "OPERATE_COST": 200.0, "OPERATE_PROFIT": 220.0,
            "TOTAL_PROFIT": 210.0, "NETPROFIT": 160.0, "PARENT_NETPROFIT": 160.0,
            "DEDUCT_PARENT_NETPROFIT": 150.0, "BASIC_EPS": 5.3,
            "OPERATE_INCOME_YOY": 8.0, "PARENT_NETPROFIT_YOY": -4.0,
            "INVENTORY": 210.0, "ACCOUNTS_RECE": 120.0,
            "TOTAL_ASSETS": 2100.0, "TOTAL_EQUITY": 1050.0,
            "TOTAL_PARENT_EQUITY": 950.0, "NETCASH_OPERATE": 180.0,
        }),
    ])
    s._hist[B] = _disc(B, [
        ("2024-12-31", "2025-03-10", {
            "OPERATE_INCOME": 500.0, "OPERATE_COST": 250.0, "OPERATE_PROFIT": 120.0,
            "TOTAL_PROFIT": 115.0, "NETPROFIT": 90.0, "PARENT_NETPROFIT": 90.0,
            "DEDUCT_PARENT_NETPROFIT": 85.0, "BASIC_EPS": 2.0,
            "OPERATE_INCOME_YOY": 3.0, "PARENT_NETPROFIT_YOY": 5.0,
            "INVENTORY": 80.0, "ACCOUNTS_RECE": 60.0,
            "TOTAL_ASSETS": 1200.0, "TOTAL_EQUITY": 600.0,
            "TOTAL_PARENT_EQUITY": 560.0, "NETCASH_OPERATE": 100.0,
        }),
    ])
    return s


@pytest.fixture
def panel():
    """构造含 amount/turnover/close 的面板（EP 与市值网格需要）。"""
    idx = pd.MultiIndex.from_product([DATES, [A, B]], names=["date", "asset"])
    n = len(idx)
    rng = np.random.default_rng(7)
    turn = rng.uniform(0.5, 3.0, n)          # 换手率 %
    close = rng.uniform(10, 200, n)
    amount = close * turn / 100.0 * 1e8       # 与换手率自洽，避免出现荒谬市值
    return pd.DataFrame({"amount": amount, "turnover": turn, "close": close}, index=idx)


ALL = [
    F.ROEFactor(), F.ROAFactor(), F.GrossMarginFactor(), F.NetMarginFactor(),
    F.AssetTurnoverFactor(), F.OperateProfitMarginFactor(), F.FinancialLeverageFactor(),
    F.CashCoverageFactor(), F.AccrualFactor(), F.DeductRatioFactor(),
    F.EPFactor(), F.RevenueYoyFactor(), F.NetProfitYoyFactor(),
]


@pytest.mark.parametrize("fac", ALL, ids=[f.name for f in ALL])
def test_fastpath_matches_slowpath(fac, svc, panel):
    """快路径 compute_panel 与逐日 compute 在每个交易日上必须一致。"""
    ctx = {"pit_service": svc}
    fast = fac.compute_panel(panel, ctx=ctx)

    # 慢路径：逐日切片 compute
    slow = {}
    for t in DATES:
        sub = panel[panel.index.get_level_values("date") <= t]
        s = fac.compute(sub, t, ctx=ctx)
        slow[t] = s
    slow_df = pd.DataFrame(slow).T

    # 逐 (日期, 资产) 比对：两边都非空必须相等；一边空另一边非空 = 口径 bug
    for t in DATES:
        for a in (A, B):
            fv = fast.loc[t, a] if (a in fast.columns and t in fast.index) else np.nan
            sv = slow_df.loc[t, a] if (a in slow_df.columns and t in slow_df.index) else np.nan
            if pd.isna(fv) and pd.isna(sv):
                continue
            assert not pd.isna(fv) and not pd.isna(sv), (
                f"{fac.name} @{t.date()} {a}: 路径不一致 fast={fv} slow={sv}")
            assert np.isclose(fv, sv, rtol=1e-9, atol=0), (
                f"{fac.name} @{t.date()} {a}: fast={fv} slow={sv}")


def test_fastpath_step_changes_at_pubdate(svc, panel):
    """阶梯语义：值只在公告日跳变（A 在 04-17 与 08-20 前有值且各自区间内恒定）。"""
    ctx = {"pit_service": svc}
    fast = F.ROEFactor().compute_panel(panel, ctx=ctx)
    s = fast[A].dropna()
    # 首次有值日 = 首个公告日（含）之后
    assert s.index[0] >= pd.Timestamp("2025-04-17")
    # 04-17 至 08-19 之间恒定（同一份年报快照）
    seg = s.loc[pd.Timestamp("2025-04-17"):pd.Timestamp("2025-08-19")]
    assert seg.nunique() == 1, "年报区间内因子值应恒定（阶梯）"
    # 中报披露后应跳变
    after = s.loc[pd.Timestamp("2025-08-20"):]
    assert after.nunique() == 1 and not np.isclose(seg.iloc[0], after.iloc[0]), \
        "中报披露后因子值应跳变到新快照"


def test_mcap_grid_matches_pit_float_mcap(panel):
    """🔴 PIT 红线：向量化市值网格必须与逐日 pit_float_mcap 同口径。"""
    grid = F._mcap_grid(panel)
    for t in list(DATES[::7]) + [DATES[-1]]:
        ref = pit_float_mcap(panel, t)          # 逐日权威实现
        for a in (A, B):
            gv = grid.loc[t, a] if a in grid.columns else np.nan
            rv = ref.get(a, np.nan)
            if pd.isna(rv):
                assert pd.isna(gv), f"@{t.date()} {a}: 逐日版无值但网格有值 {gv}"
            else:
                assert np.isclose(gv, rv, rtol=1e-9), f"@{t.date()} {a}: 网格={gv} 逐日={rv}"


def test_disclosure_dates_sorted_unique(svc):
    """服务层披露日接口：升序去重，供事件驱动取数。"""
    for code in (A, B):
        d = svc.disclosure_dates(code)
        assert list(d) == sorted(set(d)) and len(d) > 0
