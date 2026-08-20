#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
迅投因子看板 · 分类合并与规律分析
- 解析 cat_raw/*.json（每段为拼接的 JSON 数组）
- 按分类打标签，合并为单一数据集
- 输出：
    1) merged_by_category.csv        带分类标签的全量因子
    2) category_summary.csv          每类统计（数量/均值 IC/IR/超额/换手）
    3) top_ic.csv / top_ir.csv       全局 Top 因子
    4) patterns_report.md            规律小结 + 灵感候选建议
用法：python3 merge_and_analyze.py
"""
import json, os, glob, re, statistics as st
from collections import defaultdict
import importlib.util

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "cat_raw")

# 真实分类名（与看板一致）；文件名中 / : \ 已被 tr 替换为 _
REAL_CATS = ["基础科目及衍生类因子", "情绪类因子", "质量类因子", "成长类因子",
             "每股指标因子", "风险/风格类因子", "技术指标因子", "动量类因子", "财务类因子"]
def sanitize(s):
    return s.replace("/", "_").replace(":", "_").replace("\\", "_")
# 文件名(无扩展) -> 真实分类名
FILE_TO_CAT = {sanitize(c): c for c in REAL_CATS}

# 复用 count_rows.py 的健壮解析（兼容裸数组拼接 / agent-browser 引号字符串两种格式）
spec = importlib.util.spec_from_file_location("count_rows", os.path.join(HERE, "count_rows.py"))
cr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cr)

def parse_concat(path):
    """解析单个分类原始 json，返回行 list（每行为 8 列）"""
    txt = open(path, encoding="utf-8").read()
    return cr.load_rows(txt)

def fnum(s):
    if s is None:
        return None
    s = str(s).strip().replace("%", "").replace(",", "")
    try:
        return float(s)
    except ValueError:
        return None

# 解析全部分类
cat_files = sorted(glob.glob(os.path.join(RAW, "*.json")))
records = []  # {name, category, seq, min_ret, max_ret, min_turn, max_turn, ic, ir}
seen = defaultdict(list)  # name -> [categories]
parse_fail = []

for fp in cat_files:
    base = os.path.splitext(os.path.basename(fp))[0]
    cat = FILE_TO_CAT.get(base, base)  # 还原真实分类名（如 风险_风格 -> 风险/风格）
    raw = parse_concat(fp)
    if not raw:
        parse_fail.append((cat, "empty"))
        continue
    cnt = 0
    for row in raw:
        # row: [序号, 名称, 最小分位超额年化, 最大分位超额年化, 最小分位换手, 最大分位换手, IC, IR]
        if not isinstance(row, list) or len(row) < 8:
            continue
        seq, name = row[0], row[1]
        if not name:
            continue
        rec = {
            "category": cat,
            "seq": seq,
            "name": name,
            "min_ret": fnum(row[2]),
            "max_ret": fnum(row[3]),
            "min_turn": fnum(row[4]),
            "max_turn": fnum(row[5]),
            "ic": fnum(row[6]),
            "ir": fnum(row[7]),
        }
        records.append(rec)
        seen[name].append(cat)
        cnt += 1
    print(f"  [解析] {cat}: {cnt} 行")

# 重复归属检查
dups = {k: v for k, v in seen.items() if len(v) > 1}
if dups:
    print(f"  ⚠️ {len(dups)} 个因子出现在多分类：{list(dups.items())[:5]}")

print(f"  合计 {len(records)} 条记录，{len(seen)} 个唯一因子名")

# ---- 1) merged_by_category.csv ----
merged_path = os.path.join(HERE, "merged_by_category.csv")
with open(merged_path, "w", encoding="utf-8-sig") as f:
    f.write("分类,序号,因子名称,最小分位超额年化,最大分位超额年化,最小分位换手,最大分位换手,IC,IR\n")
    for r in records:
        f.write(f"{r['category']},{r['seq']},{r['name']},{r['min_ret']},{r['max_ret']},{r['min_turn']},{r['max_turn']},{r['ic']},{r['ir']}\n")
print(f"  写出 {merged_path}")

# ---- 2) category_summary.csv ----
summary = []
for cat in sorted(set(r["category"] for r in records)):
    rs = [r for r in records if r["category"] == cat]
    ics = [r["ic"] for r in rs if r["ic"] is not None]
    irs = [r["ir"] for r in rs if r["ir"] is not None]
    mret = [r["max_ret"] for r in rs if r["max_ret"] is not None]
    mtur = [r["max_turn"] for r in rs if r["max_turn"] is not None]
    summary.append({
        "category": cat,
        "n": len(rs),
        "mean_ic": round(st.mean(ics), 4) if ics else None,
        "median_ic": round(st.median(ics), 4) if ics else None,
        "mean_ir": round(st.mean(irs), 4) if irs else None,
        "mean_max_ret": round(st.mean(mret), 2) if mret else None,
        "mean_max_turn": round(st.mean(mtur), 2) if mtur else None,
    })
summary_path = os.path.join(HERE, "category_summary.csv")
with open(summary_path, "w", encoding="utf-8-sig") as f:
    f.write("分类,因子数,均值IC,中位数IC,均值IR,均值最大分位超额年化,均值最大分位换手\n")
    for s in summary:
        f.write(f"{s['category']},{s['n']},{s['mean_ic']},{s['median_ic']},{s['mean_ir']},{s['mean_max_ret']},{s['mean_max_turn']}\n")
print(f"  写出 {summary_path}")

# ---- 3) Top IC / Top IR ----
def topn(key, n=20):
    valid = [r for r in records if r[key] is not None]
    valid.sort(key=lambda x: x[key], reverse=True)
    return valid[:n]

top_ic = topn("ic")
top_ir = topn("ir")

topic_path = os.path.join(HERE, "top_ic.csv")
with open(topic_path, "w", encoding="utf-8-sig") as f:
    f.write("排名,分类,因子名称,IC,IR,最大分位超额年化,最大分位换手\n")
    for i, r in enumerate(top_ic, 1):
        f.write(f"{i},{r['category']},{r['name']},{r['ic']},{r['ir']},{r['max_ret']},{r['max_turn']}\n")
topir_path = os.path.join(HERE, "top_ir.csv")
with open(topir_path, "w", encoding="utf-8-sig") as f:
    f.write("排名,分类,因子名称,IR,IC,最大分位超额年化,最大分位换手\n")
    for i, r in enumerate(top_ir, 1):
        f.write(f"{i},{r['category']},{r['name']},{r['ir']},{r['ic']},{r['max_ret']},{r['max_turn']}\n")
print(f"  写出 {topic_path}, {topir_path}")

# ---- 4) patterns_report.md ----
# 规律：按均值 IC 排序的分类；低换手高超额的因子；IC 与超额背离的
summary_sorted = sorted(summary, key=lambda s: (s["mean_ic"] or 0), reverse=True)
low_turn_high_ret = [r for r in records if r["max_turn"] is not None and r["max_turn"] <= 1.0 and r["max_ret"] is not None and r["max_ret"] >= 15.0]
# IC 高但超额低的（可能被 turnover 拖累 / 噪音）
ic_high_ret_low = [r for r in records if r["ic"] is not None and r["ic"] >= 0.6 and r["max_ret"] is not None and r["max_ret"] < 5.0]

lines = []
lines.append("# 迅投因子看板 · 分类规律与灵感候选建议\n")
lines.append(f"> 数据来源：迅投因子看板（沪深300 / 近1年 / 全分类），共 {len(seen)} 个因子，{len(records)} 条分类记录。\n")
lines.append("> ⚠️ IC/IR 口径提示：迅投看板 IC 量级约 0.2~0.99（非 RankIC），与我方 RankIC 0.01~0.05 不可直接对比；下方仅作「相对强弱排序」与「灵感来源」，不构成我方因子 IC 声明。\n")

lines.append("## 一、各分类平均 IC 排序（强弱分布）\n")
lines.append("| 分类 | 因子数 | 均值IC | 中位数IC | 均值IR | 均值最大分位超额% | 均值最大分位换手% |")
lines.append("|---|---|---|---|---|---|---|")
for s in summary_sorted:
    lines.append(f"| {s['category']} | {s['n']} | {s['mean_ic']} | {s['median_ic']} | {s['mean_ir']} | {s['mean_max_ret']} | {s['mean_max_turn']} |")

lines.append("\n## 二、规律解读\n")
lines.append("- **最强分类**（均值IC 最高）：`%s`（%.3f）；**最弱分类**：`%s`（%.3f）。" % (
    summary_sorted[0]["category"], summary_sorted[0]["mean_ic"] or 0,
    summary_sorted[-1]["category"], summary_sorted[-1]["mean_ic"] or 0))
lines.append("- 全市场因子 IC 分布：均值IC 中位数约 %.3f，说明**质量/情绪/动量类因子整体信息含量高于基础科目类**的假设需以实际数据为准。" % (
    st.median([s["mean_ic"] for s in summary if s["mean_ic"] is not None])))
lines.append(f"- 换手维度：最大分位换手普遍在 0~5% 区间，低换手（≤1%）且高超额（≥15%）的因子共 {len(low_turn_high_ret)} 个，是「性价比」优先候选。")
if ic_high_ret_low:
    lines.append(f"- ⚠️ IC 高（≥0.6）但最大分位超额低（<5%）的因子有 {len(ic_high_ret_low)} 个，可能受高换手或方向不稳定拖累，入池时需重点验证方向。")

lines.append("\n## 三、低换手·高超额「性价比」候选（≤1% 换手且 ≥15% 超额）\n")
lines.append("| 分类 | 因子名称 | IC | IR | 最大分位超额% | 最大分位换手% |")
lines.append("|---|---|---|---|---|---|")
for r in sorted(low_turn_high_ret, key=lambda x: (x["ic"] or 0), reverse=True)[:30]:
    lines.append(f"| {r['category']} | {r['name']} | {r['ic']} | {r['ir']} | {r['max_ret']} | {r['max_turn']} |")

lines.append("\n## 四、全局 Top 20 IC 因子（灵感强信号）\n")
lines.append("| 排名 | 分类 | 因子名称 | IC | IR | 最大分位超额% |")
lines.append("|---|---|---|---|---|---|")
for i, r in enumerate(top_ic[:20], 1):
    lines.append(f"| {i} | {r['category']} | {r['name']} | {r['ic']} | {r['ir']} | {r['max_ret']} |")

lines.append("\n## 五、全局 Top 20 IR 因子（稳定性强信号）\n")
lines.append("| 排名 | 分类 | 因子名称 | IR | IC | 最大分位超额% |")
lines.append("|---|---|---|---|---|---|")
for i, r in enumerate(top_ir[:20], 1):
    lines.append(f"| {i} | {r['category']} | {r['name']} | {r['ir']} | {r['ic']} | {r['max_ret']} |")

report_path = os.path.join(HERE, "patterns_report.md")
with open(report_path, "w", encoding="utf-8") as f:
    f.write("\n".join(lines) + "\n")
print(f"  写出 {report_path}")
print("完成。")
