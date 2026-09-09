"""批量串行出包驱动：一组因子逐个 build，单因子失败不中断后续。

为什么需要：build_deliverable.py 一次只出一个因子。多个因子要逐个子进程调，
且必须保证「某个因子炸了不拖垮整批」+「退出码逐个留痕」。

用法：
  python scripts/build_batch.py --pool hs300 \
      --jobs "forecast_yoy:f0073a:预告净利同比,forecast_kind:f0074a:预告类型分档"

  --jobs 格式：注册名:fcode:中文名，逗号分隔（中文名含冒号会解析错，避免）。
  --pool 默认 hs300；多池用逗号，如 hs300,hs800。
  --timeout 单因子超时秒数（默认 3600）。
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY = sys.executable


def parse_jobs(s: str):
    jobs = []
    for item in s.split(","):
        item = item.strip()
        if not item:
            continue
        parts = item.split(":")
        if len(parts) != 3:
            raise SystemExit(f"--jobs 项格式错误（应为 注册名:fcode:中文名）：{item!r}")
        jobs.append(tuple(p.strip() for p in parts))
    if not jobs:
        raise SystemExit("--jobs 为空")
    return jobs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--jobs", required=True)
    ap.add_argument("--pool", default="hs300")
    ap.add_argument("--window-start", default="2020-01-01")
    ap.add_argument("--timeout", type=int, default=3600)
    args = ap.parse_args()

    jobs = parse_jobs(args.jobs)
    results = []
    for i, (name, fcode, cn) in enumerate(jobs, 1):
        t0 = time.time()
        print(f"\n===== [{i}/{len(jobs)}] {fcode} {name} ({cn}) =====", flush=True)
        cmd = [
            PY, "scripts/build_deliverable.py",
            "--factor", name, "--fcode", fcode, "--name", cn,
            "--pools", args.pool, "--window-start", args.window_start,
        ]
        try:
            r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True,
                               encoding="utf-8", errors="replace", timeout=args.timeout)
            keep = ("RankIC", "交付包已生成", "Error", "Traceback", "❌", "KeyError", "警告")
            tail = [ln for ln in (r.stdout or "").splitlines() if any(k in ln for k in keep)]
            print("\n".join(tail[-15:]), flush=True)
            if r.returncode != 0:
                print("STDERR tail:", " | ".join((r.stderr or "").splitlines()[-8:]), flush=True)
            results.append((fcode, name, r.returncode, round(time.time() - t0)))
        except subprocess.TimeoutExpired:
            print(f"TIMEOUT {fcode}", flush=True)
            results.append((fcode, name, -1, round(time.time() - t0)))

    print("\n========== 汇总 ==========", flush=True)
    for fcode, name, rc, sec in results:
        print(f"{fcode} {name}: {'OK' if rc == 0 else f'FAIL rc={rc}'} {sec}s", flush=True)
    ok = sum(1 for _, _, rc, _ in results if rc == 0)
    print(f"成功 {ok}/{len(results)}", flush=True)


if __name__ == "__main__":
    main()
