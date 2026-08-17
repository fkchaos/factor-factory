"""信号冗余检查：已交付 s-code 两两对比状态一致率与 raw 相关性。

为什么需要
----------
信号线的价值在于**给策略组提供不同视角的市场状态**。若两个信号 90% 的日子给出同样
的状态，第二个就是包装过的第一个——交付它只会让对方误以为拿到了两份独立信息，
比不给更糟（与"不给假 Sharpe"同一条纪律）。

判定口径（信息项，非门槛）
--------------------------
    状态一致率 ≥ 85%  → 🔴 高度重复，建议降级/弃用
    70% ~ 85%         → ⚠️ 部分重复，可留但须在 card 注明
    < 70%             → ✅ 视角独立

注：一致率天然有基线——若两个信号各自 risk_on 占比都是 60%，随机情况下一致率也有
约 52%。故同时打印**随机基线**与**超额一致率**，避免把"都偏多头"误读成"重复"。

用法
----
    python scripts/signal_redundancy.py
    python scripts/signal_redundancy.py --scodes s0001x s0002x
"""
from __future__ import annotations

import argparse
import itertools
import json
from pathlib import Path

import pandas as pd

DELIV = Path("deliverables/signals")

HIGH, MID = 0.85, 0.70


def load_state(scode: str) -> pd.Series:
    f = DELIV / scode / "state_sequence.csv"
    if not f.exists():
        raise FileNotFoundError(f"{scode} 缺 state_sequence.csv：{f}")
    df = pd.read_csv(f, parse_dates=["date"])
    return df.set_index("date")["state"].astype(int)


def load_raw(scode: str) -> pd.Series:
    f = DELIV / scode / "state_sequence.csv"
    df = pd.read_csv(f, parse_dates=["date"])
    return df.set_index("date")["raw_value"].astype(float)


def compare(a: str, b: str) -> dict:
    sa, sb = load_state(a), load_state(b)
    idx = sa.index.intersection(sb.index)
    sa, sb = sa.loc[idx], sb.loc[idx]

    agree = float((sa == sb).mean())
    pa, pb = float(sa.mean()), float(sb.mean())
    # 随机基线：两个独立信号按各自 on 占比抛硬币时的期望一致率
    baseline = pa * pb + (1 - pa) * (1 - pb)
    excess = agree - baseline

    ra, rb = load_raw(a).loc[idx], load_raw(b).loc[idx]
    raw_corr = float(ra.corr(rb))

    verdict = ("🔴 高度重复" if agree >= HIGH else
               "⚠️ 部分重复" if agree >= MID else "✅ 视角独立")
    return {
        "pair": f"{a} vs {b}", "n_days": int(len(idx)),
        "state_agreement": round(agree, 4),
        "random_baseline": round(baseline, 4),
        "excess_agreement": round(excess, 4),
        "raw_correlation": round(raw_corr, 4),
        f"{a}_on_ratio": round(pa, 4), f"{b}_on_ratio": round(pb, 4),
        "verdict": verdict,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scodes", nargs="*", default=None)
    ap.add_argument("--out", default="deliverables/signals/_REDUNDANCY.json")
    args = ap.parse_args()

    codes = args.scodes or sorted(
        p.name for p in DELIV.iterdir()
        if p.is_dir() and (p / "state_sequence.csv").exists()
    )
    if len(codes) < 2:
        print(f"信号数 {len(codes)} < 2，无需冗余检查：{codes}")
        return 0

    rows = [compare(a, b) for a, b in itertools.combinations(codes, 2)]
    for r in rows:
        print(f"{r['pair']}  n={r['n_days']}  一致率={r['state_agreement']:.1%} "
              f"(随机基线 {r['random_baseline']:.1%}，超额 {r['excess_agreement']:+.1%})  "
              f"raw相关={r['raw_correlation']:+.3f}  {r['verdict']}")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n已写入 {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
