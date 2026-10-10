"""P4 池子矩阵并行调度器（2026-10-10）。

为什么要有这个脚本
------------------
`factor_universe_matrix.py` 单进程跑 96 因子 × 7 池 = 672 个验证单元，实测 ≈2.9 分钟/单元起、
且**单单元耗时随池子规模显著上升**（ALL 池 3107 只票 ≈65 分钟/单元）→ 串行需数天，机器 16 核只用一个。

调度思路：**按池分片 × 按因子分块**，块数按各池预估 CPU 小时数分配，使所有块大致同时跑完
（否则 16 核里 15 个空闲、等最慢那个块，等于没并行）。

- 每个块 = 一个子进程：`factor_universe_matrix.py --factors <块内因子> --pools <pool> --tag <pool>-c<i>`
  产物落在 `parts/ic_matrix_<pool>-c<i>.csv`，互不覆盖、可断点续算（重跑会跳过已有单元格）。
- 因子分块用**轮转**（names[i::k]）而非连续切段：因子快慢差异大，连续切容易把慢因子堆到同一块。
- 跑完用 `scripts/merge_universe_matrix.py` 合并回主矩阵（只填 NaN，故同池多块互补不互踩）。

用法：
    python scripts/run_matrix_parallel.py                       # 用默认 plan
    python scripts/run_matrix_parallel.py --plan "sz50:1,ALL:12"
    python scripts/run_matrix_parallel.py --dry-run             # 只打印将要启动的命令
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOG_DIR = ROOT / "deliverables" / "universe_matrix"

# 块数按"各池预估 CPU 小时"分配（池子越大越慢 → 切越多块）。
# 依据 2026-10-10 实测：sz50≈2.9 分/单元、hs300≈4、zz500≈6、hs800≈9、zz1000≈9、hs1800≈18、ALL≈35。
DEFAULT_PLAN = "sz50:1,hs300:1,zz500:1,hs800:2,zz1000:2,hs1800:3,ALL:6"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", default=DEFAULT_PLAN,
                    help="池:块数 的逗号分隔表；块数≈该池预估CPU小时/目标墙钟")
    ap.add_argument("--start", default="2020-01-01")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    sys.path.insert(0, str(ROOT))
    import factors  # noqa: F401  触发全量注册
    from factors.interface import list_factors
    names = list_factors()

    plan: list[tuple[str, int]] = []
    for item in args.plan.split(","):
        item = item.strip()
        if not item:
            continue
        pool, _, k = item.partition(":")
        plan.append((pool.strip(), int(k or 1)))

    jobs: list[tuple[str, list[str], list[str]]] = []  # (tag, factor_names, argv)
    for pool, k in plan:
        k = max(1, min(k, len(names)))
        for i in range(k):
            chunk = names[i::k]  # 轮转分块：慢因子不会堆在同一块
            tag = f"{pool}-c{i+1}" if k > 1 else pool
            argv = [sys.executable, str(ROOT / "scripts" / "factor_universe_matrix.py"),
                    "--factors", ",".join(chunk), "--pools", pool,
                    "--tag", tag, "--start", args.start]
            jobs.append((tag, chunk, argv))

    print(f"[plan] {len(names)} 因子 → {len(jobs)} 个并行块 "
          f"（目标墙钟≈各块 CPU 小时的最大值）")
    for tag, chunk, _ in jobs:
        print(f"  {tag}: {len(chunk)} 因子")

    if args.dry_run:
        return

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    procs = []
    for tag, _, argv in jobs:
        log = LOG_DIR / f"_p4_{tag}.log"
        fh = open(log, "w", encoding="utf-8")
        procs.append((tag, subprocess.Popen(argv, cwd=str(ROOT), stdout=fh, stderr=subprocess.STDOUT), fh))

    print(f"\n[run] 已启动 {len(procs)} 个子进程，日志 deliverables/universe_matrix/_p4_<tag>.log")
    codes = []
    for tag, p, fh in procs:
        code = p.wait()
        fh.close()
        codes.append((tag, code))
        print(f"  [done] {tag} exit={code}", flush=True)

    bad = [t for t, c in codes if c != 0]
    print("\n[summary] " + ("全部块 exit=0" if not bad else f"非零退出：{bad}"))
    print("下一步：python scripts/merge_universe_matrix.py")


if __name__ == "__main__":
    main()
