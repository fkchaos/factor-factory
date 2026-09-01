"""预热 AkShare 财报披露历史缓存（供 f0014a/f0015a 出包前调用）。

背景：单只股票的东财利润表+资产负债表披露历史 fresh 拉取约 18~20s，
hs300 约 300 只 → 首包预载近 95 分钟，且易触发限流。本脚本把这块网络密集工作
**单独**跑（后台、可断点续：已落 parquet 的代码直接读盘跳过），跑完后再出包，
出包时 default_store 读缓存 → 秒级。

用法：
  python scripts/prewarm_financials.py --pool hs300
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from data.providers import AkShareProvider, BaoStockProvider
from data.contract import normalize_code


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pool", default="hs300")
    args = ap.parse_args()

    # 取池子成分股（baostock 接口，落 csv 缓存）
    try:
        bs = BaoStockProvider(universe=args.pool, history_start="2020-01-01")
        codes = bs._asset_list()
    except Exception as e:
        print(f"[warn] BaoStock 取池失败，用空列表降级：{e!r}", flush=True)
        codes = []
    if not codes:
        print("[error] 未能取得成分股列表，退出", flush=True)
        return
    codes = [normalize_code(c) for c in codes]
    print(f"[prewarm] 池 {args.pool} 共 {len(codes)} 只，开始预热 AkShare 财报缓存", flush=True)

    ak = AkShareProvider()
    ok = err = skip = 0
    t0 = time.time()
    for i, code in enumerate(codes, 1):
        key = ak._cache / "financial" / f"{code}.parquet"
        if key.exists():
            skip += 1
            print(f"[{i}/{len(codes)}] skip {code} (cached)", flush=True)
            continue
        t1 = time.time()
        try:
            df = ak._fetch_financial_history(code)
            ok += 1
            print(f"[{i}/{len(codes)}] ok   {code} rows={len(df)} {time.time()-t1:.1f}s", flush=True)
        except Exception as e:
            err += 1
            print(f"[{i}/{len(codes)}] ERR  {code}: {e!r} {time.time()-t1:.1f}s", flush=True)
    print(f"[prewarm] 完成：ok={ok} skip={skip} err={err} 耗时={time.time()-t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
