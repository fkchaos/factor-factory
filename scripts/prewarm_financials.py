"""预热财报披露历史缓存（供出包前调用，支持双后端）。

背景：单只股票的财报披露历史 fresh 拉取约 15~20s（AkShare）/ ~17s（BaoStock），
hs300 约 300 只 → 首包预载近 95 分钟，且易触发限流。本脚本把这块网络密集工作
**单独**跑（后台、可断点续：有效缓存直接读盘跳过），跑完后再出包，
出包时 default_store 读缓存 → 秒级。

🔴 为什么必须双后端（2026-10-10 血泪，Phase A）
 Phase A 给 BaoStock 端新加了 balance_data 流（currentRatio/quickRatio 等），
 单票调用量翻倍；而旧 prewarm **只预热 AkShare 端** → BaoStock 端缓存大量缺失。
 结果 f0092a 首次出包时 ~200 只票冷启动联网，直接撞上 build 的 3600s 超时。
 教训：**PIT 服务是几后端，prewarm 就得覆盖几后端**，加新流时尤其要同步。

用法：
  python scripts/prewarm_financials.py --pool hs300              # 双后端（默认）
  python scripts/prewarm_financials.py --pool hs300 --backend bs  # 只预热 BaoStock
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


def warm_one(prov, code, cache_cols):
    """预热单个后端的单只股票；返回 (状态, 耗时秒, 行数)。"""
    key = prov._cache / "financial" / f"{code}.parquet"
    if key.exists():
        # 🔴 缓存列指纹（与各自 _fetch_financial_history 对齐）：旧字段版缓存缺新列
        # 会静默 NaN——文件在≠有效。读列全集校验，缺列视为失效重拉。
        # （此前纯 exists() 判断：改字段后 prewarm 全 skip，build 侧才被动重拉，
        #   网络密集工作被塞进出包阶段且不可断点。）
        try:
            import pandas as pd
            cached_cols = list(pd.read_parquet(key).columns)
            if all(c in cached_cols for c in cache_cols):
                return "skip", 0.0, 0
            stale = "stale"
        except Exception:
            stale = "broken"
    else:
        stale = "miss"
    t = time.time()
    try:
        df = prov._fetch_financial_history(code)
        return "ok", time.time() - t, len(df)
    except Exception:
        return "err", time.time() - t, 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pool", default="hs300")
    ap.add_argument("--backend", default="both", choices=["ak", "bs", "both"],
                    help="预热哪个后端（默认 both=PIT 服务实际用到的两个）")
    ap.add_argument("--limit", type=int, default=0,
                    help="只处理前 N 只（冒烟用），0=全部")
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
    if args.limit > 0:
        codes = codes[: args.limit]

    providers = []
    if args.backend in ("ak", "both"):
        providers.append(AkShareProvider())
    if args.backend in ("bs", "both"):
        providers.append(BaoStockProvider(universe=args.pool, history_start="2020-01-01"))

    print(f"[prewarm] 池 {args.pool} 共 {len(codes)} 只，后端 "
          f"{[type(p).__name__ for p in providers]}", flush=True)

    stat = {"ok": 0, "err": 0, "skip": 0, "stale": 0, "broken": 0, "miss": 0}
    t0 = time.time()
    for i, code in enumerate(codes, 1):
        for p in providers:
            cache_cols = getattr(p, "_PIT_CACHE_COLS", []) or []
            st, dt, n = warm_one(p, code, cache_cols)
            if st in ("stale", "broken", "miss"):
                stat[st] += 1
                st2, dt2, n2 = "retry", dt, n
                key = p._cache / "financial" / f"{code}.parquet"
                t = time.time()
                try:
                    df = p._fetch_financial_history(code)
                    st2, dt2, n2 = "ok", time.time() - t, len(df)
                except Exception:
                    st2 = "err"
                stat[st2] += 1
                print(f"[{i}/{len(codes)}] {type(p).__name__:16} {code} {st}->{st2} "
                      f"rows={n2} {dt2:.1f}s", flush=True)
            else:
                stat[st] += 1
                if st == "ok":
                    print(f"[{i}/{len(codes)}] {type(p).__name__:16} {code} ok "
                          f"rows={n} {dt:.1f}s", flush=True)
    # skip/broken/miss 与结算 cols 说明
    cols = ", ".join(f"{k}={v}" for k, v in stat.items())
    print(f"[prewarm] 完成：{cols} 耗时={time.time()-t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
