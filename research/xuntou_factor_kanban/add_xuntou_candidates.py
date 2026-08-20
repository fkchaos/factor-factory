#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把迅投因子看板的分类规律 + Top 优质因子候选写入灵感池 idea_backlog.csv。"""
import csv, os, re

HERE = os.path.dirname(os.path.abspath(__file__))
BACKLOG = os.path.join(HERE, "..", "idea_backlog.csv")
MERGED = os.path.join(HERE, "merged_by_category.csv")

# 读现有灵感池，找最大序号
with open(BACKLOG, encoding="utf-8-sig", newline="") as f:
    reader = csv.DictReader(f)
    fieldnames = reader.fieldnames
    rows = list(reader)

maxn = 0
for r in rows:
    m = re.match(r"i\d{8}-(\d+)", r.get("idea_id", ""))
    if m:
        maxn = max(maxn, int(m.group(1)))

counter = {"n": maxn}
def next_id():
    counter["n"] += 1
    return f"i20260820-{counter['n']:03d}"

# 读合并数据集
recs = []
with open(MERGED, encoding="utf-8-sig", newline="") as f:
    for r in csv.DictReader(f):
        recs.append(r)

def fnum(s):
    try:
        return float(str(s).strip().replace("%", "").replace(",", ""))
    except Exception:
        return None

# 筛选：低换手(最大分位换手<=1%) + 高超额(最大分位超额>=15%)，按 IC 降序取前 15
cand = [r for r in recs
        if (fnum(r["最大分位换手"]) is not None and fnum(r["最大分位换手"]) <= 1.0)
        and (fnum(r["最大分位超额年化"]) is not None and fnum(r["最大分位超额年化"]) >= 15.0)]
cand.sort(key=lambda r: fnum(r["IC"]) or 0, reverse=True)
cand = cand[:15]

new_rows = []
for r in cand:
    cat = r["分类"]; name = r["因子名称"]
    ic = r["IC"]; ir = r["IR"]; mret = r["最大分位超额年化"]; mtur = r["最大分位换手"]
    new_rows.append({
        "idea_id": next_id(),
        "source_type": "xuntou_kanban",
        "source_ref": f"迅投因子看板(沪深300/近1年)/{cat}",
        "raw_idea": f"{name}：迅投口径 IC={ic}, IR={ir}, 最大分位超额={mret}%, 最大分位换手={mtur}%",
        "hypothesis": "该因子在迅投口径下 IC 高且低换手高超额，可尝试在我方 PIT 口径（pit_float_mcap 中性化、exec_lag=1）下复现并验证方向",
        "rationale": f"来自迅投因子看板「{cat}」，属 IC/IR 排名靠前且性价比优（低换手高超额）的因子，值得作为灵感候选",
        "confidence_seed": "medium",
        "status": "hypothesized",
        "created_at": "2026-08-20",
        "owner": "factor-scout",
        "linked_fcode": "",
        "review_cycle": "2027-02-16",
        "hit_status": "pending",
        "note": "⚠️ 迅投 IC 量级 0.2~0.99 非 RankIC，不可直接对比我方 RankIC；仅作灵感来源，须我方口径重测",
        "fcode": "",
    })

# 3 条分类规律建议
patterns = [
    ("成长/动量/情绪类因子整体信息含量最高（均值IC 0.52~0.56），应作为灵感因子的主要来源池",
     "优先从成长、动量、情绪三类挖掘候选，因其在迅投全市场回测中平均 IC 显著高于其他类（风险/风格类仅0.32）",
     "基于迅投9分类412因子均值IC排序"),
    ("财务类因子数量巨大(248,占60%)但IC高而最大分位超额极低(均值0.5%)，属典型『高IC低超额』陷阱",
     "财务细分科目因子虽与收益相关但选股超额小，入池需先验证方向（可能需反向）与拥挤度，勿直接照搬",
     "基于财务类248因子均值IC 0.512 vs 均值超额0.5%的背离"),
    ("换手率类因子（情绪类各周期平均换手率）是少数『高IC+高超额+低换手』的优质alpha源",
     "重点研究情绪类换手率衍生因子（5/10/20/120日平均换手率等），其超额可达27%~50%且换手<0.1%",
     "基于性价比候选中换手率因子占比高且超额突出"),
]
for raw, hyp, rat in patterns:
    new_rows.append({
        "idea_id": next_id(),
        "source_type": "xuntou_kanban",
        "source_ref": "迅投因子看板(沪深300/近1年) 分类规律",
        "raw_idea": raw,
        "hypothesis": hyp,
        "rationale": rat,
        "confidence_seed": "medium",
        "status": "hypothesized",
        "created_at": "2026-08-20",
        "owner": "factor-scout",
        "linked_fcode": "",
        "review_cycle": "2027-02-16",
        "hit_status": "pending",
        "note": "分类规律总结，供灵感池后续挖掘方向参考；具体因子见同批候选条目",
        "fcode": "",
    })

# 去重（raw_idea 已存在则跳过）
existing = {r.get("raw_idea", "") for r in rows}
to_add = [r for r in new_rows if r["raw_idea"] not in existing]

with open(BACKLOG, "a", encoding="utf-8-sig", newline="") as f:
    w = csv.DictWriter(f, fieldnames=fieldnames)
    for r in to_add:
        w.writerow(r)

print(f"新增 {len(to_add)} 条（规律3 + 因子{len(to_add)-3}），跳过重复 {len(new_rows)-len(to_add)}")
for r in to_add:
    print(f"  {r['idea_id']}  [{r['source_ref'].split('/')[-1]}]  {r['raw_idea'][:60]}")
