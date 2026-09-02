"""筹码成本偏离因子（chip_cost_distance）。

逻辑：以「自样本起算的成交量加权持仓成本」作为全体持仓者平均成本代理，
测当前收盘价相对该成本的偏离度：
    cost_t = Σ(amount 截至 t) / Σ(volume 截至 t)        # 锚定 VWAP 成本
    factor = (close_t - cost_t) / cost_t

读数为负 = 现价低于平均持仓成本（套牢盘多，潜在支撑/吸筹区）；
读数为正 = 现价高于平均成本（获利盘多，潜在兑现压力）。
属「筹码分布」家族，与边际量价因子（overnight_intraday / ivol）正交。

PIT 安全：compute 仅用 as_of_date 及之前数据；cumsum 按资产分组递推，
不引用任何未来行；纯函数（无实例状态），满足 assert_no_lookahead 双调用一致性。
"""
from __future__ import annotations

import pandas as pd
import numpy as np

from factors.interface import register_factor


@register_factor
class ChipCostDistanceFactor:
    name = "chip_cost_distance"
    fcode = "f0004a"
    # 主场池声明（待 factor_universe_matrix 实测回填；锚定成本在大盘宽基更稳）
    universe_hint = "hs300"

    def compute(self, panel: pd.DataFrame, as_of_date, ctx=None) -> pd.Series:
        t = pd.Timestamp(as_of_date)
        # 保证 (asset, date) 时序有序，使分组 cumsum 为逐资产chrono累加
        sub = panel.sort_index()
        g = sub.groupby(level="asset")
        cum_amt = g["amount"].cumsum()
        cum_vol = g["volume"].cumsum()
        cost = cum_amt / cum_vol.replace(0, np.nan)
        cost_at_t = cost.xs(t, level="date")
        close_at_t = sub["close"].xs(t, level="date")
        factor = (close_at_t - cost_at_t) / cost_at_t
        return factor.dropna()


register_factor(ChipCostDistanceFactor())
