"""Phase A 因子单测（f0092a 流动比率 / f0093a 速动比率 / f0094a 研发强度）。

锁死三件事：
1. 注册与 fcode 绑定（防止改名后交付包对不上）。
2. 金融股 NaN **不填充、不伪造**（行业特性，见 modules docstring）。
3. 非正比率 / 无效营收 **不入截面**（按缺失处理，而非截断为 0）。
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

import factors  # noqa: F401  （触发全量注册）
from factors.interface import get_factor
from factors.solvency import (
    CurrentRatioFactor,
    QuickRatioFactor,
    RDIntensityFactor,
)


def _snap(rows: dict) -> dict:
    """构造 snapshot({asset: {field: (value, statDate)}})。"""
    return {a: {f: (v, pd.Timestamp(sd)) for f, (v, sd) in fv.items()} for a, fv in rows.items()}


# ---------------- 注册 / 元数据 ----------------
@pytest.mark.parametrize("name,cls,fcode", [
    ("current_ratio", CurrentRatioFactor, "f0092a"),
    ("quick_ratio", QuickRatioFactor, "f0093a"),
    ("rd_intensity", RDIntensityFactor, "f0094a"),
])
def test_registered_and_fcode(name, cls, fcode):
    f = get_factor(name)
    assert isinstance(f, cls)
    assert f.fcode == fcode


def test_fcodes_are_unique():
    codes = [get_factor(n).fcode for n in ("current_ratio", "quick_ratio", "rd_intensity")]
    assert len(set(codes)) == 3


# ---------------- f0092a 流动比率 ----------------
def test_current_ratio_basic():
    f = CurrentRatioFactor()
    snap = _snap({
        "AAA.SH": {"current_ratio": (2.5, "2024-03-31")},
        "BBB.SH": {"current_ratio": (0.8, "2024-03-31")},
    })
    out = f._calc(snap, None, pd.Timestamp("2024-06-30"))
    assert set(out.index) == {"AAA.SH", "BBB.SH"}
    assert out["AAA.SH"] == pytest.approx(2.5)
    assert out["BBB.SH"] == pytest.approx(0.8)


def test_current_ratio_financial_stock_is_nan_not_filled():
    """银行/保险 current_ratio 天然 NaN —— 必须缺席截面，绝不能用行业均值插补。"""
    f = CurrentRatioFactor()
    snap = _snap({
        "BANK.SH": {"current_ratio": (np.nan, None)},
        "AAA.SH": {"current_ratio": (3.0, "2024-03-31")},
    })
    out = f._calc(snap, None, pd.Timestamp("2024-06-30"))
    assert "BANK.SH" not in out.index          # 缺席，而非填充 0 / 均值
    assert list(out.index) == ["AAA.SH"]


def test_current_ratio_nonpositive_excluded():
    """非正比率（资不抵债 / -1000 哨兵值）不入截面。"""
    f = CurrentRatioFactor()
    snap = _snap({
        "BAD.SH": {"current_ratio": (-1000.0, "2024-03-31")},   # 东财同款哨兵值
        "ZERO.SH": {"current_ratio": (0.0, "2024-03-31")},
        "OK.SH": {"current_ratio": (1.5, "2024-03-31")},
    })
    out = f._calc(snap, None, pd.Timestamp("2024-06-30"))
    assert list(out.index) == ["OK.SH"]


# ---------------- f0093a 速动比率 ----------------
def test_quick_ratio_basic():
    f = QuickRatioFactor()
    snap = _snap({"AAA.SH": {"quick_ratio": (1.9, "2024-03-31")}})
    out = f._calc(snap, None, pd.Timestamp("2024-06-30"))
    assert out["AAA.SH"] == pytest.approx(1.9)


def test_quick_ratio_le_current_ratio_in_practice():
    """速动比率 = (流动资产-存货)/流动负债 ≤ 流动比率，是同向更严格的口径。

    这里用真实量级数据（茅台 2026Q1：流动 7.06 / 速动 5.48）验证因子如实透传、
    未做倒置或缩放。
    """
    f_cr, f_qr = CurrentRatioFactor(), QuickRatioFactor()
    snap = _snap({
        "600519.SH": {"current_ratio": (7.060729, "2026-03-31"),
                      "quick_ratio": (5.482485, "2026-03-31")},
    })
    t = pd.Timestamp("2026-06-30")
    cr = f_cr._calc(snap, None, t)["600519.SH"]
    qr = f_qr._calc(snap, None, t)["600519.SH"]
    assert qr <= cr
    assert cr == pytest.approx(7.060729)
    assert qr == pytest.approx(5.482485)


# ---------------- f0094a 研发强度 ----------------
def test_rd_intensity_basic():
    f = RDIntensityFactor()
    snap = _snap({
        "TECH.SH": {"rd_expense": (2.0e8, "2024-03-31"), "revenue": (1.0e9, "2024-03-31")},
    })
    out = f._calc(snap, None, pd.Timestamp("2024-06-30"))
    assert out["TECH.SH"] == pytest.approx(0.2)


def test_rd_intensity_zero_kept():
    """rd==0 是真实'不研发'信号，必须保留（不能当缺失丢掉）。"""
    f = RDIntensityFactor()
    snap = _snap({
        "NORD.SH": {"rd_expense": (0.0, "2024-03-31"), "revenue": (5.0e9, "2024-03-31")},
    })
    out = f._calc(snap, None, pd.Timestamp("2024-06-30"))
    assert "NORD.SH" in out.index
    assert out["NORD.SH"] == 0.0


def test_rd_intensity_bad_revenue_excluded():
    f = RDIntensityFactor()
    snap = _snap({
        "NEGREV.SH": {"rd_expense": (1.0e8, "2024-03-31"), "revenue": (-1.0, "2024-03-31")},
        "NOREV.SH": {"rd_expense": (1.0e8, "2024-03-31"), "revenue": (np.nan, None)},
        "MISSRD.SH": {"rd_expense": (np.nan, None), "revenue": (1.0e9, "2024-03-31")},
    })
    out = f._calc(snap, None, pd.Timestamp("2024-06-30"))
    assert len(out) == 0      # 三条都不该产出


def test_rd_intensity_same_period_flows_need_no_annualization():
    """研发支出与营收同为流量项且同报告期 → 比值与年化系数无关（Q1 与年报应同量级）。"""
    f = RDIntensityFactor()
    q1 = _snap({"A.SH": {"rd_expense": (1.0, "2024-03-31"), "revenue": (10.0, "2024-03-31")}})
    yr = _snap({"A.SH": {"rd_expense": (4.0, "2024-12-31"), "revenue": (40.0, "2024-12-31")}})
    t1, t2 = pd.Timestamp("2024-06-30"), pd.Timestamp("2025-06-30")
    assert f._calc(q1, None, t1)["A.SH"] == pytest.approx(f._calc(yr, None, t2)["A.SH"])


# ---------------- 空输入健壮性 ----------------
@pytest.mark.parametrize("cls", [CurrentRatioFactor, QuickRatioFactor, RDIntensityFactor])
def test_empty_snapshot_returns_empty_series(cls):
    out = cls()._calc({}, None, pd.Timestamp("2024-06-30"))
    assert len(out) == 0
    assert isinstance(out, pd.Series)
