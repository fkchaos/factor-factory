"""P0 价格/量能类因子交付后处理（batch2 跑完后调用）。

对每个已构建的 f-code：
- 从 deliverables/factors/<fcode>/card.md 提取 RankIC/ICIR/IC胜率/Sharpe/方向
- 回填灵感池对应 idea_id（status=validated, linked_fcode, note 含真实口径指标）
对数据阻塞的基本面因子（存货/应收账款周转天数）：
- 仅追加 note 标明"数据阻塞，需 PIT 基本面管线"，不改 status（仍为 hypothesized）

映射（fcode -> idea_id）：
  f0011a -> i20260820-022 (120日平均换手率, 已标)
  f0012a -> i20260820-014 (10日平均换手率)
  f0013a -> i20260820-020 (240日平均换手率)
  f0016a -> i20260820-024 (20日成交金额标准差)
阻塞：
  i20260820-017 (存货周转天数)
  i20260820-019 (应收账款周转天数)
幂等：已 validated 的行跳过；note 不重复追加。
"""
import csv, re, os, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
BACKLOG = os.path.abspath(os.path.join(HERE, "..", "research", "idea_backlog.csv"))
DELIV = os.path.abspath(os.path.join(HERE, "..", "deliverables", "factors"))

MAPPING = {
    "f0011a": "i20260820-022",
    "f0012a": "i20260820-014",
    "f0013a": "i20260820-020",
    "f0016a": "i20260820-024",
}
BLOCKED = ["i20260820-017", "i20260820-019"]


def extract_card(fcode):
    path = os.path.join(DELIV, fcode, "card.md")
    if not os.path.exists(path):
        return None
    txt = open(path, encoding="utf-8").read()
    d = {}
    m = re.search(r"\|\s*RankIC\s*\|\s*([-\d.]+)", txt)
    if m: d["rankic"] = m.group(1)
    m = re.search(r"\|\s*ICIR\s*\|\s*([-\d.]+)", txt)
    if m: d["icir"] = m.group(1)
    m = re.search(r"\|\s*IC 胜率\s*\|\s*([\d.]+)%", txt)
    if m: d["win"] = m.group(1)
    m = re.search(r"\|\s*Sharpe\(净\)\s*\|\s*([-\d.]+)", txt)
    if m: d["sharpe"] = m.group(1)
    m = re.search(r"类别 / 方向[:：]\s*(.+)", txt)
    if m: d["dir"] = m.group(1).strip()
    return d


def main():
    today = datetime.date.today().isoformat()
    rows = list(csv.DictReader(open(BACKLOG, encoding="utf-8-sig")))
    by_id = {r["idea_id"]: r for r in rows}
    changed = []

    for fcode, idea_id in MAPPING.items():
        card = extract_card(fcode)
        if card is None:
            print(f"[skip] {fcode}: card.md 未生成（batch2 未完成？）")
            continue
        r = by_id.get(idea_id)
        if r is None:
            print(f"[warn] {idea_id} 不在灵感池"); continue
        if r["status"] == "validated":
            print(f"[skip] {idea_id} 已 validated"); continue
        note = (f"{today} 交付为 {fcode}：我方PIT口径 "
                f"RankIC={card.get('rankic','?')} / ICIR={card.get('icir','?')} "
                f"/ 胜率{card.get('win','?')}% / Sharpe(净){card.get('sharpe','?')} "
                f"/ 方向{card.get('dir','?')}；迅投IC为另一口径，已如实交付交策略组判强弱")
        r["linked_fcode"] = fcode
        r["status"] = "validated"
        if note not in r["note"]:
            r["note"] = (r["note"].strip() + " | " + note).strip(" |") if r["note"].strip() else note
        changed.append((idea_id, fcode))

    for idea_id in BLOCKED:
        r = by_id.get(idea_id)
        if r is None: continue
        blk = (f"{today} 数据阻塞：需 PIT 基本面管线（存货/应收账款来自利润表+资产负债表），"
               "当前 BaoStockProvider.get_pit_financials 为未实现桩，另开慢车道评估")
        if "数据阻塞" not in r["note"]:
            r["note"] = (r["note"].strip() + " | " + blk).strip(" |") if r["note"].strip() else blk
            changed.append((idea_id, "BLOCKED"))

    cols = list(rows[0].keys())
    with open(BACKLOG, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader(); w.writerows(rows)
    print(f"\n✅ 已更新 {len(changed)} 行：")
    for i, fc in changed:
        print(f"   {i} -> {fc}")


if __name__ == "__main__":
    main()
