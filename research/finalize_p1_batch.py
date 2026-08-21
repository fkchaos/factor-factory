"""P1 批量构建完成后，回填灵感池：从各因子 card 提取真实指标，标记对应 idea 为 validated。

映射：fcode -> (idea_id, 中文名, 灵感池 raw_idea 关键字)
"""
from __future__ import annotations
import csv, re, os
from collections import OrderedDict

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
BL = os.path.join(ROOT, "research", "idea_backlog.csv")
FAC = os.path.join(ROOT, "deliverables", "factors")

# fcode -> (idea_id, 因子中文名)
MAP = OrderedDict([
    ("f0017a", ("i20260820-013", "5日平均换手率")),
    ("f0018a", ("i20260820-026", "5日指数移动均线")),
    ("f0019a", ("i20260820-027", "10日指数移动均线")),
    ("f0020a", ("i20260820-015", "12日指数移动均线")),
    ("f0021a", ("i20260820-025", "120日指数移动均线")),
    ("f0022a", ("i20260820-023", "5日移动均线")),
    ("f0023a", ("i20260820-021", "20日成交金额的移动平均值")),
    ("f0024a", ("i20260820-016", "20日资金流量")),
    ("f0025a", ("i20260820-018", "上轨线（布林线）指标")),
])


def extract_metrics(fcode):
    card = os.path.join(FAC, fcode, "card.md")
    if not os.path.exists(card):
        return None
    txt = open(card, encoding="utf-8").read()
    def grab(pat):
        m = re.search(pat, txt)
        return m.group(1) if m else "?"
    return {
        "rankic": grab(r"RankIC\s*\|\s*(-?[\d.]+)"),
        "icir": grab(r"ICIR\s*\|\s*(-?[\d.]+)"),
        "win": grab(r"IC\s*胜率\s*\|\s*([\d.]+)"),
        "sharpe": grab(r"Sharpe[^\d-]*\|?\s*(-?[\d.]+)"),
        "direction": grab(r"方向[：:]\s*([^（\s，]+)"),
    }


def main():
    rows = list(csv.DictReader(open(BL, encoding="utf-8-sig")))
    fieldnames = list(rows[0].keys())
    by_id = {r["idea_id"]: r for r in rows}
    for fcode, (idea_id, cn) in MAP.items():
        m = extract_metrics(fcode)
        if m is None:
            print(f"[SKIP] {fcode} 无 card，跳过")
            continue
        r = by_id.get(idea_id)
        if r is None:
            print(f"[WARN] {idea_id} 不在池，fcode={fcode}")
            continue
        r["status"] = "validated"
        r["linked_fcode"] = fcode
        note = (r.get("note", "") or "").strip()
        if "已交付" in note:  # 幂等：清掉本脚本上一轮加的旧 suffix
            note = note[:note.index("已交付")].rstrip().rstrip("|").rstrip()
        suffix = f"已交付{fcode}（{cn}）；我方PIT口径 RankIC={m['rankic']} / ICIR={m['icir']} / 胜率{m['win']}% / Sharpe={m['sharpe']} / 方向{m['direction']}；迅投IC为另一口径，强弱交策略组判"
        r["note"] = (note + " | " + suffix) if note else suffix
        print(f"[OK] {idea_id} -> {fcode} ({cn}) RankIC={m['rankic']} ICIR={m['icir']}")
    with open(BL, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)
    print("=== 灵感池已回填 ===")


if __name__ == "__main__":
    main()
