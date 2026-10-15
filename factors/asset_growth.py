"""总资产同比增长因子（asset_growth, f0100a）。

对应灵感 i20261015-002（Asset Growth anomaly 非线性）：总资产同比增长（急剧扩张或
急剧收缩）公司 mis-pricing 更严重，呈 U 形/倒U 形关系。本因子提供连续的"总资产
同比(相邻同年季度披露期)"增长率，U/倒U 形态由下游 IC 分析自然呈现。

实现（PIT 安全）：
    - 仅用 PIT 财报字段 total_assets（资产负债表，东财/AkShare 多后端，已缓存）
    - 逐资产取全部披露日快照的 total_assets → 同比 = ta_t / ta_{t-4} - 1（t-4 = 上年同季）
    - 增长值自披露日(pubDate)起生效（pubDate<=as_of），之后 ffill 到每个交易日
    - 绝不读面板 market_cap 快照列（今日市值回填全历史 = 假 PIT）

与 f0068a(accrual 应计) 区别：本因子是"资产规模变化率"(CMA/投资异象)，f0068a 是
"应计项目水平"，二者底层字段与逻辑均不同，非同源。
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from factors.interface import register_factor
from factors.fundamentals import _gv
from data.pit_fundamentals import default_store


class AssetGrowthFactor:
    name = "asset_growth"
    fcode = "f0100a"
    universe_hint = "hs300"
    pit_fields = ["total_assets"]

    def compute_panel(self, panel, ctx=None) -> pd.DataFrame:
        dates = pd.DatetimeIndex(sorted(panel.index.get_level_values("date").unique()))
        assets = list(dict.fromkeys(panel.index.get_level_values("asset")))
        svc = default_store(assets, self.pit_fields)
        cols = {}
        for a in assets:
            pubs = svc.disclosure_dates(a)
            if len(pubs) == 0:
                continue
            pubs = pubs[(pubs >= dates[0]) & (pubs <= dates[-1])]
            if len(pubs) == 0:
                continue
            tas, idx = [], []
            for pub in pubs:
                snap = svc.snapshot([a], pub, with_dates=True)
                ta = _gv(snap, a, "total_assets")
                if pd.notna(ta) and ta > 0:
                    tas.append(float(ta))
                    idx.append(pub)
            if len(tas) < 5:  # 需 >=5 个披露期才能算同比(t vs t-4)
                continue
            s = pd.Series(tas, index=pd.DatetimeIndex(idx)).sort_index()
            yoy = s / s.shift(4) - 1.0  # t vs 上年同季（t-4）
            yoy = yoy.dropna()
            if len(yoy) == 0:
                continue
            cols[a] = yoy.reindex(dates.union(yoy.index)).ffill().reindex(dates)
        return pd.DataFrame(cols, index=dates) if cols else pd.DataFrame(index=dates)

    def compute(self, panel, as_of_date, ctx=None) -> pd.Series:
        full = self.compute_panel(panel, ctx)
        t = pd.Timestamp(as_of_date)
        if t in full.index:
            return full.loc[t].dropna().rename(self.name)
        return pd.Series(dtype=float, name=self.name)


register_factor(AssetGrowthFactor())
