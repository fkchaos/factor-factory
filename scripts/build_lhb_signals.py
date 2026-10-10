"""预建龙虎榜（LHB）资金面信号面板（Phase 2 资金面 · F2/F3 数据源）。

数据源：AkShare `stock_lhb_detail_em`（东财龙虎榜每日明细，免费已验证）。
取 上榜日 / 代码 / 龙虎榜净买额 / 流通市值，映射成面板 asset 代码（600000.SH 等），
产出两张 (date×asset) 缓存面板：
  - lhb_netbuy_20d.parquet   : 近 20 日历日「上榜日 净买额/流通市值」之和（连续型净买入强度）
  - lhb_attention_20d.parquet: 近 20 日历日上榜天数（游资关注度代理）

PIT 安全：龙虎榜于上榜日收盘后披露，信号只用 t 及之前事件；交易滞后期由框架 exec_lag 负责。
非上榜日净买额记 0 → rolling 自然衰减；未被龙虎榜覆盖的股票信号恒 0（排名时被丢弃）。

用法：python scripts/build_lhb_signals.py
窗口：2019-01-01 → 2026-10-10（早于回测起点，留足 20 日滚动窗）。
"""
from __future__ import annotations
import time
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import akshare as ak

OUT = Path("data/moneyflow_cache")
OUT.mkdir(parents=True, exist_ok=True)
START = "20190101"
END = "20261010"
WIN = 20


def to_panel_code(code: str) -> str:
    """龙虎榜纯数字代码 -> 面板 asset 代码（带交易所后缀）。"""
    c = str(code).strip()
    if c.startswith(("6", "9")):      # 沪市 / 沪B
        return f"{c}.SH"
    if c.startswith(("0", "2", "3")):  # 深市 / 深B / 创业板
        return f"{c}.SZ"
    if c.startswith(("4", "8")):       # 北交所
        return f"{c}.BJ"
    return c


def main() -> None:
    frames = []
    cur = pd.Timestamp(START)
    end = pd.Timestamp(END)
    n_fail = 0
    while cur <= end:
        nxt = cur + pd.offsets.QuarterEnd(1)
        s = cur.strftime("%Y%m%d")
        e = min(nxt, end).strftime("%Y%m%d")
        try:
            df = ak.stock_lhb_detail_em(start_date=s, end_date=e)
        except Exception as ex:
            print(f"  [warn] {s}~{e} 拉取失败: {ex!r}", flush=True)
            n_fail += 1
            cur = nxt + pd.Timedelta(days=1)
            continue
        if df is not None and len(df):
            frames.append(df)
        cur = nxt + pd.Timedelta(days=1)
        time.sleep(0.4)

    if not frames:
        print("❌ 未取到任何龙虎榜数据", flush=True)
        sys.exit(1)

    raw = pd.concat(frames, ignore_index=True)
    print(f"原始明细行数={len(raw)}  列={list(raw.columns)[:8]}...", flush=True)

    raw["asset"] = raw["代码"].map(to_panel_code)
    raw["date"] = pd.to_datetime(raw["上榜日"], errors="coerce")
    raw["net"] = pd.to_numeric(raw["龙虎榜净买额"], errors="coerce")
    raw["mcap"] = pd.to_numeric(raw["流通市值"], errors="coerce")
    raw = raw.dropna(subset=["asset", "date", "net", "mcap"])
    raw["intensity"] = raw["net"] / raw["mcap"].replace(0, np.nan)

    events = raw[["date", "asset", "intensity"]].dropna(subset=["intensity"])
    alldates = pd.date_range(events["date"].min(), events["date"].max(), freq="D")
    assets = sorted(events["asset"].unique())

    # 事件日强度（同日多上榜合并为 sum），铺到日历网格，非事件日填 0
    piv = (events.pivot_table(index="date", columns="asset",
                              values="intensity", aggfunc="sum")
                  .reindex(alldates).fillna(0.0))
    f2 = piv.rolling(WIN, min_periods=1).sum()

    # 关注度：事件日标记 1，滚动计数
    listed = (events.assign(one=1)
                    .pivot_table(index="date", columns="asset", values="one", aggfunc="sum")
                    .reindex(alldates).fillna(0.0))
    f3 = listed.rolling(WIN, min_periods=1).sum()

    f2.to_parquet(OUT / "lhb_netbuy_20d.parquet")
    f3.to_parquet(OUT / "lhb_attention_20d.parquet")
    print(f"✅ F2 lhb_netbuy_20d: {f2.shape} (日期×股票)", flush=True)
    print(f"✅ F3 lhb_attention_20d: {f3.shape}", flush=True)
    print(f"事件数={len(events)} 覆盖股票数={len(assets)} 拉取失败季度={n_fail}", flush=True)


if __name__ == "__main__":
    main()
