"""盈利质量边际改善因子：ΔROE（i20260907-006，f0079a）。

对应灵感池 i20260907-006：全 A 非金融 ROE 企稳改善（杜邦拆解净利率/周转率共升），
盈利加速（连续两季加速 + 现金流双加速）为 alpha 线索。本模块交付**ΔROE** =
最新已披露报告期 ROE 相对上一报告期 ROE 的环比变动（盈利质量边际改善，非静态 ROE 水平）。

实现（PIT 安全）：
    ROE(a, t) = 年化归母净利 / 归母净资产，取截至 as_of 最新已披露报告期
    分子（net_profit_parent）按 statDate 月份年化（Q1→×4 / H1→×2 / Q3→×4/3 / 年报→×1）
    分母 parent_equity 为时点项不年化
    ΔROE = ROE_latest − ROE_prev（相邻两次披露之间阶梯恒定，披露日更新）

🔴 口径红线：快照严格按 pubDate<=as_of 过滤（NOTICE_DATE 真实公告日对齐，无前视）；
    年化系数与 f0060a ROE 完全一致，保证口径可比。
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from factors.interface import register_factor
from factors.fundamentals import (
    FundamentalFactorBase, _gv, _val_sd, _ann,
)


@register_factor
class DeltaROEFactor(FundamentalFactorBase):
    name = "delta_roe"
    fcode = "f0079a"
    pit_fields = ["net_profit_parent", "parent_equity"]

    def _roe(self, snap, a):
        v, sd = _val_sd(snap, a, "net_profit_parent")
        pe = _gv(snap, a, "parent_equity")
        if pd.notna(v) and pd.notna(pe) and pe != 0:
            return _ann(v, sd) / pe
        return np.nan

    def compute_panel(self, panel, ctx=None) -> pd.DataFrame:
        """先算阶梯 ROE 面板，再对每只股票取相邻披露期之差（ΔROE）。"""
        roe = self._step_panel(
            panel, lambda snap, a, t: self._roe(snap, a), ctx
        )
        if roe is None or roe.empty:
            return pd.DataFrame(index=panel.index.get_level_values("date").unique())
        out = roe.copy()
        for a in roe.columns:
            s = roe[a].dropna()
            if len(s) < 2:
                out[a] = np.nan
                continue
            d = s.diff()
            out[a] = d.reindex(out.index)
        return out


register_factor(DeltaROEFactor())
