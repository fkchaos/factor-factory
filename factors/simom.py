"""短期特质动量因子（simom，Short-term Idiosyncratic Momentum）。

对应灵感池 i20261001-001：Eom(2026, SSRN 4370153) 将传统 12 个月 IMOM 压缩到
前 1 个月形成期，构建"短期特质动量"——基于个股近 1 个月日频残差收益复利，
仍可正向预测至多 8 个月收益，且与 IVOL / 短期反转区分（保留独立信息）。

实现（纯 close，逐资产截至 t，满足 assert_no_lookahead）：
    1) ret    = close 逐资产 pct_change(1)
    2) mkt    = 每日跨资产等权平均收益（系统性成分代理，面板无行业列）
    3) beta   = 逐资产 trailing W_BETA=60 日 ret 对 mkt 滚动回归斜率
    4) resid  = ret − beta · mkt                      （市场模型特质残差）
    5) simom  = Π_{s=t−20..t}(1 + resid_s) − 1       （近 21 日残差复利）
              = expm1( Σ log1p(resid) over 21d )，与乘积数学等价、数值更稳

经济含义：个股近期"剔除系统性/行业后的自身收益"持续为正 → 未来 1-8 月收益更高。
与 f0043a(idiosyncratic_share=1−R² 波动率占比) / f0051a(idio_tail_beta 下尾敏感度)
视角不同：本因子刻画特质收益的**方向性动量**，而非波动占比或尾部敏感度。

PIT 安全：仅用 close；不引用 market_cap 快照列（市值暴露由 harness 用 pit_float_mcap 剥离）。
纯函数，满足 assert_no_lookahead（harness 传入 panel 已截断至 as_of_date）。
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from factors.interface import register_factor

W_BETA = 60   # 滚动 beta 估计窗口（交易日）
W_COMP = 21   # 残差复利窗口（≈1 个月交易日）


@register_factor
class SimomFactor:
    """短期特质动量：近 21 日市场模型残差复利。"""

    name = "simom"
    fcode = "f0088a"
    universe_hint = None

    def compute(self, panel: pd.DataFrame, as_of_date, ctx=None) -> pd.Series:
        t = pd.Timestamp(as_of_date)
        sub = panel.sort_index()

        ret = sub["close"].groupby(level="asset").pct_change()
        # 系统性代理：每日等权市场收益
        mkt = ret.groupby(level="date").mean()
        mkt_aligned = pd.Series(
            ret.index.get_level_values("date").map(mkt), index=ret.index
        )

        df = pd.DataFrame(index=ret.index)
        df["ra"] = ret
        df["mkt"] = mkt_aligned
        df["ra_mkt"] = ret * mkt_aligned

        g = df.groupby(level="asset")
        m_ra = g["ra"].transform(lambda s: s.rolling(W_BETA).mean())
        m_mkt = g["mkt"].transform(lambda s: s.rolling(W_BETA).mean())
        m_ra_mkt = g["ra_mkt"].transform(lambda s: s.rolling(W_BETA).mean())
        var_mkt = g["mkt"].transform(lambda s: s.rolling(W_BETA).var())

        cov = m_ra_mkt - m_ra * m_mkt
        with np.errstate(divide="ignore", invalid="ignore"):
            beta = cov / var_mkt
        beta = beta.fillna(0.0)
        resid = ret - beta * mkt_aligned            # 特质残差收益

        # 近 W_COMP 日残差复利（log1p 求和再 expm1 = 乘积−1，数值更稳）
        log1p_resid = np.log1p(resid.clip(lower=-0.9999))
        comp_sum = log1p_resid.groupby(level="asset").transform(
            lambda s: s.rolling(W_COMP).sum()
        )
        simom = np.expm1(comp_sum)

        return simom.xs(t, level="date").dropna().rename(self.name)

    def compute_panel(self, panel: pd.DataFrame) -> pd.DataFrame:
        """向量化全序列（供 build_deliverable 快路径 O(N) 使用）。

        与 compute 同口径：对完整 panel 一次性算滚动 beta 残差 → 21 日残差复利，
        再 unstack 成 date×asset 的 DataFrame（index=date, columns=asset）。
        滚动均为因果算子（只用 ≤t 的数据），PIT 安全。
        """
        sub = panel.sort_index()
        ret = sub["close"].groupby(level="asset").pct_change()
        mkt = ret.groupby(level="date").mean()
        mkt_aligned = pd.Series(
            ret.index.get_level_values("date").map(mkt), index=ret.index
        )
        df = pd.DataFrame(index=ret.index)
        df["ra"] = ret
        df["mkt"] = mkt_aligned
        df["ra_mkt"] = ret * mkt_aligned

        g = df.groupby(level="asset")
        m_ra = g["ra"].transform(lambda s: s.rolling(W_BETA).mean())
        m_mkt = g["mkt"].transform(lambda s: s.rolling(W_BETA).mean())
        m_ra_mkt = g["ra_mkt"].transform(lambda s: s.rolling(W_BETA).mean())
        var_mkt = g["mkt"].transform(lambda s: s.rolling(W_BETA).var())

        cov = m_ra_mkt - m_ra * m_mkt
        with np.errstate(divide="ignore", invalid="ignore"):
            beta = cov / var_mkt
        beta = beta.fillna(0.0)
        resid = ret - beta * mkt_aligned

        log1p_resid = np.log1p(resid.clip(lower=-0.9999))
        comp_sum = log1p_resid.groupby(level="asset").transform(
            lambda s: s.rolling(W_COMP).sum()
        )
        simom = np.expm1(comp_sum)

        return simom.unstack(level="asset")  # date × asset


register_factor(SimomFactor())
