"""理想振幅因子（ideal_amplitude, f0098a）。

对应灵感 i20261015-008（开源金工《交易行为因子》）：按股价维度切割后的结构化振幅，
高振幅蕴含噪音/投机，方向与波动率家族一致（高→未来收益低，反向）。

实现（纯 OHLCV，逐资产截至 t）：
    amp_d = (high - low) / prev_close          # 日振幅（前收归一）
    amp   = rolling W=20 日均值                  # 结构化振幅（近 20 日平均振幅）
    PIT 安全：仅用 OHLCV（t 日及之前可观测量）；不引用 market_cap 快照列。
    市值暴露由 harness 用 pit_float_mcap 中性化剥离。

口径：理想振幅的"价态切割"由 harness 市值中性化近似覆盖（高价股 % 振幅天然偏低，
已被市值中性化吸收）；因子值本身为纯振幅水平，取自 high-low 区间而非收益率，属
区间振幅代理，与 idio_vol/特质波动率(收益波动)正交度交由冗余前置闸门核验。
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from factors.interface import register_factor

W = 20


@register_factor
class IdealAmplitudeFactor:
    name = "ideal_amplitude"
    fcode = "f0098a"
    universe_hint = None

    def compute_panel(self, panel, ctx=None) -> pd.DataFrame:
        asset = panel.index.get_level_values("asset")
        close = panel["close"].astype(float)
        high = panel["high"].astype(float)
        low = panel["low"].astype(float)
        prev_close = close.groupby(asset).shift(1)
        amp = (high - low) / prev_close.replace(0, np.nan)
        amp = amp.groupby(asset).transform(lambda s: s.rolling(W).mean())
        mat = amp.unstack("asset")
        if mat.index.name != "date":
            mat = mat.T
        return mat

    def compute(self, panel, as_of_date, ctx=None) -> pd.Series:
        full = self.compute_panel(panel, ctx)
        t = pd.Timestamp(as_of_date)
        if t in full.index:
            return full.loc[t].dropna().rename(self.name)
        return pd.Series(dtype=float, name=self.name)


register_factor(IdealAmplitudeFactor())
