"""龙虎榜上榜关注度因子（lhb_attention, f0096a）。

对应灵感池 i20260806-011（龙虎榜上榜后超额）：以「近 20 日历日上榜天数」作游资关注度代理。
机制：短期内频繁登上龙虎榜 = 资金/游资高度关注，往往伴随动量或情绪极致，截面可分。
PIT 安全：同上（预建面板只用 t 及之前事件）；未被龙虎榜覆盖的股票信号恒 0。
数据：scripts/build_lhb_signals.py 预建 data/moneyflow_cache/lhb_attention_20d.parquet（date×asset）。
"""
from __future__ import annotations

import pandas as pd
from pathlib import Path

from factors.interface import register_factor

CACHE = Path("data/moneyflow_cache/lhb_attention_20d.parquet")
_CACHE: dict = {}


@register_factor
class LhbAttentionFactor:
    name = "lhb_attention"
    fcode = "f0096a"
    universe_hint = "hs300"

    @classmethod
    def _load(cls) -> pd.DataFrame:
        if "attention" not in _CACHE:
            _CACHE["attention"] = pd.read_parquet(CACHE)
        return _CACHE["attention"]

    def compute_panel(self, panel: pd.DataFrame) -> pd.DataFrame:
        sig = self._load()
        dates = sorted(panel.index.get_level_values("date").unique())
        assets = panel.index.get_level_values("asset").unique()
        return sig.reindex(index=dates, columns=assets)

    def compute(self, panel: pd.DataFrame, as_of_date, ctx=None) -> pd.Series:
        sig = self._load()
        t = pd.Timestamp(as_of_date)
        row = sig.loc[t] if t in sig.index else pd.Series(dtype=float, index=sig.columns)
        return row.reindex(panel.index.get_level_values("asset").unique()).dropna()


register_factor(LhbAttentionFactor())
