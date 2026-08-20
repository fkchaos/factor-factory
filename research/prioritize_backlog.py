# -*- coding: utf-8 -*-
"""
为灵感池 idea_backlog.csv 计算优先级（量化优势优先）。
- xuntou_kanban 候选：从 raw_idea 解析 IC/IR/最大分位超额/最大分位换手，
  算量化价值分 composite，含"高IC低超额"陷阱封顶；按 composite 排名分配 P0/P1。
- 非 xuntou：按来源分层（downstream_feedback=P1，paper/zoo/sell_side=P2，forum=P3）。
- status=validated 的已验证项直接 P0。
输出：覆盖写回 idea_backlog.csv（新增 3 列，按优先级排序）+ 生成 prioritized_backlog.md 视图。
幂等：重跑安全（会先剥离旧 priority 列再重算）。
"""
import csv, re, os

HERE = os.path.dirname(os.path.abspath(__file__))
CSV_PATH = os.path.join(HERE, "idea_backlog.csv")

# ---- 权重（透明可调）----
W_IC = 0.30
W_IR = 0.25
W_EXCESS = 0.30
W_TURNOVER = 0.15
EXCESS_SCALE = 50.0      # 最大分位超额年化 /50 归一（业界封顶约50%）
TRAP_IC = 0.60           # IC 高阈值
TRAP_EXCESS = 5.0        # 最大分位超额 <5% 视为无真实超额
TRAP_CAP = 0.25          # 陷阱项 composite 封顶

XUNTOU_P0_TOPN = 6       # xuntou 按分排前 N 名为 P0

SRC_TIER = {             # 非 xuntou 来源分层
    "downstream_feedback": ("P1", 60, "策略组明确需求，次之推进"),
    "paper":               ("P2", 45, "学术/论文来源，研究价值中等"),
    "zoo":                 ("P2", 45, "因子动物园来源，研究价值中等"),
    "sell_side":           ("P2", 42, "卖方研究来源，研究价值中等"),
    "forum":               ("P3", 35, "社区闲聊来源，未验证，最低"),
}

RAW_RE = re.compile(
    r"^(?P<name>.+?)：迅投口径 IC=(?P<ic>[-0-9.]+), IR=(?P<ir>[-0-9.]+), "
    r"最大分位超额=(?P<excess>[-0-9.]+)%, 最大分位换手=(?P<turnover>[-0-9.]+)%"
)

def parse_xuntou(raw):
    m = RAW_RE.match(raw.strip())
    if not m:
        return None
    return {
        "ic": float(m.group("ic")),
        "ir": float(m.group("ir")),
        "excess": float(m.group("excess")),
        "turnover": float(m.group("turnover")),
    }

def composite(m):
    ic, ir, excess, turn = m["ic"], m["ir"], m["excess"], m["turnover"]
    ex_n = max(0.0, min(1.0, excess / EXCESS_SCALE))
    c = W_IC * ic + W_IR * ir + W_EXCESS * ex_n - W_TURNOVER * turn
    trap = (ic >= TRAP_IC) and (excess < TRAP_EXCESS)
    if trap:
        c = min(c, TRAP_CAP)
    return c, trap

