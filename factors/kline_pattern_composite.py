"""K 线形态综合因子（kline_pattern_composite）。

对应灵感池 i20261005-006：金融工程专题(新浪/2026) 梳理 33 种 K 线形态，按各形态最佳
持有期 Kelly 值离散化打分并叠加得综合 K 线因子；再用"价量共振"情绪调整系数
（近 5 日量能 / 60 日均线变化）修正，五分组单调。

A 股落地口径（纯 OHLC，无前视；情绪系数用 volume 近 5/60 日量能比）：
    1) 由 open/high/low/close 拆解每根 K 线：实体 body、上影 upper、下影 lower（均归一
       到 (high−low)，+ 为阳线方向）
    2) 每日 K 线多空指数 KBI：
         + body                阳线方向强度
         + 0.5*(lower − upper) 锤头(下影长) vs 流星(上影长) 反转倾向
         + bull_engulf          （今阳吞昨阴，且实体更大）→ +1
         − bear_engulf          （今阴吞昨阳，且实体更大）→ −1
    3) 综合分 = 近 10 日 KBI 滚动均值（捕捉"近期形态强度"）
    4) 情绪系数 = tanh(vol_5/vol_60 − 1)（量能放大→正，放大本因子权重；缩量→负，抑制）
    5) 因子 = 综合分 × 情绪系数

经济含义：近期 K 线组合偏多（锤头/阳吞阴）且处放量共振 regime → 短期动量延续/反转收益更高。
与已落的长上/下影(f0036a/f0028a)、第二阶段突破(f0087a)、反转类(f0049a/f0050a) 不同——
本因子是**多形态加权合成**且引入**量能情绪系数**作为条件权重。

PIT 安全：仅用 open/high/low/close/volume（均为 t 日及之前可观测量）；不引用 market_cap
快照列（市值暴露由 harness 用 pit_float_mcap 剥离）。
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from factors.interface import register_factor

W_KBI = 10    # K 线综合分滚动窗口
W_VOL_S = 5   # 量能短窗
W_VOL_L = 60  # 量能长窗
EPS = 1e-9


@register_factor
class KlinePatternCompositeFactor:
    """K 线形态综合：近 10 日多形态加权分 × 量能情绪系数。"""

    name = "kline_pattern_composite"
    fcode = "f0090a"
    universe_hint = None

    def compute(self, panel: pd.DataFrame, as_of_date, ctx=None) -> pd.Series:
        t = pd.Timestamp(as_of_date)
        df = self._kbi_panel(panel)
        return df.xs(t, level="date").dropna().rename(self.name)

    def compute_panel(self, panel: pd.DataFrame) -> pd.DataFrame:
        df = self._kbi_panel(panel)
        return df.unstack(level="asset")  # date × asset

    def _kbi_panel(self, panel: pd.DataFrame) -> pd.DataFrame:
        sub = panel.sort_index()
        g = sub.groupby(level="asset")
        o, h, l, c, v = sub["open"], sub["high"], sub["low"], sub["close"], sub["volume"]
        rng = (h - l).clip(lower=EPS)
        body = (c - o) / rng                       # + 阳线方向
        upper = (h - sub[["open", "close"]].max(axis=1)) / rng   # 上影占比
        lower = (sub[["open", "close"]].min(axis=1) - l) / rng   # 下影占比

        body_prev = body.groupby(level="asset").shift(1)
        bull_engulf = ((body > 0) & (body_prev < 0) & (body.abs() > body_prev.abs())).astype(float)
        bear_engulf = ((body < 0) & (body_prev > 0) & (body.abs() > body_prev.abs())).astype(float)

        kbi = body + 0.5 * (lower - upper) + bull_engulf - bear_engulf

        # 综合分：近 W_KBI 日滚动均值
        composite = kbi.groupby(level="asset").transform(
            lambda s: s.rolling(W_KBI, min_periods=5).mean())

        # 情绪系数：量能共振（近 5 日量 / 近 60 日量 − 1），tanh 压缩到 (−1,1)
        vol_s = g["volume"].transform(lambda s: s.rolling(W_VOL_S, min_periods=3).mean())
        vol_l = g["volume"].transform(lambda s: s.rolling(W_VOL_L, min_periods=20).mean())
        with np.errstate(divide="ignore", invalid="ignore"):
            vol_ratio = (vol_s / vol_l).fillna(1.0)
        emotion = np.tanh(vol_ratio - 1.0)

        factor = composite * emotion
        return factor


register_factor(KlinePatternCompositeFactor())
