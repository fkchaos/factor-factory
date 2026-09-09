"""一次性驱动：串行 build Phase 0 财报扩面 13 因子（hs300 单池验收）。跑完即删。

每个因子独立 subprocess 调 build_deliverable.py，单因子失败不中断后续；
退出码 + 卡上 RankIC 行打印在 stdout，供验收汇总。
"""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY = sys.executable

# (注册名, fcode, 中文名)
JOBS = [
    ("roe", "f0060a", "ROE"),
    ("roa", "f0061a", "ROA"),
    ("gross_margin", "f0062a", "毛利率"),
    ("net_margin", "f0063a", "净利率"),
    ("asset_turnover", "f0064a", "资产周转率"),
    ("operate_profit_margin", "f0065a", "营业利润率"),
    ("financial_leverage", "f0066a", "财务杠杆"),
    ("cash_coverage", "f0067a", "盈利现金保障"),
    ("accrual", "f0068a", "应计"),
    ("deduct_ratio", "f0069a", "扣非净利占比"),
    ("ep", "f0070a", "EP盈利市值比"),
    ("revenue_yoy", "f0071a", "营收同比"),
    ("netprofit_yoy", "f0072a", "净利同比"),
]


def main():
    results = []
    for i, (name, fcode, cn) in enumerate(JOBS, 1):
        t0 = time.time()
        print(f"\n===== [{i}/{len(JOBS)}] {fcode} {name} ({cn}) =====", flush=True)
        cmd = [
            PY, "scripts/build_deliverable.py",
            "--factor", name, "--fcode", fcode, "--name", cn,
            "--pools", "hs300", "--window-start", "2020-01-01",
        ]
        try:
            r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True,
                               encoding="utf-8", errors="replace", timeout=3600)
            # 打印关键行：IC/卡上指标/报错
            tail = [ln for ln in (r.stdout or "").splitlines()
                    if any(k in ln for k in ("RankIC", "交付包已生成", "Error", "Traceback", "❌", "KeyError"))]
            print("\n".join(tail[-15:]), flush=True)
            if r.returncode != 0:
                err_tail = (r.stderr or "").splitlines()[-8:]
                print("STDERR tail:", " | ".join(err_tail), flush=True)
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
