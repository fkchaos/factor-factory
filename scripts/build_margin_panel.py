"""预建融资融券余额面板（Phase 2 资金面 · F1 数据源）。

数据源：AkShare `stock_margin_detail_sse(date=)` / `stock_margin_detail_szse(date=)`（免费已验证）。
逐交易日拉取全市场两融标的的「融资余额」，缓存为 (date×asset) 面板，供 f0097a 计算 5 日增幅。

注意：两融标的仅覆盖约 2000~3600 只（非全市场），未被覆盖的股票在面板中为 NaN（排名时被丢弃）。
逐日拉取量 ≈ 1500 交易日 × 2 端，较重；本脚本按日缓存（.cache/margin_raw/），可断点续跑。

用法：python scripts/build_margin_panel.py
窗口：2019-12-20 → 2026-10-10（早于回测起点，留足 5 日增幅窗）。
"""
from __future__ import annotations
import time
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import akshare as ak

ROOT = Path(".")
RAW = ROOT / ".cache" / "margin_raw"
RAW.mkdir(parents=True, exist_ok=True)
OUT = ROOT / "data" / "moneyflow_cache"
OUT.mkdir(parents=True, exist_ok=True)
START = "20191220"
END = "20261010"


def to_panel_code(code: str) -> str:
    c = str(code).strip()
    if c.startswith(("6", "9", "5")):       # 沪市 / 沪B / 沪市ETF
        return f"{c}.SH"
    if c.startswith(("0", "2", "3", "1")):  # 深市 / 深B / 创业板
        return f"{c}.SZ"
    if c.startswith(("4", "8")):            # 北交所
        return f"{c}.BJ"
    return c


def fetch_one(date: str):
    """拉取单日两融明细（沪深），返回 concat 后的 DataFrame 或 None。"""
    rows = []
    for fn, key in ((ak.stock_margin_detail_sse, "sse"), (ak.stock_margin_detail_szse, "szse")):
        try:
            df = fn(date=date)
        except Exception as ex:
            print(f"  [warn] {date} {key} 失败: {ex!r}", flush=True)
            continue
        if df is None or len(df) == 0:
            continue
        df = df.copy()
        df["_mkt"] = key
        rows.append(df)
    if not rows:
        return None
    return pd.concat(rows, ignore_index=True)


def main() -> None:
    cur = pd.Timestamp(START)
    end = pd.Timestamp(END)
    n_ok = n_skip = n_fail = 0
    while cur <= end:
        d = cur.strftime("%Y%m%d")
        fp_sse = RAW / f"{d}_sse.parquet"
        fp_szse = RAW / f"{d}_szse.parquet"
        if fp_sse.exists() and fp_szse.exists():
            n_skip += 1
        else:
            df = fetch_one(d)
            if df is not None and len(df):
                # 统一列：code / 融资余额
                if "标的证券代码" in df.columns:       # sse
                    sub = df[["标的证券代码", "融资余额"]].copy()
                    sub.columns = ["code", "rzye"]
                else:                                    # szse
                    sub = df[["证券代码", "融资余额"]].copy()
                    sub.columns = ["code", "rzye"]
                sub["code"] = sub["code"].map(to_panel_code)
                sub["rzye"] = pd.to_numeric(sub["rzye"], errors="coerce")
                sub = sub.dropna(subset=["code", "rzye"])
                sse_part = sub[sub["code"].str.endswith(".SH")]
                szse_part = sub[sub["code"].str.endswith(".SZ")]
                if len(sse_part):
                    sse_part.to_parquet(fp_sse)
                else:
                    fp_sse.write_text("")  # 占位，标记已查（空）
                if len(szse_part):
                    szse_part.to_parquet(fp_szse)
                else:
                    fp_szse.write_text("")
                n_ok += 1
            else:
                # 空日也写占位，避免重复拉取
                fp_sse.write_text("")
                fp_szse.write_text("")
                n_fail += 1
        cur = cur + pd.Timedelta(days=1)
        time.sleep(0.15)

    # ---- 汇总成 (date×asset) 面板 ----
    files = sorted(RAW.glob("*.parquet"))
    recs = []
    for fp in files:
        d = fp.name[:8]
        try:
            df = pd.read_parquet(fp)
        except Exception:
            continue
        if df is None or len(df) == 0:
            continue
        df = df.copy()
        df["date"] = pd.Timestamp(d)
        recs.append(df[["date", "code", "rzye"]])
    if not recs:
        print("❌ 无有效两融数据", flush=True)
        sys.exit(1)
    allrec = pd.concat(recs, ignore_index=True)
    panel = allrec.pivot_table(index="date", columns="code", values="rzye", aggfunc="last")
    panel = panel.sort_index()
    panel.to_parquet(OUT / "margin_balance_panel.parquet")
    print(f"✅ margin_balance_panel: {panel.shape} (日期×两融标的)", flush=True)
    print(f"拉取统计: ok={n_ok} skip={n_skip} empty={n_fail}", flush=True)


if __name__ == "__main__":
    main()
