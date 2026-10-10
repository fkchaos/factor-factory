"""融资余额 5 日增幅因子（margin_balance_5d, f0097a）。

对应灵感池 i20260806-012（融资余额 5 日增幅→低收益，杠杆资金激进追涨后回吐）。
信号：个股融资余额近 5 交易日增幅 = (rzye[t] - rzye[t-5]) / rzye[t-5]。
机制：融资余额短期快速拉升 = 杠杆资金激进追高，后续往往回吐（杠杆周期逻辑），截面预期 RankIC<0（反向）。
PIT 安全：融资余额于每日收盘后由交易所披露；compute 只用 t 及之前数据（预建面板已含此约束），
框架 exec_lag=1 再负责交易滞后期。未被纳入两融标的的股票信号恒 NaN（排名时被丢弃）。
数据：scripts/build_margin_panel.py 预建 data/moneyflow_cache/margin_balance_panel.parquet（date×asset 融资余额）。
"""
from __future__ import annotations

import pandas as pd
from pathlib import Path

from factors.interface import register_factor

CACHE = Path("data/moneyflow_cache/margin_balance_panel.parquet")
_CACHE: dict = {}


@register_factor
class MarginBalance5dFactor:
    name = "margin_balance_5d"
    fcode = "f0097a"
    universe_hint = "hs300"

    @classmethod
    def _load(cls) -> pd.DataFrame:
        if "margin" not in _CACHE:
            _CACHE["margin"] = pd.read_parquet(CACHE)
        return _CACHE["margin"]

    def compute_panel(self, panel: pd.DataFrame) -> pd.DataFrame:
        mbal = self._load()
        dates = sorted(panel.index.get_level_values("date").unique())
        assets = panel.index.get_level_values("asset").unique()
        sub = mbal.reindex(index=dates, columns=assets)
        # 近 5 交易日融资余额增幅（截面 z-score 由框架管线统一做）
        return sub.pct_change(5)

    def compute(self, panel: pd.DataFrame, as_of_date, ctx=None) -> pd.Series:
        # 复用 compute_panel 逻辑，保证与前视审计（全量 vs 切片面板）输出一致；
        # compute 不读 panel 内容，仅取 (date, asset) 索引，天然无前视。
        grid = self.compute_panel(panel)
        t = pd.Timestamp(as_of_date)
        if t in grid.index:
            return grid.loc[t].dropna()
        return pd.Series(dtype=float)


register_factor(MarginBalance5dFactor())
