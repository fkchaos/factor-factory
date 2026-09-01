"""f0014a 存货周转天数 / f0015a 应收账款周转天数 因子单测。

隔离验证（不联网 AkShare）：
  A. `_ann_factor` 年度化系数：Q1(Mar)→4 / H1(Jun)→2 / Q3(Sep)→4/3 / 年报(Dec)→1 / 非季末月→NaN。
  B. `_turnover_days` 公式：365 × 存量 / (流量 × 年化系数)，含流量项缺失/<=0 跳过。
  C. 因子 compute 无前视：as_of 早于披露日 → 资产不在结果；跨过披露日 → 出现且正确年度化。
  D. 季度 vs 年报可比性：同存货、季度 cogs=年报/4 → 经年度化后周转天数应一致（证明年度化消除"报告期类型"污染）。

注入式 PitFinancialsService（假 provider 走受控披露表），绕开 AkShare 联网。
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from data.contract import normalize_code
from data.pit_fundamentals import PitFinancialsService
from factors.turnover_days import (
    _ann_factor, _turnover_days,
    InventoryTurnoverDaysFactor, AccountReceivableTurnoverDaysFactor,
)
from factors.interface import slice_panel_to_date


# 披露表列（与 AkShareProvider._fetch_financial_history 输出一致）
_DISC_COLS = ["statDate", "pubDate", "OPERATE_INCOME", "OPERATE_COST",
              "INVENTORY", "ACCOUNTS_RESE"]


class _FakeProvider:
    """走受控披露表的假 provider（不联网）。"""
    _PIT_FIELD_MAP = {"revenue": "OPERATE_INCOME", "cogs": "OPERATE_COST",
                      "inventory": "INVENTORY", "accounts_receivable": "ACCOUNTS_RESE"}

    def __init__(self, hist: dict):
        self._hist = {normalize_code(k): v for k, v in hist.items()}

    def _fetch_financial_history(self, code):
        return self._hist.get(normalize_code(code), pd.DataFrame())


def _disc(rows: list[dict]) -> pd.DataFrame:
    norm = []
    for r in rows:
        norm.append({c: r.get(c, np.nan) for c in _DISC_COLS})
    return pd.DataFrame(norm)


def _svc(rows: list[dict], assets=("600519.SH",)) -> PitFinancialsService:
    prov = _FakeProvider({a: _disc(rows) for a in assets})
    return PitFinancialsService(prov, list(assets),
                                ["cogs", "inventory", "accounts_receivable", "revenue"])


def _panel(asset="600519.SH", date="2000-01-01") -> pd.DataFrame:
    """构造最小面板：仅让资产在 date<=as_of 出现在切片里（因子只取 asset 列表）。"""
    idx = pd.MultiIndex.from_tuples([(pd.Timestamp(date), normalize_code(asset))],
                                    names=["date", "asset"])
    return pd.DataFrame({"close": [1.0]}, index=idx)


def _one_asset_snap(factor, rows, as_of, asset="600519.SH"):
    """用注入式服务跑一次 compute，返回结果 Series。"""
    svc = _svc(rows, [asset])
    ctx = {"pit_service": svc}
    panel = _panel(asset)
    return factor.compute(panel, pd.Timestamp(as_of), ctx=ctx)


# ===========================================================================
# A. 年度化系数
# ===========================================================================

@pytest.mark.parametrize("stat_date,expected", [
    ("2024-03-31", 4.0),    # Q1
    ("2024-06-30", 2.0),    # H1
    ("2024-09-30", 4.0/3.0),  # Q3
    ("2023-12-31", 1.0),    # 年报
    ("2024-04-15", np.nan), # 非季末月 → NaN
    (None, np.nan),
])
def test_ann_factor(stat_date, expected):
    got = _ann_factor(stat_date)
    if pd.isna(expected):
        assert pd.isna(got), f"非季末月/缺失应得 NaN，实得 {got}"
    else:
        assert abs(got - expected) < 1e-9, f"年化系数错：{got} != {expected}"


# ===========================================================================
# B. 公式
# ===========================================================================

def test_turnover_days_formula_and_skip():
    """365×存量/(流量×年化)；流量缺失或<=0 跳过该资产。"""
    snap = {
        "A.SH": {"inventory": (50.0, "2023-12-31"), "cogs": (100.0, "2023-12-31")},   # 年报 ann=1
        "B.SH": {"inventory": (50.0, "2024-03-31"), "cogs": (25.0, "2024-03-31")},    # Q1 ann=4
        "C.SH": {"inventory": (50.0, "2024-03-31"), "cogs": (np.nan, "2024-03-31")},  # 流量缺失→跳过
        "D.SH": {"inventory": (50.0, "2024-03-31"), "cogs": (0.0, "2024-03-31")},     # 流量<=0→跳过
    }
    out = _turnover_days(snap, "inventory", "cogs")
    assert "A.SH" in out and abs(out["A.SH"] - 365*50/100) < 1e-9
    assert "B.SH" in out and abs(out["B.SH"] - 365*50/(25*4)) < 1e-9  # =365*50/100，与 A 一致
    assert "C.SH" not in out and "D.SH" not in out


# ===========================================================================
# C. 因子 compute 无前视
# ===========================================================================

def test_inventory_compute_no_lookahead_and_annualized():
    """年报 2023-12-31 于 2024-04-30 披露：04-29 不可见，05-01 可见且按年报(ann=1)年化。"""
    rows = [{"statDate": "2023-12-31", "pubDate": "2024-04-30",
             "INVENTORY": 50.0, "OPERATE_COST": 100.0}]
    fac = InventoryTurnoverDaysFactor()
    before = _one_asset_snap(fac, rows, "2024-04-29")
    assert before.empty, "前视红线失效：披露日前竟取到存货周转天数"
    after = _one_asset_snap(fac, rows, "2024-05-01")
    assert "600519.SH" in after.index
    assert abs(after["600519.SH"] - 365*50/100) < 1e-9  # 年报 ann=1


def test_ar_compute_quarterly_vs_annual_comparable():
    """同一应收账款(20)、季度营收=年报/4 → 经年度化后周转天数应一致（可比性证明）。"""
    annual = [{"statDate": "2023-12-31", "pubDate": "2024-04-30",
               "ACCOUNTS_RESE": 20.0, "OPERATE_INCOME": 800.0}]  # 年报 ann=1
    q1 = [{"statDate": "2024-03-31", "pubDate": "2024-04-27",
           "ACCOUNTS_RESE": 20.0, "OPERATE_INCOME": 200.0}]       # Q1 ann=4 (=800/4)
    fac = AccountReceivableTurnoverDaysFactor()
    a = _one_asset_snap(fac, annual, "2024-05-01")
    q = _one_asset_snap(fac, q1, "2024-05-01")
    exp = 365*20/800  # 两者数值相同
    assert abs(a["600519.SH"] - exp) < 1e-9
    assert abs(q["600519.SH"] - exp) < 1e-9, "年度化未消除报告期类型污染：季度与年报结果不一致"


def test_compute_uses_full_history_not_single_stream():
    """双流独立：存货来自资产负债表流(快报 03-21)、成本来自利润表流(年报 04-30)。
    04-01（年报未披露）时存货可见、成本不可见 → 周转天数缺失；05-01 两者齐 → 出值。"""
    rows = [
        {"statDate": "2023-12-31", "pubDate": "2024-03-21",
         "INVENTORY": 50.0, "ACCOUNTS_RESE": 30.0,
         "OPERATE_INCOME": np.nan, "OPERATE_COST": np.nan},
        {"statDate": "2023-12-31", "pubDate": "2024-04-30",
         "INVENTORY": np.nan, "ACCOUNTS_RESE": np.nan,
         "OPERATE_INCOME": 800.0, "OPERATE_COST": 100.0},
    ]
    fac = InventoryTurnoverDaysFactor()
    mid = _one_asset_snap(fac, rows, "2024-04-01")
    assert mid.empty, "成本流尚未披露却算出周转天数（前视/串流）"
    end = _one_asset_snap(fac, rows, "2024-05-01")
    assert abs(end["600519.SH"] - 365*50/100) < 1e-9


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
