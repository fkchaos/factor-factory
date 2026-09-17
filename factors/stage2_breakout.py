"""第二阶段突破强度（stage2_breakout）· f0087a。

对应灵感池 i20260917-011：个股 250 日 RPS 相对强度（前 10%）+ 站上 200 日均线
+ 月线反转底部启动信号 → 未来 20 日收益越高（Minervini SEPA「第二阶段突破」：
趋势动量 + 基底突破，属经典趋势/动量类异象，与单纯 12-1 动量互补在「强度 + 位置」维度）。

实现（纯 close，向后看，无前视；全部统计量仅用 t 日及之前数据）：
- rps250    ：个股 250 交易日收益 close/close[-250]-1 的**截面百分位排名**（0-1，越高越强）
- dist_ma200：close 相对 200 日均线的偏离 (close-SMA200)/SMA200
- dist_52wlow：close 相对近 252 日最低点的偏离 (close-low252)/low252（捕捉「脱离 52 周底部」，
   Minervini 第二阶段要求价格较 52 周低点抬升 ≥20%，即 dist_52wlow≥0.2）
- ma200_slope：200 日均线 20 日变化率 SMA200_t/SMA200_{t-20}-1（捕捉「均线抬头」）
四个分量各自做**截面 z-score**（等权，避免量纲碾压）后取均值 → 连续因子值；
方向已对齐「因子值越大 → 未来收益越高」。

口径红线：仅用 close；不读面板 market_cap 快照列（市值暴露由 harness 用 pit_float_mcap 剥离）。
compute_panel 一次性矩阵化（O(N)），与 f0058a/f0083a 同快路径。
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from factors.interface import register_factor

WIN = 250          # RPS / 52 周窗口（交易日）
MA = 200           # 长期均线
SLOPE_LAG = 20     # 均线抬头观察窗


def _zscore_cs(df: pd.DataFrame) -> pd.DataFrame:
    """逐交易日（行）截面 z-score。"""
    sd = df.std(axis=1)
    sd = sd.replace(0, np.nan)
    return (df.sub(df.mean(axis=1), axis=0)).div(sd, axis=0)


class Stage2BreakoutFactor:
    """第二阶段突破强度（趋势 + 基底突破复合）。"""

    name = "stage2_breakout"
    fcode = "f0087a"
    universe_hint = None

    def _full(self, panel: pd.DataFrame) -> pd.Series:
        sub = panel.sort_index()
        close = sub["close"].unstack(level="asset")           # T x A

        ret250 = close / close.shift(WIN) - 1.0
        rps = ret250.rank(pct=True, axis=1)                   # 截面百分位 0-1

        ma200 = close.rolling(MA, min_periods=MA // 2).mean()
        dist_ma = (close - ma200) / ma200

        low252 = close.rolling(WIN, min_periods=WIN // 2).min()
        dist_low = (close - low252) / low252

        ma_slope = ma200 / ma200.shift(SLOPE_LAG) - 1.0

        comp = _zscore_cs(rps.fillna(0.0)) \
            + _zscore_cs(dist_ma) \
            + _zscore_cs(dist_low) \
            + _zscore_cs(ma_slope)
        raw = (comp / 4.0).stack().reindex(sub["close"].index)
        return raw

    def compute(self, panel: pd.DataFrame, as_of_date, ctx=None) -> pd.Series:
        t = pd.Timestamp(as_of_date)
        return self._full(panel).xs(t, level="date").dropna().rename(self.name)

    def compute_panel(self, panel: pd.DataFrame) -> pd.DataFrame:
        return self._full(panel).unstack(level="asset")


register_factor(Stage2BreakoutFactor())
