"""收益反向交叉次数因子（reverse_cross_60）。

对应灵感池 i20260903-004：过去 60 个交易日中，日收益方向与市场（等权全 A）日收益方向
相反的交易日数量越多 → 未来 20 日收益越低。经济含义：个股频繁与市场"对着干"= 逆向交易
者 / 情绪化博弈占比高，后续走弱概率大。

实现（纯 close，市场收益用截面等权均值代理，逐资产截至 t）：
  对每个截至 t 的交易日 d（取 t 及之前最近 60 个交易日）：
    r_i,d = close_i,d / close_i,d-1 - 1
    r_mkt,d = 截面等权均值(r_j,d)   # 市场收益代理
    若 sign(r_i,d) != sign(r_mkt,d) 且两者均非零 → 计 1
  因子值 = 窗口内计 1 的天数（范围 0~60）。

PIT 安全：仅用 ≤t 的 close；市场收益为同期截面均值、无未来信息；
不引用 market_cap 快照列（市值暴露由 harness 用 pit_float_mcap 剥离）。
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from factors.interface import register_factor, slice_panel_to_date


@register_factor
class ReverseCross60Factor:
    name = "reverse_cross_60"
    fcode = "f0037a"  # 交付包代号（对齐 deliverables/factors/_REGISTRY.csv）
    universe_hint = "hs300"

    def compute(self, panel: pd.DataFrame, as_of_date, ctx=None) -> pd.Series:
        as_of = pd.Timestamp(as_of_date)
        sub = slice_panel_to_date(panel, as_of)
        dates = sorted(d for d in sub.index.get_level_values("date").unique() if d <= as_of)
        if len(dates) < 62:
            return pd.Series(dtype=float, name=self.name)

        window = dates[-61:]  # 61 个交易日 → 60 个日收益
        sub_w = sub.loc[sub.index.get_level_values("date").isin(window)]
        close_w = sub_w["close"].unstack("asset")
        ret_w = close_w.pct_change().iloc[1:]  # 60 × assets，每行一交易日
        if ret_w.empty:
            return pd.Series(dtype=float, name=self.name)

        mkt_w = ret_w.mean(axis=1)  # 截面等权市场收益
        sig_ret = np.sign(ret_w.values)
        sig_mkt = np.sign(mkt_w.values).reshape(-1, 1)
        mismatch = (
            (sig_ret != sig_mkt)
            & (ret_w.values != 0)
            & (mkt_w.values.reshape(-1, 1) != 0)
        )
        count = mismatch.sum(axis=0)
        return pd.Series(count, index=ret_w.columns, name=self.name)


register_factor(ReverseCross60Factor())
