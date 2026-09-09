"""Phase 1 业绩预告因子（f0073a–f0075a，2026-09-09）。

数据源：AkShare 东财业绩预告，经 PitForecastService 按**公告日**对齐（无前视）。
因子清单：
  f0073a forecast_yoy   预告净利同比变动 = 东财「业绩变动幅度」（%）
  f0074a forecast_kind  预告类型分档     = KIND_SCORE（预增+3 … 预减-3，见 pit_forecast）
  f0075a forecast_ep    前瞻 EP         = 年化预告归母净利 / PIT 流通市值

🔴 必读约束（实测，见 data/pit_forecast.py docstring）：
- **覆盖率仅 28~36%**：hs300 内每报告期只有约 1/3 公司发预告 → 截面稀疏是**数据事实**，
  不是取数 bug，不得用全池前填/均值填充粉饰。
- **无修正历史**：同一 (股票, 报告期) 恒为 1 条 → 预告修正动量类因子在本源不可实现。
- 预告值为年初至报告期末**累计**口径，前瞻 EP 的分子已按报告期月份年化。

PIT 安全：严格 pubDate <= as_of；因子值在公告日跳变后阶梯沿用（与财报因子同语义）。
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from factors.interface import register_factor, slice_panel_to_date
from data.pit_forecast import default_service
from factors.fundamentals import _mcap_grid


class ForecastFactorBase:
    """预告因子基类：统一取 PIT 公告快照 / 事件驱动阶梯面板。"""

    universe_hint = "hs300"
    field = "yoy"  # 子类覆盖：yoy / kind_score / fc_np_ann

    # ---------- 逐日慢路径（单测 & 独立调用）----------
    def compute(self, panel: pd.DataFrame, as_of_date, ctx=None) -> pd.Series:
        t = pd.Timestamp(as_of_date)
        sub = slice_panel_to_date(panel, t)
        assets = sub.index.get_level_values("asset").unique().tolist()
        svc = (ctx or {}).get("forecast_service") or default_service()
        snap = svc.snapshot(assets, t)
        vals = {a: snap.get(a, {}).get(self.field, np.nan) for a in assets}
        s = pd.Series(vals, dtype=float)
        return s[pd.notna(s)]

    # ---------- 事件驱动快路径（build_deliverable.compute_factor_series 契约）----------
    # 预告在公告日跳变、之后恒定 → 按公告日算一次再阶梯 ffill，O(披露次数)。
    def compute_panel(self, panel: pd.DataFrame, ctx=None) -> pd.DataFrame:
        dates = pd.DatetimeIndex(sorted(panel.index.get_level_values("date").unique()))
        assets = list(dict.fromkeys(panel.index.get_level_values("asset")))
        svc = (ctx or {}).get("forecast_service") or default_service()
        return svc.stepped(dates, assets, self.field)


class ForecastYoyFactor(ForecastFactorBase):
    name = "forecast_yoy"
    fcode = "f0073a"
    field = "yoy"


class ForecastKindFactor(ForecastFactorBase):
    name = "forecast_kind"
    fcode = "f0074a"
    field = "kind_score"


class ForecastEPFactor(ForecastFactorBase):
    """前瞻 EP：分子（年化预告净利）阶梯、分母（市值）逐日。

    🔴 分母必须与 pit_float_mcap 同口径（PIT 红线）：见 fundamentals._mcap_grid。
    """

    name = "forecast_ep"
    fcode = "f0075a"
    field = "fc_np_ann"

    def compute(self, panel, as_of_date, ctx=None) -> pd.Series:
        from data.pit import pit_float_mcap

        t = pd.Timestamp(as_of_date)
        sub = slice_panel_to_date(panel, t)
        assets = sub.index.get_level_values("asset").unique().tolist()
        svc = (ctx or {}).get("forecast_service") or default_service()
        snap = svc.snapshot(assets, t)
        mcap = pit_float_mcap(sub, t)
        if mcap is None or len(mcap) == 0:
            return pd.Series(dtype=float)
        out = {}
        for a in assets:
            v = snap.get(a, {}).get("fc_np_ann", np.nan)
            m = mcap.get(a)
            if pd.notna(v) and pd.notna(m) and m > 0:
                out[a] = v / m
        s = pd.Series(out, dtype=float)
        return s[pd.notna(s)]

    def compute_panel(self, panel, ctx=None) -> pd.DataFrame:
        num = super().compute_panel(panel, ctx)
        den = _mcap_grid(panel).reindex(index=num.index, columns=num.columns)
        if den.empty:
            return pd.DataFrame(index=num.index)
        return num / den.where(den > 0)


for _f in (ForecastYoyFactor(), ForecastKindFactor(), ForecastEPFactor()):
    register_factor(_f)
