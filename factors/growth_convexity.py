"""双重增长凸性因子（growth_convexity）。

对应灵感池 i20260910-002：个股 营收同比 × 净利同比 交互项（双重增长凸性）截面越高
→ 未来 20 日收益越高（高质量成长：收入与利润同步加速，非单项虚增）。

实现（PIT 安全）：
    因子值 = operate_income_yoy（营收同比）× net_profit_parent_yoy（归母净利同比）
    两项均为 AkShare 三表、NOTICE_DATE 真实公告日对齐（无前视），随披露日阶梯跳变。
    属纯比率乘积，无分母、无市值口径问题。

🔴 口径红线：仅用 PIT 财报字段，绝不读面板 market_cap 快照列（今日市值回填全历史
= 假 PIT，会把未来收益注入残差）。
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from factors.interface import register_factor, slice_panel_to_date
from factors.fundamentals import FundamentalFactorBase, _gv


@register_factor
class GrowthConvexityFactor(FundamentalFactorBase):
    name = "growth_convexity"
    fcode = "f0082a"
    pit_fields = ["operate_income_yoy", "net_profit_parent_yoy"]

    def _calc(self, snap, sub, t):
        out = {}
        for a in snap:
            ry = _gv(snap, a, "operate_income_yoy")
            ny = _gv(snap, a, "net_profit_parent_yoy")
            if pd.notna(ry) and pd.notna(ny):
                out[a] = ry * ny
        return pd.Series(out, dtype=float)

    def compute_panel(self, panel, ctx=None) -> pd.DataFrame:
        """分子走阶梯（财报披露日）：营收同比 × 净利同比。"""
        return self._step_panel(
            panel,
            lambda snap, a, t: (
                _gv(snap, a, "operate_income_yoy") * _gv(snap, a, "net_profit_parent_yoy")
            ),
            ctx,
        )


register_factor(GrowthConvexityFactor())
