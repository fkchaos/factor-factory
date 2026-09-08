"""日内博弈激烈度因子（intraday_battle_intensity）· f0056a。

对应灵感池 i20260903-005（sell_side，此前已翻 in_pipeline，本轮补齐实现）：
个股近 20 个交易日 `(最高价−最低价) / max(|收盘价−开盘价|, tick下限)` 的均值
（日内多空博弈激烈度）越高 → 未来 20 个交易日收益越**低**。

机制（方正金工「多空博弈」因子的纯日频降级）
--------------------------------------------
一根 K 线的**振幅**(H−L) 代表当日多空来回争夺的空间，**实体**|C−O| 代表最终净胜出
幅度。两者比值高 = 拉锯剧烈但无人胜出 = 分歧未决且交易摩擦已被消耗掉。原文用分钟频
刻画，本条只取 OHLC 四价（baostock 前复权口径直接可得，零数据缺口）。

实现（纯 OHLC，向后看，W=20）
------------------------------
    ratio_t = (high_t − low_t) / max(|close_t − open_t|, FLOOR_PCT × close_t)
    factor  = ratio 的近 20 日滚动均值（每资产各自 rolling）

⚠️ 分母下限（原假设落地要点①）
    一字板 / 开收盘同价样本会让 |C−O| → 0，比值爆炸并污染极值端。分母取
    `max(|C−O|, 0.001×close)`（千分之一价位，约等于 A 股主板一个 tick 的量级），
    使一字板样本落在有限的高位而非 +inf。这个下限是**构造性防护**、不是拟合参数：
    它只影响"实体≈0"的病态样本，对正常样本恒不生效（|C−O| 通常 ≫ 0.1% × C）。

符号约定
--------
按本工厂惯例交付**原始量**（与 f0002a ivol / f0036a 长上影线同）：因子值越大 =
博弈越激烈。假设方向为**负相关**，由 harness 的 RankIC 符号如实体现，不在因子内翻转
（翻符号 = 看过结果再定方向 = 数据窥探）。

冗余提示
--------
与 f0036a（长上影线，单日形态）、f0028a（长下影线）刻画的都是 K 线形状，但本因子是
**20 日振幅/实体比的均值**（连续、多日平滑、不区分上下方向），出包后须看 correlation.csv；
若与 f0036a/f0028a 相关 >0.8 应合并降级。

PIT 安全：仅用 open/high/low/close；不读 market_cap 快照列（市值暴露由 harness
用 pit_float_mcap 中性化剥离）。compute_panel 一次性向量化全序列。
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from factors.interface import register_factor

W = 20            # 滚动窗口（交易日）
FLOOR_PCT = 0.001  # 分母下限 = FLOOR_PCT × close，防一字板除零


class IntradayBattleIntensityFactor:
    """日内博弈激烈度：近 20 日 (振幅 / 实体) 均值。"""

    name = "intraday_battle_intensity"
    fcode = "f0056a"
    universe_hint = None

    def _full(self, panel: pd.DataFrame) -> pd.Series:
        sub = panel.sort_index()
        amp = sub["high"] - sub["low"]                       # 振幅
        body = (sub["close"] - sub["open"]).abs()            # 实体
        floor = FLOOR_PCT * sub["close"].abs()
        denom = np.maximum(body, floor)
        with np.errstate(divide="ignore", invalid="ignore"):
            ratio = amp / denom
        ratio = ratio.replace([np.inf, -np.inf], np.nan)

        M = ratio.unstack(level="asset")                     # T x A
        out = M.rolling(W, min_periods=max(5, W // 2)).mean()
        return out.stack().reindex(ratio.index)

    def compute(self, panel: pd.DataFrame, as_of_date, ctx=None) -> pd.Series:
        t = pd.Timestamp(as_of_date)
        return self._full(panel).xs(t, level="date").dropna().rename(self.name)

    def compute_panel(self, panel: pd.DataFrame) -> pd.DataFrame:
        return self._full(panel).unstack(level="asset")


register_factor(IntradayBattleIntensityFactor())
