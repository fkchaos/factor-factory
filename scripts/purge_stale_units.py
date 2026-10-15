"""把池子矩阵里「旧口径」的单元格清空，只保留 turnover 修复后新算的值。

为什么必须做（2026-10-15）：
  验证器 validate_factor 的默认 fields 长期漏了 "turnover"（2026-10-13 22:03 修复）。
  缺 turnover → data/pit.py::pit_float_mcap() 算不出 PIT 流通市值 → 中性化被降级为
  「只做行业、跳过市值」→ 与交付卡片（行业+市值都做）不是同一个口径。
  实测：修复后新算的单元与卡片差 2.46e-06（等价）；修复前的老值差 3.64e-03，
  例如 ivol 卡片 0.0185 vs 矩阵 0.0321 —— 差了 1.7 倍，是实质性偏差。

如何识别新旧：
  分片 CSV 是整文件重写的，无法从文件本身区分单个单元格是何时算的。
  唯一可靠来源是各块的运行日志——只有「真正新算出结果」的单元会打印
  `因子名: RankIC=...`，被跳过的打印 `skip 因子/池`。
  因此：新口径集合 = 所有 10-13 22:00 之后启动的批次日志里出现过 RankIC 行的
  (因子, 池) 组合。不在此集合的单元格一律置 NaN，等下轮补齐。

用法：
  python .cache/purge_stale_units.py            # 预演，只打印不落盘
  python .cache/purge_stale_units.py --apply    # 真正清空
"""
from __future__ import annotations

import re
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "deliverables" / "universe_matrix"
PARTS = OUT / "parts"

# 修复提交时间：2026-10-13 22:03:38 (+0800)。晚于此的批次才算新口径。
CUT = time.mktime(time.strptime("2026-10-13 22:00:00", "%Y-%m-%d %H:%M:%S"))


def collect_new_units() -> set[tuple[str, str]]:
    """扫描批次日志，返回新口径的 (因子名, 池子) 集合。"""
    new: set[tuple[str, str]] = set()
    for f in sorted(OUT.glob("_p4_*.log")):
        if f.name == "_p4_run_2026-10-10.log":
            continue  # 最老的一轮，肯定旧口径
        if f.stat().st_mtime < CUT:
            continue  # 修复之前启动/最后写入的批次
        text = f.read_text(encoding="utf-8", errors="ignore")
        # 文件名 _p4_<tag>.log → pool = tag 去掉 -cN 分片后缀
        pool = f.stem[4:].split("-c")[0]
        for m in re.finditer(r"^\s*([\w_]+):\s*RankIC=", text, re.M):
            new.add((m.group(1), pool))
    return new


def main() -> None:
    apply = "--apply" in sys.argv
    new = collect_new_units()
    print(f"新口径单元格（日志可追溯） = {len(new)}")

    # 以最新的主矩阵为准
    mains = sorted(OUT.glob("ic_matrix_*.csv"))
    if not mains:
        print("❌ 找不到主矩阵 ic_matrix_*.csv")
        return
    stamp = mains[-1].name[len("ic_matrix_"):-4]  # 去掉 ".csv"
    print(f"基准主矩阵 = ic_matrix_{stamp}\n")

    stats = {}
    for kind in ("ic", "icir", "dsr"):
        p = OUT / f"{kind}_matrix_{stamp}.csv"
        df = pd.read_csv(p, index_col=0)
        before = int(df.notna().sum().sum())
        cleared = 0
        for r in df.index:
            for c in df.columns:
                if pd.isna(df.loc[r, c]):
                    continue
                if (r, c) not in new:
                    df.loc[r, c] = np.nan
                    cleared += 1
        after = int(df.notna().sum().sum())
        stats[kind] = (before, cleared, after)
        print(f"{kind:5s}: {before:4d} → 清空 {cleared:4d} → 剩余 {after:4d}")
        if apply:
            df.to_csv(p)
            print(f"   ✅ 已写回 {p.name}")

    if apply:
        # 分片已并入主矩阵，清空以免下一轮重复继承旧口径值
        n = 0
        for f in sorted(PARTS.glob("*.csv")):
            f.unlink()
            n += 1
        print(f"\n已清空分片文件 {n} 个（下一轮统一从主矩阵继承进度）")
    else:
        print("\n（预演模式，未写盘。加 --apply 生效）")


if __name__ == "__main__":
    main()
