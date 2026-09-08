"""市场beta × 量波动交互因子（beta_qvol_interact）· f0058a。

对应灵感池 i20260907-001（paper，arXiv 2026-09-04）：个股对宽基的暴露 beta 与其由
交易流 induced 的"数量"波动 q（以近 20 日换手率序列波动 proxy）的交互项 beta×q
截面越高 → 未来 20 日收益越高（高暴露股吸收噪声交易流，要求更高风险补偿）。

机制
----
原模型用于解释"截面风险-收益关系近乎平坦"这一长期难题：风险补偿并非由 beta 单独
决定，而由 beta 与其**承接的交易流数量波动**共同决定——只有当高 beta 股同时承担
大量噪声交易流冲击时，才索取显著的风险溢价。故交互项而非任一单项才是定价变量。

实现（close + turnover，向后看）
--------------------------------
    ret_i   = close 逐资产 pct_change(1)
    mkt     = 每日跨资产等权平均收益（池内等权代理宽基）
    beta_i  = cov(ret_i, mkt) / var(mkt)，滚动 BETA_WIN=60 日
    q_i     = std(turnover, 20) / mean(turnover, 20)  （近 20 日换手率变异系数）
    factor  = beta_i × q_i

q 用**变异系数**而非标准差：换手率水平本身有强烈的市值/流动性截面差异，直接用 std
等于混入了规模因子；除以均值后得到无量纲的"相对波动"，更贴近原文"数量波动"语义。

冗余提示
--------
须与 f0002a（特质波动率）、f0030a（20 日成交量变异系数）、f0042a（分歧度代理）核对
相关性——本因子的 q 部分与 f0030a 语义邻近（一个用成交量、一个用换手率），
差别在于本因子把它与 beta 相乘。若相关 >0.8 应视作同族并降级，见 correlation.csv。

PIT 安全：仅用 close / turnover；不读 market_cap 快照列（市值暴露由 harness 用
pit_float_mcap 中性化剥离）。turnover 为 baostock 当日换手率（逐日变化，非快照回填）。
compute_panel 一次性向量化全序列（rolling cov/var 矩阵化）。
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from factors.interface import register_factor

BETA_WIN = 60   # beta 滚动窗口
Q_WIN = 20      # 换手率变异系数窗口


class BetaQvolInteractFactor:
    """beta×q 交互项：60 日市场 beta × 20 日换手率变异系数。"""

    name = "beta_qvol_interact"
    fcode = "f0058a"
    universe_hint = None

    def _full(self, panel: pd.DataFrame) -> pd.Series:
        sub = panel.sort_index()
        close = sub["close"]
        R = close.unstack(level="asset").pct_change(fill_method=None)   # T x A 个股日收益
        mkt = R.mean(axis=1, skipna=True)                              # 等权市场日收益

        # 滚动 beta = cov(r_i, r_m) / var(r_m)，全矩阵化：
        # cov = E[r_i·r_m] − E[r_i]·E[r_m]
        minp = max(20, BETA_WIN // 2)
        mkt_mat = pd.DataFrame(
            np.repeat(mkt.values[:, None], R.shape[1], axis=1),
            index=R.index, columns=R.columns).where(R.notna())
        e_im = (R * mkt_mat).rolling(BETA_WIN, min_periods=minp).mean()
        e_i = R.rolling(BETA_WIN, min_periods=minp).mean()
        e_m = mkt_mat.rolling(BETA_WIN, min_periods=minp).mean()
        var_m = (mkt_mat ** 2).rolling(BETA_WIN, min_periods=minp).mean() - e_m ** 2
        cov_im = e_im - e_i * e_m
        with np.errstate(divide="ignore", invalid="ignore"):
            beta = cov_im / var_m.where(var_m > 0)

        # q = 换手率变异系数
        TO = sub["turnover"].unstack(level="asset")
        q_minp = max(10, Q_WIN // 2)
        to_mu = TO.rolling(Q_WIN, min_periods=q_minp).mean()
        to_sd = TO.rolling(Q_WIN, min_periods=q_minp).std()
        with np.errstate(divide="ignore", invalid="ignore"):
            q = to_sd / to_mu.where(to_mu > 0)

        out = (beta * q).replace([np.inf, -np.inf], np.nan)
        return out.stack().reindex(close.index)

    def compute(self, panel: pd.DataFrame, as_of_date, ctx=None) -> pd.Series:
        t = pd.Timestamp(as_of_date)
        return self._full(panel).xs(t, level="date").dropna().rename(self.name)

    def compute_panel(self, panel: pd.DataFrame) -> pd.DataFrame:
        return self._full(panel).unstack(level="asset")


register_factor(BetaQvolInteractFactor())
