"""把灵感池候选标记为已交付（晋级为 f-code）。

用法：
  python3 research/mark_delivered.py <idea_id> <fcode> "<交付结论摘要>"

- 置 status=validated（本项目语义：已从灵感池晋级为交付因子，强弱由策略组判，与 validated 强度无关）
- 填 linked_fcode=<fcode>（结构化字段，便于看板/脚本识别消费）
- 在 note 追加交付日期 + 结论
幂等：重复执行不重复追加。
"""
import csv, sys, os, datetime

BACKLOG = os.path.join(os.path.dirname(__file__), "..", "research", "idea_backlog.csv")
BACKLOG = os.path.abspath(BACKLOG)


def main():
    if len(sys.argv) < 3:
        print("usage: mark_delivered.py <idea_id> <fcode> <note>"); sys.exit(1)
    idea_id, fcode = sys.argv[1], sys.argv[2]
    note = sys.argv[3] if len(sys.argv) > 3 else ""
    today = datetime.date.today().isoformat()

    rows = list(csv.DictReader(open(BACKLOG, encoding="utf-8-sig")))
    hit = [r for r in rows if r["idea_id"] == idea_id]
    if not hit:
        print(f"!! 未找到 {idea_id}"); sys.exit(2)
    r = hit[0]
    r["linked_fcode"] = fcode
    r["status"] = "validated"
    add = f"{today} 交付为 {fcode}：{note}"
    if add not in r["note"]:
        r["note"] = (r["note"].strip() + " | " + add).strip(" |") if r["note"].strip() else add

    cols = list(rows[0].keys())
    with open(BACKLOG, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    print(f"✅ {idea_id} -> {fcode} (status=validated, linked_fcode 已填)")


if __name__ == "__main__":
    main()
