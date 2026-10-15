"""验证「快路径 compute_panel」与「慢路径 compute」算出的 IC 是否等价。

背景（2026-10-15）：
  池子矩阵（factor_universe_matrix.py → validate_factor）此前只走逐日慢路径，
  而出包脚本（build_deliverable.py::compute_factor_series）走 compute_panel 快路径。
  两者理论上等价，但当 fields 不一致时会各自走不同的降级分支 → 数字对不上
  （2026-10-13 的 turnover 事故正是如此）。

本脚本对同一 (因子, 池子) 分别用两条路径算出 rank_ic / icir / 胜率，
逐项比对。若差异在浮点噪声量级（<1e-9），即可放心把验证器切成快路径。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("FF_PROVIDER", "baostock")

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import factors  # noqa: F401,E402  触发全量注册
from data.providers import BaoStockProvider  # noqa: E402
from engine.interface import BacktestConfig, prepare_panel_for_factor  # noqa: E402
from factors.interface import get_factor  # noqa: E402
from validate.validator import (  # noqa: E402
    DEFAULT_FIELDS,
    _neutralize_cross_section,
    _rank_ic,
    winsorize_mad,
    zscore_cross_section,
)

POOLS = {
    "sz50": {},
    "hs300": {},
    "zz500": {},
    "hs800": {},
    "zz1000": {},
    "hs1800": {},
    "ALL": {"min_mcap": 50e8},
}


def run(factor_name: str, pool: str, mode: str):
    """mode: 'fast' = compute_panel 一次性算全序列; 'slow' = 逐日 compute。"""
    prov = BaoStockProvider(universe=pool, history_start="2020-01-01", **POOLS[pool])
    panel = prov.get_panel(DEFAULT_FIELDS, None, None)
    dates = sorted(panel.index.get_level_values("date").unique())
    N = len(dates)

    f = get_factor(factor_name)
    bulk = getattr(f, "compute_panel", None)
    full = bulk(panel) if (mode == "fast" and bulk is not None) else None
    if mode == "fast" and full is None:
        return None

    cfg = BacktestConfig(train_days=252)
    fs: dict = {}
    fr: dict = {}
    for idx, t in enumerate(dates):
        ctx = {"start": str(dates[max(0, idx - cfg.train_days)])}
        if full is not None:
            try:
                fv = full.loc[t].dropna()
            except KeyError:
                fv = pd.Series(dtype=float)
        else:
            sub = prepare_panel_for_factor(prov, f, t, DEFAULT_FIELDS, ctx)
            fv = f.compute(sub, t, ctx).dropna()
        fv = winsorize_mad(fv)
        fv = _neutralize_cross_section(fv, panel, t, prov)
        fv = zscore_cross_section(fv)
        fs[t] = fv

        close_t = panel.xs(t, level="date")["close"]
        if idx + 1 < N:
            close_t1 = panel.xs(dates[idx + 1], level="date")["close"]
            fr[t] = close_t1 / close_t - 1.0

    ics = []
    for t in fs:
        if t in fr:
            ic = _rank_ic(fs[t], fr[t])
            if np.isfinite(ic):
                ics.append(ic)
    s = pd.Series(ics)
    return float(s.mean()), float(s.mean() / s.std()) if s.std() > 0 else np.nan, float((s > 0).mean()), int(len(s))


def main() -> None:
    cases = sys.argv[1:] or ["reversal_60d:sz50"]
    print(f"DEFAULT_FIELDS = {DEFAULT_FIELDS}")
    print(f"{'因子':26s} {'路径':4s} {'rank_ic':>11s} {'icir':>9s} {'胜率':>7s} {'天数':>6s}  耗时s")
    for c in cases:
        fn, pool = c.split(":")
        import time
        t0 = time.time()
        fast = run(fn, pool, "fast")
        t_fast = time.time() - t0
        t1 = time.time()
        slow = run(fn, pool, "slow")
        t_slow = time.time() - t1
        if fast is None:
            print(f"{fn:26s} {'fast':4s}  (该因子无 compute_panel，跳过)")
            continue
        for lbl, r, el in (("fast", fast, t_fast), ("slow", slow, t_slow)):
            print(f"{fn + '@' + pool:26s} {lbl:4s} {r[0]:11.6f} {r[1]:9.4f} {r[2]:7.4f} {r[3]:6d}  {el:7.1f}")
        d_ic = abs(fast[0] - slow[0])
        d_ir = abs(fast[1] - slow[1])
        ok = d_ic < 1e-9 and d_ir < 1e-9
        print(f"  → |ΔIC|={d_ic:.3e}  |ΔICIR|={d_ir:.3e}   {'等价 ✓' if ok else '⚠ 不一致'}")


if __name__ == "__main__":
    main()
