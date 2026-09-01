"""量能扩张速度因子（volume_expansion_speed）。

逻辑（对应灵感池 i20260806-007）：量能「速度」比量能「水平」更具选股增量，
用近 20 日均量 ÷ 近 120 日均量刻画量能扩张/萎缩的相对速度：
    v20 = 资产截至 t 的 20 日成交量均值
    v120 = 资产截至 t 的 120 日成交量均值
    factor = v20 / v120
值 > 1 表示量能处于扩张段（近期成交显著放量），< 1 表示萎缩段。

读数为截面排序型量价特征，与 f0001a(隔夜-日内分解)/f0002a(特质波动率)/
f0004a(锚定成本偏离) 正交。属高频量价家族，信息源独立于财报/估值。

PIT 安全：compute 仅用 as_of_date 及之前数据；滚动窗口在分组 cumsum/rolling
内递推，不引用未来行；纯函数（无实例状态），满足 assert_no_lookahead 一致性。
"""
from __future__ import annotations

import pandas as pd
import numpy as np

from factors.interface import register_factor


@register_factor
class VolumeExpansionSpeedFactor:
    name = "volume_expansion_speed"
    fcode = "f0026a"
    universe_hint = "hs300"

    def compute(self, panel: pd.DataFrame, as_of_date, ctx=None) -> pd.Series:
        t = pd.Timestamp(as_of_date)
        sub = panel.sort_index()
        g = sub.groupby(level="asset")["volume"]
        v20 = g.transform(lambda s: s.rolling(20, min_periods=20).mean())
        v120 = g.transform(lambda s: s.rolling(120, min_periods=120).mean())
        speed = (v20 / v120.replace(0, np.nan)).xs(t, level="date")
        return speed.dropna()


register_factor(VolumeExpansionSpeedFactor())
