"""Amihud 跳跃成分占比因子（amihud_jump_share）。

对应灵感池 i20260914-010：个股 realized Amihud 非流动性 的跳跃(jump)成分占比
截面越高 → 未来流动性枯竭风险 / 收益波动越高（收益越低）。

实现（纯 close/amount，逐资产截至 t，全部向后看，无前视）：
    ret      = close.pct_change(1)
    amihud_t = |ret| / amount                (amount=0 → NaN 防除零)
    jump_t   = |ret| > JUMP_K × rolling(W).std(|ret|)   (统计异常跳变日，W=60)
    factor_t = Σ_{w} amihud[jump] / Σ_{w} amihud        # W=60 窗口内跳跃成分占比

PIT 安全：仅用 close / amount（t 日及之前可观测量），不引用 market_cap 快照列。
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from factors.interface import register_factor

W = 60
JUMP_K = 3.0


@register_factor
class AmihudJumpShareFactor:
    name = "amihud_jump_share"
    fcode = "f0085a"
    universe_hint = None

    def compute(self, panel: pd.DataFrame, as_of_date, ctx=None) -> pd.Series:
        t = pd.Timestamp(as_of_date)
        sub = panel.sort_index()
        close = sub["close"]
        amount = sub["amount"].replace(0, np.nan)
        ret = close.groupby(level="asset").transform(lambda s: s.pct_change(1))
        abs_ret = ret.abs()
        amihud = abs_ret / amount
        # 逐资产滚动 60 日 |ret| 标准差作跳跃阈值
        vol = abs_ret.groupby(level="asset").transform(
            lambda s: s.rolling(W, min_periods=W // 2).std()
        )
        jump = abs_ret > JUMP_K * vol
        # 🔴 跳跃日稀疏（60 日内通常仅个位数），滚动求和必须 min_periods=1 且非跳跃日填 0，
        # 否则窗口内非 NaN 数永远 <30 → 全 NaN → 因子空（实测首版 n=0）。
        # 语义：跳跃成分占比 = Σ(跳跃日 Amihud) / Σ(全期 Amihud)，无跳跃日→0。
        jump_amihud = (amihud.where(jump, 0.0)).groupby(level="asset").transform(
            lambda s: s.rolling(W, min_periods=1).sum()
        )
        tot_amihud = amihud.groupby(level="asset").transform(
            lambda s: s.rolling(W, min_periods=W // 2).sum()
        )
        share = (jump_amihud / tot_amihud).replace([np.inf, -np.inf], np.nan)
        return share.xs(t, level="date").dropna().rename(self.name)


register_factor(AmihudJumpShareFactor())
