"""价值因子：账面市值比 B/M（i20260903-010，f0078a）。

对应灵感池 i20260903-010：价值因子的有效性高度依赖市值分域，账面市值比的多头
超额几乎只存在于小市值组。本模块先交付**基础 B/M 因子**（母公募净资产 / PIT 流通市值），
"按市值分域施用"作为组合层改进项后续接入。

实现（PIT 安全）：
    分子 = 归母净资产 parent_equity（AkShare 三表，NOTICE_DATE 真实公告日对齐，无前视）
    分母 = PIT 流通市值 pit_float_mcap（amount/(turnover/100) 现算，取前一日近 5 日中位数）
    B/M = parent_equity / mcap（值随披露日阶梯跳变 = 财报特性，非前视）

🔴 口径红线：分母必须与 data.pit.pit_float_mcap 同口径（见 _mcap_grid 与单测对照），
    绝不用面板 market_cap 快照列（今日市值回填全历史 = 假 PIT，会把未来收益注入残差）。
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from factors.interface import register_factor, slice_panel_to_date
from factors.fundamentals import FundamentalFactorBase, _gv, _mcap_grid
from data.pit import pit_float_mcap


@register_factor
class ValueBMFactor(FundamentalFactorBase):
    name = "value_bm"
    fcode = "f0078a"
    pit_fields = ["parent_equity"]

    def _calc(self, snap, sub, t):
        mcap = pit_float_mcap(sub, t)
        out = {}
        for a in snap:
            pe = _gv(snap, a, "parent_equity")
            m = (mcap.get(a) if mcap is not None else np.nan)
            if pd.notna(pe) and pd.notna(m) and m > 0:
                out[a] = pe / m
        return pd.Series(out, dtype=float)

    def compute_panel(self, panel, ctx=None) -> pd.DataFrame:
        """分子走阶梯（财报披露日），分母走逐日 PIT 市值网格（与 pit_float_mcap 同口径）。"""
        num = self._step_panel(
            panel, lambda snap, a, t: _gv(snap, a, "parent_equity"), ctx
        )
        den = _mcap_grid(panel).reindex(index=num.index, columns=num.columns)
        if den is None or den.empty:
            return pd.DataFrame(index=num.index)
        return num / den.where(den > 0)


register_factor(ValueBMFactor())
