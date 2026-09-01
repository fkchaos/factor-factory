"""出包后回填 idea_backlog（f0014a 存货周转天数 / f0015a 应收账款周转天数）。

读 deliverables/factors/<fcode>/metrics_hs300.json，提取 RankIC/ICIR/IC胜率/方向，
回填 research/idea_backlog.csv 中 i20260820-017（存货）/ i20260820-019（应收）两行：
  status: hypothesized -> validated
  linked_fcode: f0014a / f0015a
  note: 追加「我方 PIT 口径重测结果」真实数值与方向，并标注迅投 IC 非 RankIC 口径不可直接对比。

用法：python scripts/backfill_backlog_financials.py
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKLOG = ROOT / "research" / "idea_backlog.csv"

# (灵感 id, 对应 f-code, 因子名)
TARGETS = [
    ("i20260820-017", "f0014a", "存货周转天数"),
    ("i20260820-019", "f0015a", "应收账款周转天数"),
]


def _load_metrics(fcode: str) -> dict:
    p = ROOT / "deliverables" / "factors" / fcode / "metrics_hs300.json"
    if not p.exists():
        raise FileNotFoundError(f"未找到 {p}：请先跑出包")
    return json.loads(p.read_text(encoding="utf-8"))


def main():
    rows = []
    with open(BACKLOG, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        rows = list(reader)

    by_id = {r["idea_id"]: r for r in rows}

    for idea_id, fcode, name in TARGETS:
        if idea_id not in by_id:
            print(f"[skip] {idea_id} 不在 backlog 中")
            continue
        m = _load_metrics(fcode)
        ic = m.get("ic", {})
        rank_ic = ic.get("rank_ic")
        icir = ic.get("icir")
        win = ic.get("ic_win_rate")
        n = ic.get("n_days")
        direction = ("正向" if (rank_ic or 0) > 0 else "反向") if rank_ic is not None else "—"
        bt = m.get("backtest", {}).get("net", {})
        ann = bt.get("ann_ret")
        sharpe = bt.get("sharpe")

        r = by_id[idea_id]
        r["status"] = "validated"
        r["linked_fcode"] = fcode
        tag = (f" | 我方 PIT 口径重测（{name}/{fcode}，hs300，2020 起）："
               f"RankIC={rank_ic:+.4f} ICIR={icir:+.3f} 胜率={win:.1%} n={n} "
               f"方向={direction} 净年化={ann:.1%} 净Sharpe={sharpe:.2f}。"
               f"⚠️ 迅投看板 IC 0.2~0.99 为另一口径（非 RankIC），量级不可直接对比，"
               f"我方 RankIC 偏低属常态；财报类因子存在「高IC低超额/方向或反向」陷阱，"
               f"以分池 IC + 多头超额为最终判据。")
        r["note"] = (r.get("note", "") or "") + tag
        print(f"[ok] {idea_id} -> {fcode} RankIC={rank_ic:+.4f} 方向={direction}")

    with open(BACKLOG, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)
    print(f"[done] 已写回 {BACKLOG}")


if __name__ == "__main__":
    main()
