"""存货周转天数 / 应收账款周转天数 因子（首批财报类因子，f0014a / f0015a）。

数据源：AkShare 东财明细表（baostock 免费接口不返 cogs/inventory/accounts_receivable，
见 BaoStockProvider._PIT_FIELD_UNAVAILABLE）。取数经 PitFinancialsService 走 NOTICE_DATE
真实公告日对齐，杜绝前视。

定义（取截至 as_of 最新已披露报告期，字段独立取数）：
  f0014a 存货周转天数     = 365 × inventory        / (cogs     × 年化系数)
  f0015a 应收账款周转天数 = 365 × accounts_receivable / (revenue  × 年化系数)

🔴 年度化（关键）：cogs / revenue 是**流量项**（利润表，季报只覆盖 3/6/9 个月），
若直接 365×存货/季度cogs 会把周转天数高估 2~4 倍，截面只反映"报告期类型"而非真实运营。
故用流量项自身取值来源的 statDate 月份反推覆盖月数 → 年化系数：
  statDate 月 = 3(Q1)→4, 6(H1)→2, 9(Q3)→4/3, 12(年报)→1。
inventory / accounts_receivable 是**存量项**（资产负债表时点值），不参与年化。

PIT 安全：快照按 pubDate<=as_of 过滤；回测逐日调用 compute，每个 as_of 取当时可知最新披露，
绝不用未公告财报。因子值随披露日阶梯跳变（财报特性，非前视）。

绩效口径：harness 仍做 MAD 去极值 + 截面 Z + 行业/市值(PIT) 中性化；本文件只算原始周转天数。
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from factors.interface import register_factor, slice_panel_to_date
from data.pit_fundamentals import default_store


def _ann_factor(stat_date) -> float:
    """流量项 statDate 月份 → 年化系数（覆盖月数反推）。缺失/非季末月 → NaN。"""
    if stat_date is None or (isinstance(stat_date, float) and np.isnan(stat_date)):
        return np.nan
    try:
        m = pd.Timestamp(stat_date).month
    except Exception:
        return np.nan
    return {3: 4.0, 6: 2.0, 9: 4.0 / 3.0, 12: 1.0}.get(m, np.nan)


def _turnover_days(snap: dict, balance_field: str, flow_field: str) -> pd.Series:
    """从带披露日的快照算周转天数。snap: asset -> {field: (value, statDate)}。"""
    out = {}
    for asset, vals in snap.items():
        bal, _ = vals[balance_field]
        (flow, flow_sd) = vals[flow_field]
        if not (pd.notna(bal) and pd.notna(flow) and flow > 0):
            continue
        ann = _ann_factor(flow_sd)
        if not pd.notna(ann):
            continue
        out[asset] = 365.0 * bal / (flow * ann)
    return pd.Series(out, dtype=float)


@register_factor
class InventoryTurnoverDaysFactor:
    name = "inventory_turnover_days"
    fcode = "f0014a"
    universe_hint = "hs300"
    pit_fields = ["inventory", "cogs"]

    def compute(self, panel: pd.DataFrame, as_of_date, ctx=None) -> pd.Series:
        t = pd.Timestamp(as_of_date)
        sub = slice_panel_to_date(panel, t)
        assets = sub.index.get_level_values("asset").unique().tolist()
        svc = (ctx or {}).get("pit_service")
        if svc is None:
            svc = default_store(assets, self.pit_fields)
        snap = svc.snapshot(assets, t, with_dates=True)
        return _turnover_days(snap, "inventory", "cogs")


@register_factor
class AccountReceivableTurnoverDaysFactor:
    name = "ar_turnover_days"
    fcode = "f0015a"
    universe_hint = "hs300"
    pit_fields = ["accounts_receivable", "revenue"]

    def compute(self, panel: pd.DataFrame, as_of_date, ctx=None) -> pd.Series:
        t = pd.Timestamp(as_of_date)
        sub = slice_panel_to_date(panel, t)
        assets = sub.index.get_level_values("asset").unique().tolist()
        svc = (ctx or {}).get("pit_service")
        if svc is None:
            svc = default_store(assets, self.pit_fields)
        snap = svc.snapshot(assets, t, with_dates=True)
        return _turnover_days(snap, "accounts_receivable", "revenue")


register_factor(InventoryTurnoverDaysFactor())
register_factor(AccountReceivableTurnoverDaysFactor())
