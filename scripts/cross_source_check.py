"""跨数据源一致性核对：主源 vs AkShare 基准。

目的：验证数据契约（单位/格式）在真实源间生效——同票同日的 close/volume/amount 应一致。
复权口径：tushare(免费档)=raw，akshare/baostock=qfq。同口径（akshare vs baostock）close
也应 <1%；跨口径（tushare vs akshare）close 在除权除息日附近有差（预期内，容忍放宽）。

用法：
    python scripts/cross_source_check.py [--codes 000001.SZ,600519.SH] [--start 2024-01-01]
                                        [--end 2024-12-31] [--source tushare|baostock]

    --source tushare（默认）：Tushare(raw) vs AkShare(qfq)
    --source baostock：      BaoStock(qfq) vs AkShare(qfq)，免积分；首次拉取较慢（建缓存）

退出码：0=全部通过；1=存在超差（打印明细）。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

FIELDS = ["close", "volume", "amount", "turnover"]


def _tushare_token() -> str:
    tok = [l.split(":", 1)[1].strip()
           for l in open(ROOT / "configs" / "tushare.yaml", encoding="utf-8")
           if l.startswith("token:")]
    if not tok:
        raise RuntimeError("configs/tushare.yaml 未配置 token（或改用 --source baostock）")
    return tok[0]


def compare(pa, pb, name_a: str, name_b: str, codes: list[str], args,
            close_tol: float, note: str) -> bool:
    ok = True
    print(f"核对区间 {args.start} ~ {args.end}；{note}")
    for code in codes:
        panel_a = pa.get_panel(FIELDS, args.start, args.end)
        panel_b = pb.get_panel(FIELDS, args.start, args.end)
        ca = panel_a.xs(code, level="asset") if code in panel_a.index.get_level_values("asset") else pd.DataFrame()
        cb = panel_b.xs(code, level="asset") if code in panel_b.index.get_level_values("asset") else pd.DataFrame()
        if ca.empty or cb.empty:
            print(f"[skip] {code}: 单源无数据 ({name_a} {len(ca)} 行 / {name_b} {len(cb)} 行)")
            continue
        j = ca.join(cb, how="inner", lsuffix="_a", rsuffix="_b")
        if j.empty:
            print(f"[skip] {code}: 无共同交易日")
            continue
        for f in ("close", "volume", "amount"):
            a, b = j[f"{f}_a"], j[f"{f}_b"]
            rel = (b - a).abs() / a.replace(0, pd.NA)
            max_rel = rel.max()
            tol = close_tol if f == "close" else 0.01  # volume/amount 单位一致须 <1%
            status = "OK" if max_rel <= tol else "MISMATCH"
            if status == "MISMATCH":
                ok = False
            print(f"[{status}] {code} {f}: 共同样本 {len(j)} 日, 最大相对差 {max_rel:.2%}"
                  + (f" (日期 {rel.idxmax()})" if len(j) else ""))
        print(f"[info] {code} turnover 非空: {name_a} {ca['turnover'].notna().mean():.0%} / "
              f"{name_b} {cb['turnover'].notna().mean():.0%}")
    print("=" * 50)
    print("结论:", "✅ 跨源一致（契约生效）" if ok else "❌ 存在超差，请检查单位换算")
    return ok


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--codes", default="000001.SZ,000002.SZ,300750.SZ")
    ap.add_argument("--start", default="2024-01-01")
    ap.add_argument("--end", default="2024-12-31")
    ap.add_argument("--source", choices=["tushare", "baostock"], default="tushare",
                    help="主对照源（与 AkShare 基准对比）")
    args = ap.parse_args()
    codes = [c.strip() for c in args.codes.split(",")]

    from data.providers import TushareProvider, AkShareProvider, BaoStockProvider

    if args.source == "baostock":
        pa = BaoStockProvider(universe="hs300")   # 覆盖 --codes；首次全池拉取较慢
        pb = AkShareProvider()
        ok = compare(pa, pb, "baostock", "akshare", codes, args,
                     close_tol=0.01, note="复权口径：baostock=qfq / akshare=qfq（同口径）")
    else:
        pa = TushareProvider(token=_tushare_token(), universe="SZ", calls_per_min=200)
        pb = AkShareProvider()
        # 跨口径方向性诊断：显式放行复权不一致（raw vs qfq），但要求产物标注口径差异
        from data.contract import assert_adj_policy
        assert_adj_policy(pa.adj_policy, allow_mismatch=True)
        ok = compare(pa, pb, "tushare", "akshare", codes, args,
                     close_tol=0.05, note="复权口径：tushare=raw / akshare=qfq（跨口径，close 容忍放宽）")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
