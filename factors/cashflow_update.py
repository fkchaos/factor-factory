"""财报更新收益因子（cashflow_update）。

对应灵感池 i20260914-009：个股 最新可得财报相对上次使用财报的因子值变化(update return)
截面越高 → 未来 20 日收益越高（新披露信息相对上次的「更新」被部分定价，非单纯水平）。

实现（PIT 安全）：
    以经营现金流(ocf)为基底，取相邻披露期变化率：
        update_t = (ocf_cur − ocf_prev) / |ocf_prev|
        （prev = 上一已披露期，除零 / 缺失 → NaN，不构造假更新）
    因子值随披露日阶梯跳变（财报特性，非前视）。属纯比率变化，无市值口径问题。
    仅用 PIT 财报字段，绝不读面板 market_cap 快照列（今日市值回填全历史 = 假 PIT，
    会把未来收益注入残差）。

🔴 与 f0072a(netprofit_yoy)/f0071a(revenue_yoy) 正交性：本因子测量的是
「相邻披露期现金流的环比变化率」(update news)，而非同比(YoY)比率；基底选 ocf（现金流）
而非净利，与现有盈利同比因子口径不同，冗余风险较低，最终以全局矩阵 ρ 为准。
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from factors.interface import register_factor
from factors.fundamentals import FundamentalFactorBase, _gv
from data.pit_fundamentals import default_store


class CashflowUpdateFactor(FundamentalFactorBase):
    name = "cashflow_update"
    fcode = "f0086a"
    pit_fields = ["ocf"]

    def compute_panel(self, panel, ctx=None) -> pd.DataFrame:
        """事件驱动算出 date × asset 阶梯面板；value = 相邻披露期 ocf 环比变化率。"""
        dates = pd.DatetimeIndex(sorted(panel.index.get_level_values("date").unique()))
        assets = list(dict.fromkeys(panel.index.get_level_values("asset").tolist()))
        svc = (ctx or {}).get("pit_service") or default_store(assets, self.pit_fields)
        cols = {}
        for a in assets:
            pubs = svc.disclosure_dates(a)
            if len(pubs) == 0:
                continue
            pubs = pubs[(pubs >= dates[0]) & (pubs <= dates[-1])]
            if len(pubs) == 0:
                continue
            prev = None
            vals, idx = [], []
            for pub in pubs:
                snap = svc.snapshot([a], pub, with_dates=True)
                v = _gv(snap, a, "ocf")
                if pd.notna(v):
                    if prev is not None and pd.notna(prev) and prev != 0:
                        vals.append(float((v - prev) / abs(prev)))
                        idx.append(pub)
                    prev = v
            if not vals:
                continue
            ser = pd.Series(vals, index=pd.DatetimeIndex(idx))
            # 披露当日即生效（PIT 快照口径 pubDate <= as_of），之后 ffill 到每个交易日
            cols[a] = ser.reindex(dates.union(ser.index)).ffill().reindex(dates)
        return pd.DataFrame(cols, index=dates) if cols else pd.DataFrame(index=dates)


register_factor(CashflowUpdateFactor())