def main():
    rows = list(csv.DictReader(open(CSV_PATH, encoding="utf-8-sig")))
    # 幂等：剥离旧 priority 列
    for r in rows:
        for k in ("priority", "priority_score", "priority_basis"):
            r.pop(k, None)

    # 1) 算 xuntou composite
    xuntou = []
    for r in rows:
        if r["source_type"] == "xuntou_kanban":
            m = parse_xuntou(r["raw_idea"])
            if m:
                c, trap = composite(m)
                r["_comp"] = c
                r["_trap"] = trap
                r["_metrics"] = m
                xuntou.append(r)
            else:
                # 解析失败（如分类规律/方向性建议，无单因子量化分）→ 兜底 P1
                r["priority"] = "P1"
                r["priority_score"] = 58.0
                r["priority_basis"] = "xuntou 方向性/规律建议（无单因子量化分），随量化候选同期推进"
    xuntou.sort(key=lambda r: r["_comp"], reverse=True)
    for i, r in enumerate(xuntou):
        if i < XUNTOU_P0_TOPN:
            r["priority"] = "P0"
            r["priority_score"] = round(r["_comp"] * 100, 1)
            r["priority_basis"] = (
                f"xuntou量化价值分Top{XUNTOU_P0_TOPN}（IC={r['_metrics']['ic']:.2f},"
                f"IR={r['_metrics']['ir']:.2f},超额={r['_metrics']['excess']:.1f}%,"
                f"换手={r['_metrics']['turnover']:.2f}%）"
                + ("；⚠️高IC低超额陷阱已封顶" if r["_trap"] else "")
            )
        else:
            r["priority"] = "P1"
            r["priority_score"] = round(r["_comp"] * 100, 1)
            r["priority_basis"] = (
                f"xuntou量化价值分（IC={r['_metrics']['ic']:.2f},"
                f"IR={r['_metrics']['ir']:.2f},超额={r['_metrics']['excess']:.1f}%,"
                f"换手={r['_metrics']['turnover']:.2f}%）"
                + ("；⚠️高IC低超额陷阱已封顶" if r["_trap"] else "")
            )

    # 2) 非 xuntou 分层
    for r in rows:
        if r["source_type"] == "xuntou_kanban":
            continue
        if r.get("status") == "validated":
            r["priority"] = "P0"
            r["priority_score"] = 95.0
            r["priority_basis"] = "已验证(validated)，直接优先"
            continue
        tier = SRC_TIER.get(r["source_type"], ("P3", 30, "未分类来源"))
        r["priority"] = tier[0]
        r["priority_score"] = float(tier[1])
        r["priority_basis"] = tier[2]

    # 3) 排序：P0<P1<P2<P3，同层按分数降序
    prank = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
    rows.sort(key=lambda r: (prank.get(r["priority"], 9), -float(r.get("priority_score", 0))))

    # 清洗临时字段
    for r in rows:
        for k in ("_comp", "_trap", "_metrics"):
            r.pop(k, None)

    # 4) 写回
    fieldnames = list(rows[0].keys())
    if "priority" not in fieldnames:
        fieldnames += ["priority", "priority_score", "priority_basis"]
    with open(CSV_PATH, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow(r)

    # 5) 统计 + 视图
    from collections import Counter
    dist = Counter(r["priority"] for r in rows)
    print("优先级分布:", dict(sorted(dist.items())))
    print("\n=== P0 / P1 顶层候选（最优价值先搞）===")
    for r in rows:
        if r["priority"] in ("P0", "P1"):
            tag = r["idea_id"]
            print(f"[{r['priority']}] {tag}  score={r['priority_score']:<5} {r['raw_idea'][:50]}")

    # 写 markdown 视图
    md = ["# 灵感池优先级视图（量化优势优先）", "",
          f"生成基于 `prioritize_backlog.py`。分布：", ""]
    md.append("| 优先级 | 数量 |")
    md.append("|---|---|")
    for p in ("P0", "P1", "P2", "P3"):
        md.append(f"| {p} | {dist.get(p,0)} |")
    md.append("")
    md.append("## 顶层候选（先搞这些）")
    md.append("")
    for p in ("P0", "P1"):
        md.append(f"### {p}")
        for r in rows:
            if r["priority"] == p:
                md.append(f"- **{r['idea_id']}** ({r['source_type']}) — {r['raw_idea'][:70]}")
                md.append(f"  - 依据：{r['priority_basis']}")
        md.append("")
    with open(os.path.join(HERE, "prioritized_backlog.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(md))
    print("\n已写回 idea_backlog.csv 并生成 prioritized_backlog.md")

if __name__ == "__main__":
    main()
