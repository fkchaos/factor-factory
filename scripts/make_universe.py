"""用 AkShare 生成股票池 CSV 落缓存（绕开 Tushare stock_basic 免费档限频 1次/小时）。

用法：
    python scripts/make_universe.py SZ        # 深交所股票池 -> .cache/tushare/asset_list_SZ.csv
    python scripts/make_universe.py SH        # 上交所
    python scripts/make_universe.py ALL       # 全A（对应 universe=L）
    python scripts/make_universe.py SZ --count 100   # 只取前 100 只（快速验证用）

输出格式与 TushareProvider._asset_list 的缓存一致（ts_code 列，规范代码 6位.交易所）。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))  # 先设路径再 import 本地包

from data.contract import normalize_code  # noqa: E402

CACHE = ROOT / ".cache" / "tushare"
CACHE.mkdir(parents=True, exist_ok=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["SZ", "SH", "BJ", "ALL"], help="股票池模式")
    ap.add_argument("--count", type=int, default=0, help="只取前 N 只（0=全部）")
    args = ap.parse_args()

    import akshare as ak  # 懒导入

    df = ak.stock_info_a_code_name()  # 全A：code/name（含退市风险，无后缀）
    codes = [normalize_code(c) for c in df["code"]]
    if args.mode != "ALL":
        suffix = {"SZ": ".SZ", "SH": ".SH", "BJ": ".BJ"}[args.mode]
        codes = [c for c in codes if c.endswith(suffix)]
    if args.count:
        codes = codes[: args.count]
    out = CACHE / f"asset_list_{args.mode}.csv"
    pd.DataFrame({"ts_code": codes}).to_csv(out, index=False)
    print(f"✅ 股票池已生成: {out} ({len(codes)} 只)")


if __name__ == "__main__":
    main()
