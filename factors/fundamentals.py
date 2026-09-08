"""Phase 0 财报扩面因子（f0060a–f0072a，2026-09-08）。

数据源：AkShare 东财三表，经 PitFinancialsService 走 NOTICE_DATE 真实公告日对齐（无前视）。
因子清单（全部为 PIT 安全的截面比率，正交于价量因子）：
  f0060a roe                  净资产收益率   = 年化归母净利 / 归母净资产
  f0061a roa                  总资产收益率   = 年化归母净利 / 总资产
  f0062a gross_margin         毛利率         = (营收-成本)/营收
  f0063a net_margin           净利率         = 归母净利 / 营收
  f0064a asset_turnover       资产周转率     = 年化营收 / 总资产
  f0065a operate_profit_margin 营业利润率    = 营业利润 / 营收
  f0066a financial_leverage   财务杠杆       = 总资产 / 归母净资产
  f0067a cash_coverage        盈利现金保障   = 经营现金流 / 归母净利
  f0068a accrual             应计           = (年化归母净利-年化经营现金流)/总资产
  f0069a deduct_ratio         扣非净利占比   = 扣非归母净利 / 归母净利
  f0070a ep                   盈利市值比(E/P)= 年化归母净利 / PIT流通市值
  f0071a revenue_yoy          营收同比       = 利润表 OPERATE_INCOME_YOY 列
  f0072a netprofit_yoy        净利同比       = 利润表 PARENT_NETPROFIT_YOY 列

🔴 年度化（关键，同源 f0014a/f0015a）：利润表/现金流量表是**流量项**（季报只覆盖
3/6/9 个月），直接除时点项（资产/净资产）会系统性低估。故流量项按 statDate 月份
反推覆盖月数 → 年化系数 {3:4, 6:2, 9:4/3, 12:1}。资产/净资产是时点项不参与年化。
毛利率/净利率/营业利润率/扣非占比/现金保障这类"流量/流量"比率，年化在分子分母同乘
可约掉，故不显式年化。

⚠️ 季度报告期混合口径偏差（如实标注，非前视）：同一截面日，不同股票"截至该日最新
已披露报告期"可能是年报/三季/中报/一季，量纲不同。本批因子未做跨股票报告期对齐
（全市场同口径截面排序，方向可比，但绝对值跨报告期不可比）。如需严格可比，后续可
改用 TTM 滚动口径或统一报告期对齐——列为改进项。

PIT 安全：快照严格按 pubDate<=as_of 过滤；因子值随披露日阶梯跳变（财报特性，非前视）。
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from factors.interface import register_factor, slice_panel_to_date
from data.pit_fundamentals import default_store
from data.pit import pit_float_mcap


# ---------- 取值 / 年度化辅助（同源 turnover_days._ann_factor）----------
def _val_sd(snap: dict, a: str, f: str):
    """资产 a 字段 f 的 (value, statDate)，NaN 安全。"""
    v, sd = snap.get(a, {}).get(f, (np.nan, None))
    return (v if pd.notna(v) else np.nan), sd


def _gv(snap: dict, a: str, f: str):
    """资产 a 字段 f 的取值（只取 value）。"""
    return _val_sd(snap, a, f)[0]


def _ann(val, sd) -> float:
    """流量项按报告期月份 → 年化系数（3→4, 6→2, 9→4/3, 12→1）。缺失/非季末月 → NaN。"""
    if not pd.notna(val) or sd is None or (isinstance(sd, float) and pd.isna(sd)):
        return np.nan
    try:
        m = pd.Timestamp(sd).month
    except Exception:
        return np.nan
    k = {3: 4.0, 6: 2.0, 9: 4.0 / 3.0, 12: 1.0}.get(m, np.nan)
    return val * k if pd.notna(k) else np.nan


class FundamentalFactorBase:
    """财报因子基类：统一取 PIT 快照 + 派发到子类 _calc。"""

    universe_hint = "hs300"

    def compute(self, panel: pd.DataFrame, as_of_date, ctx=None) -> pd.Series:
        t = pd.Timestamp(as_of_date)
        sub = slice_panel_to_date(panel, t)
        assets = sub.index.get_level_values("asset").unique().tolist()
        svc = (ctx or {}).get("pit_service")
        if svc is None:
            svc = default_store(assets, self.pit_fields)
        snap = svc.snapshot(assets, t, with_dates=True)
        return self._calc(snap, sub, t)

    def _calc(self, snap, sub, t) -> pd.Series:  # pragma: no cover
        raise NotImplementedError


# ---------------- 盈利/质量比率因子 ----------------
class ROEFactor(FundamentalFactorBase):
    name = "roe"
    fcode = "f0060a"
    pit_fields = ["net_profit_parent", "parent_equity"]

    def _calc(self, snap, sub, t):
        out = {}
        for a in snap:
            v, sd = _val_sd(snap, a, "net_profit_parent")
            pe = _gv(snap, a, "parent_equity")
            if pd.notna(v) and pd.notna(pe) and pe != 0:
                out[a] = _ann(v, sd) / pe
        return pd.Series(out, dtype=float)


class ROAFactor(FundamentalFactorBase):
    name = "roa"
    fcode = "f0061a"
    pit_fields = ["net_profit_parent", "total_assets"]

    def _calc(self, snap, sub, t):
        out = {}
        for a in snap:
            v, sd = _val_sd(snap, a, "net_profit_parent")
            ta = _gv(snap, a, "total_assets")
            if pd.notna(v) and pd.notna(ta) and ta != 0:
                out[a] = _ann(v, sd) / ta
        return pd.Series(out, dtype=float)


class GrossMarginFactor(FundamentalFactorBase):
    name = "gross_margin"
    fcode = "f0062a"
    pit_fields = ["revenue", "cogs"]

    def _calc(self, snap, sub, t):
        out = {}
        for a in snap:
            rv, cg = _gv(snap, a, "revenue"), _gv(snap, a, "cogs")
            if pd.notna(rv) and pd.notna(cg) and rv != 0:
                out[a] = (rv - cg) / rv
        return pd.Series(out, dtype=float)


class NetMarginFactor(FundamentalFactorBase):
    name = "net_margin"
    fcode = "f0063a"
    pit_fields = ["net_profit_parent", "revenue"]

    def _calc(self, snap, sub, t):
        out = {}
        for a in snap:
            np_, rv = _gv(snap, a, "net_profit_parent"), _gv(snap, a, "revenue")
            if pd.notna(np_) and pd.notna(rv) and rv != 0:
                out[a] = np_ / rv
        return pd.Series(out, dtype=float)


class AssetTurnoverFactor(FundamentalFactorBase):
    name = "asset_turnover"
    fcode = "f0064a"
    pit_fields = ["revenue", "total_assets"]

    def _calc(self, snap, sub, t):
        out = {}
        for a in snap:
            rv, sd = _val_sd(snap, a, "revenue")
            ta = _gv(snap, a, "total_assets")
            if pd.notna(rv) and pd.notna(ta) and ta != 0:
                out[a] = _ann(rv, sd) / ta
        return pd.Series(out, dtype=float)


class OperateProfitMarginFactor(FundamentalFactorBase):
    name = "operate_profit_margin"
    fcode = "f0065a"
    pit_fields = ["operate_profit", "revenue"]

    def _calc(self, snap, sub, t):
        out = {}
        for a in snap:
            op, rv = _gv(snap, a, "operate_profit"), _gv(snap, a, "revenue")
            if pd.notna(op) and pd.notna(rv) and rv != 0:
                out[a] = op / rv
        return pd.Series(out, dtype=float)


class FinancialLeverageFactor(FundamentalFactorBase):
    name = "financial_leverage"
    fcode = "f0066a"
    pit_fields = ["total_assets", "parent_equity"]

    def _calc(self, snap, sub, t):
        out = {}
        for a in snap:
            ta, pe = _gv(snap, a, "total_assets"), _gv(snap, a, "parent_equity")
            if pd.notna(ta) and pd.notna(pe) and pe != 0:
                out[a] = ta / pe
        return pd.Series(out, dtype=float)


class CashCoverageFactor(FundamentalFactorBase):
    name = "cash_coverage"
    fcode = "f0067a"
    pit_fields = ["ocf", "net_profit_parent"]

    def _calc(self, snap, sub, t):
        out = {}
        for a in snap:
            ocf, np_ = _gv(snap, a, "ocf"), _gv(snap, a, "net_profit_parent")
            if pd.notna(ocf) and pd.notna(np_) and np_ != 0:
                out[a] = ocf / np_
        return pd.Series(out, dtype=float)


class AccrualFactor(FundamentalFactorBase):
    name = "accrual"
    fcode = "f0068a"
    pit_fields = ["net_profit_parent", "ocf", "total_assets"]

    def _calc(self, snap, sub, t):
        out = {}
        for a in snap:
            np_v, np_sd = _val_sd(snap, a, "net_profit_parent")
            ocf_v, ocf_sd = _val_sd(snap, a, "ocf")
            ta = _gv(snap, a, "total_assets")
            if pd.notna(np_v) and pd.notna(ocf_v) and pd.notna(ta) and ta != 0:
                out[a] = (_ann(np_v, np_sd) - _ann(ocf_v, ocf_sd)) / ta
        return pd.Series(out, dtype=float)


class DeductRatioFactor(FundamentalFactorBase):
    name = "deduct_ratio"
    fcode = "f0069a"
    pit_fields = ["deduct_net_profit", "net_profit_parent"]

    def _calc(self, snap, sub, t):
        out = {}
        for a in snap:
            d, np_ = _gv(snap, a, "deduct_net_profit"), _gv(snap, a, "net_profit_parent")
            if pd.notna(d) and pd.notna(np_) and np_ != 0:
                out[a] = d / np_
        return pd.Series(out, dtype=float)


class EPFactor(FundamentalFactorBase):
    name = "ep"
    fcode = "f0070a"
    pit_fields = ["net_profit_parent"]

    def _calc(self, snap, sub, t):
        mcap = pit_float_mcap(sub, t)
        if mcap is None or len(mcap) == 0:
            return pd.Series(dtype=float)
        out = {}
        for a in snap:
            v, sd = _val_sd(snap, a, "net_profit_parent")
            m = mcap.get(a)
            if pd.notna(v) and pd.notna(m) and m > 0:
                out[a] = _ann(v, sd) / m
        return pd.Series(out, dtype=float)


class RevenueYoyFactor(FundamentalFactorBase):
    name = "revenue_yoy"
    fcode = "f0071a"
    pit_fields = ["operate_income_yoy"]

    def _calc(self, snap, sub, t):
        out = {}
        for a in snap:
            yoy = _gv(snap, a, "operate_income_yoy")
            if pd.notna(yoy):
                out[a] = yoy
        return pd.Series(out, dtype=float)


class NetProfitYoyFactor(FundamentalFactorBase):
    name = "netprofit_yoy"
    fcode = "f0072a"
    pit_fields = ["net_profit_parent_yoy"]

    def _calc(self, snap, sub, t):
        out = {}
        for a in snap:
            yoy = _gv(snap, a, "net_profit_parent_yoy")
            if pd.notna(yoy):
                out[a] = yoy
        return pd.Series(out, dtype=float)


for _f in [
    ROEFactor(), ROAFactor(), GrossMarginFactor(), NetMarginFactor(),
    AssetTurnoverFactor(), OperateProfitMarginFactor(), FinancialLeverageFactor(),
    CashCoverageFactor(), AccrualFactor(), DeductRatioFactor(),
    EPFactor(), RevenueYoyFactor(), NetProfitYoyFactor(),
]:
    register_factor(_f)
