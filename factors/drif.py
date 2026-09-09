"""DRIF（Daily Return Information Factor，i20260810-001）。

对应灵感池 i20260810-001：上月日收益序列（排序向量）本身即统一异象信息源，
DRIF 宣称可吸收绝大多数短周期与彩票型异象（短期反转 / MAX5 / MIN3 等）。

实现（纯 close，逐资产截至 t，无前视）：
    取截至 as_of 最近 W=21 个交易日的日收益，升序排列得到 21 维分位向量；
    对各维做固定权重线性组合（权重为预先设定的"尾部形态"权重：
    最负 3 日与最正 3 日取 ±1，中间为 0），得到每只股票的"收益分布形态"打分。

🔴 关于 IC 符号加权：原论文用滚动历史 IC 符号加权，但那需要在 compute 内用
    未来收益估计 IC —— 违反 assert_no_lookahead 红线。故以**固定尾部形态权重**
    替代（极值越高→打分越高）。真实 IC 与方向由 harness 独立估计，本模块不偷看未来。

PIT 安全：仅用 close；不引用 market_cap 快照列（市值暴露由 harness 剥离）。
纯函数，满足 assert_no_lookahead（compute_panel 窗口止于 t，无未来数据）。
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from numpy.lib.stride_tricks import sliding_window_view

from factors.interface import register_factor

W = 21
# 固定"尾部形态"权重：升序 21 维，最负 3 日=-1、最正 3 日=+1、中段=0。
_W = np.zeros(W, dtype=float)
_W[[0, 1, 2]] = -1.0
_W[[18, 19, 20]] = 1.0


@register_factor
class DRIFFactor:
    name = "drif"
    fcode = "f0077a"
    universe_hint = None

    def compute_panel(self, panel: pd.DataFrame, ctx=None) -> pd.DataFrame:
        """全序列一次性算出（index=date, columns=asset）；窗口止于 each date，无前视。"""
        closes = panel["close"].unstack("asset")
        if closes.empty:
            return pd.DataFrame(index=panel.index.get_level_values("date").unique())
        rets = closes.pct_change()
        out = pd.DataFrame(index=closes.index, columns=closes.columns, dtype=float)
        for a in closes.columns:
            s = rets[a].to_numpy(dtype=float, na_value=np.nan)
            n = len(s)
            res = np.full(n, np.nan)
            if n >= W:
                wv = sliding_window_view(s, W)              # (n-W+1, W)
                ok = ~np.isnan(wv).any(axis=1)
                idx = np.where(ok)[0]
                if len(idx):
                    svals = np.sort(wv[idx], axis=1)        # 升序
                    res[idx + W - 1] = svals @ _W
            out[a] = res
        return out

    def compute(self, panel: pd.DataFrame, as_of_date, ctx=None) -> pd.Series:
        t = pd.Timestamp(as_of_date)
        full = self.compute_panel(panel, ctx)
        if full is None or full.empty:
            return pd.Series(dtype=float, name=self.name)
        try:
            return full.loc[t].dropna().rename(self.name)
        except KeyError:
            return pd.Series(dtype=float, name=self.name)


register_factor(DRIFFactor())
