"""长上影线因子（upper_shadow）。

对应灵感池 i20260820-042：当日出现长上影线（(最高−收盘)/(最高−最低) > 0.6，
且当日成交量 / 20 日均量偏高）的个股，后续有冲高回落 / 逢高派发压力——
技术面"上攻受阻"信号。A 股盘中冲高后被砸回常伴随主力派发或套牢盘抛压，截面含增量信息。

实现（纯 OHLC，逐资产截至 t 的当日线）：
    upper_shadow = (high - max(open, close)) / (high - low + eps)
值越大表示上影越长（盘中冲高后被砸回）。方向未知，由 RankIC 符号自动判定。
（与 f0028a 长下影线互为镜像，分别捕捉"上攻受阻"与"探底回升"两类形态。）

PIT 安全：compute 仅消费 panel 中 t 及之前的 open/high/low/close，逐日切片只含 ≤t 行；
不引用未来行、不引用 market_cap 快照列（市值暴露由 harness 用 pit_float_mcap 剥离）。
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from factors.interface import register_factor


@register_factor
class UpperShadowFactor:
    name = "upper_shadow"
    fcode = "f0036a"  # 交付包代号（对齐 deliverables/factors/_REGISTRY.csv）
    universe_hint = "hs300"

    def compute(self, panel: pd.DataFrame, as_of_date, ctx=None) -> pd.Series:
        t = pd.Timestamp(as_of_date)
        sub = panel.sort_index().copy()
        hi = sub["high"]
        base = sub[["open", "close"]].max(axis=1)  # 实体上沿
        us = (hi - base) / (hi - sub["low"] + 1e-9)
        return us.xs(t, level="date").dropna()


register_factor(UpperShadowFactor())
