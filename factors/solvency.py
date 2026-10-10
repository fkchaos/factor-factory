"""Phase A 数据源扩展因子（f0092a–f0094a，2026-10-10）：偿债能力 + 研发强度。

灵感来源：
  f0092a 流动比率  ← i20260903-008「偿债能力类财务比率本身即是 A 股截面收益的有效因子」
  f0093a 速动比率  ← 同上（(流动资产−存货)/流动负债，比流动比率更严格）
  f0094a 研发强度  ← i20260903-009「无形资产调整 B/M」的**前置件**
                     （本体需近 5 年研发序列做 20% 年摊销资本化，多期依赖，另排 f0095a）

数据源（**多后端**）：
  - current_ratio / quick_ratio ← **BaoStock** `query_balance_data`（带 pubDate，PIT 合规）
  - rd_expense                  ← **AkShare** 东财利润表 `RESEARCH_EXPENSE`
  详见 `data/pit_fundamentals.py` 与 `docs/dev/PLAN_PHASE_A_DATA.md`。

🔴 为什么流动/速动比率取现成比率而不自算（2026-10-10 实测）：
东财 `stock_balance_sheet_by_report_em` 的 `CURRENT_ASSET_BALANCE` / `CURRENT_LIAB_BALANCE`
**不可用**——茅台恒 0.0、宁德 -1000（缺失哨兵值）、银行股 NaN。用它自算会造出假因子。
故直接取 baostock 官方口径比率（实测茅台 5.98/5.04、格力 1.12/0.93，量级合理）。

🔴 与 Phase 0 财报因子的关键差异：**本批不需年度化**
  - 流动/速动比率 = 时点项之比（流动资产÷流动负债），天然可比。
  - 研发强度 = 研发支出÷营业收入，**两者同为流量项且取自同一报告期**，年化系数可约掉。
  故本模块不使用 `_ann()`。

⚠️ 金融股（银行/保险/券商）current_ratio / quick_ratio / rd_expense 天然 NaN：
银行报表不分流动/非流动，也不列研发费用。这是**行业特性**而非数据缺陷——
因子侧按 NaN 处理（截面排序时自动排除），**不填充、不伪造、不用行业均值插补**。
实测 600036.SH（招行）三字段全 NaN，asset_to_equity 仍有值（10.45），符合预期。

⚠️ 季度报告期混合口径偏差（如实标注，与 Phase 0 同类，非前视）：
同一截面日，不同股票"截至该日最新已披露报告期"可能是一季/中报/三季/年报。
研发支出存在 Q4 集中确认的季节性，研发强度的**绝对值**跨报告期不可比；
截面排序方向仍可比，但强度值本身有季节性噪声。如需严格可比可改 TTM 口径（改进项）。
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from factors.fundamentals import FundamentalFactorBase, _gv
from factors.interface import register_factor


class CurrentRatioFactor(FundamentalFactorBase):
    """f0092a 流动比率 = 流动资产 / 流动负债（baostock 官方口径）。

    灵感假设：流动比率截面分位越高 → 未来 20 日收益越高（行业+PIT 市值中性化后）。
    方向交由 IC 实测，不预设符号。
    """
    name = "current_ratio"
    fcode = "f0092a"
    pit_fields = ["current_ratio"]

    def _calc(self, snap, sub, t) -> pd.Series:
        out = {}
        for a in snap:
            v = _gv(snap, a, "current_ratio")
            # v>0 过滤：非正比率（资不抵债或哨兵值）不入截面，按缺失处理而非截断
            if pd.notna(v) and v > 0:
                out[a] = float(v)
        return pd.Series(out, dtype=float)


class QuickRatioFactor(FundamentalFactorBase):
    """f0093a 速动比率 = (流动资产 − 存货) / 流动负债（baostock 官方口径）。

    比流动比率更严格（剔除变现能力最差的存货），与 f0092a 预期高度相关
    → 出包后须过冗余前置闸门；若 |ρ|≥0.7 应合并或只留其一。
    """
    name = "quick_ratio"
    fcode = "f0093a"
    pit_fields = ["quick_ratio"]

    def _calc(self, snap, sub, t) -> pd.Series:
        out = {}
        for a in snap:
            v = _gv(snap, a, "quick_ratio")
            if pd.notna(v) and v > 0:
                out[a] = float(v)
        return pd.Series(out, dtype=float)


class RDIntensityFactor(FundamentalFactorBase):
    """f0094a 研发强度 = 研发支出 / 营业收入（同为流量项，年化系数可约）。

    经济含义：研发资本化程度高的公司，账面净资产被系统性低估（研发费用化不入账），
    标准 B/M 对其失真。本因子是该链条的**可观测代理**，非最终调整 B/M。
    金融股天然 NaN（不列研发），制造业/科技股为主要覆盖域。
    """
    name = "rd_intensity"
    fcode = "f0094a"
    pit_fields = ["rd_expense", "revenue"]

    def _calc(self, snap, sub, t) -> pd.Series:
        out = {}
        for a in snap:
            rd = _gv(snap, a, "rd_expense")
            rv = _gv(snap, a, "revenue")
            # rd==0 保留（真实"不研发"信号）；rv<=0 或缺失 → 不入截面
            if pd.notna(rd) and pd.notna(rv) and rv > 0 and rd >= 0:
                out[a] = float(rd) / float(rv)
        return pd.Series(out, dtype=float)


for _f in [CurrentRatioFactor(), QuickRatioFactor(), RDIntensityFactor()]:
    register_factor(_f)
