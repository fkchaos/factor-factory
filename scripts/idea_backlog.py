"""灵感池 idea backlog — 轻量存储 + 论坛漏斗校验 + 复盘统计。

设计：仅依赖标准库，不涉及 baostock 缓存，可独立运行。
存储：research/idea_backlog.csv（首次 add 自动建表 + 写表头）。
字段与状态机见 docs/PLAN_IDEA_BACKLOG.md §3/§4。

核心函数（_ensure_file / allocate_idea_id / add_idea / load_backlog /
list_ideas / funnel_check / promote / to_pipeline / review_stats）均为纯函数，
I/O 通过 path 参数注入，便于单测。CLI 仅做参数解析与格式化输出。
"""
import csv
import os
from datetime import date, timedelta

# ---- 枚举（与 PLAN_IDEA_BACKLOG.md §3 对齐）----
SOURCE_TYPES = {"paper", "sell_side", "zoo", "forum", "observation", "logic", "chat", "ml_mining"}
CONFIDENCE_SEEDS = {"high", "mid", "low"}
STATUSES = {"backlog", "hypothesized", "in_pipeline", "validated", "rejected", "dormant"}
HIT_STATUS = {"pending", "hit", "miss"}
REVIEW_DAYS = 90  # 反馈闭环周期：3 个月后回看

FIELDS = [
    "idea_id", "source_type", "source_ref", "raw_idea", "hypothesis",
    "rationale", "confidence_seed", "status", "created_at", "owner",
    "linked_fcode", "review_cycle", "hit_status", "note",
]

BACKLOG_PATH = os.path.join("research", "idea_backlog.csv")


# ---- 存储层 ----
def _ensure_file(path: str) -> None:
    """首次写入建表 + 表头。已存在则不动。"""
    if not os.path.exists(path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", newline="", encoding="utf-8") as f:
            csv.DictWriter(f, fieldnames=FIELDS).writeheader()


def allocate_idea_id(path: str, today: date | None = None) -> str:
    """生成 iYYYYMMDD-NNN：当日序号递增，保证唯一。"""
    today = today or date.today()
    prefix = f"i{today.strftime('%Y%m%d')}-"
    rows = load_backlog(path)
    seq = 1
    for r in rows:
        if r["idea_id"].startswith(prefix):
            try:
                n = int(r["idea_id"].split("-")[-1])
                seq = max(seq, n + 1)
            except ValueError:
                continue
    return f"{prefix}{seq:03d}"


def load_backlog(path: str) -> list[dict]:
    """读全表为 dict 列表；文件不存在返回空表。"""
    if not os.path.exists(path):
        return []
    with open(path, "r", newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _append_row(path: str, row: dict) -> None:
    _ensure_file(path)
    with open(path, "a", newline="", encoding="utf-8") as f:
        csv.DictWriter(f, fieldnames=FIELDS).writerow(row)


# ---- 业务层 ----
def add_idea(
    path: str,
    source_type: str,
    raw_idea: str,
    hypothesis: str | None = None,
    rationale: str = "",
    source_ref: str = "",
    owner: str = "user",
    today: date | None = None,
) -> dict:
    """新增一个灵感。

    规则（论坛漏斗 §4）：
    - 任意来源：写了 hypothesis → 状态 hypothesized；没写 → 状态 backlog（留在池里不进流程）
    - forum 源：confidence_seed 强制 low（即使调用方传了别的）
    返回写入的整行。
    """
    today = today or date.today()
    if source_type not in SOURCE_TYPES:
        raise ValueError(f"source_type 非法: {source_type}，须 ∈ {sorted(SOURCE_TYPES)}")
    confidence_seed = "low" if source_type == "forum" else _default_seed(source_type)
    status = "hypothesized" if hypothesis and hypothesis.strip() else "backlog"
    review_cycle = today + timedelta(days=REVIEW_DAYS)
    row = {
        "idea_id": allocate_idea_id(path, today),
        "source_type": source_type,
        "source_ref": source_ref,
        "raw_idea": raw_idea,
        "hypothesis": (hypothesis or "").strip(),
        "rationale": rationale,
        "confidence_seed": confidence_seed,
        "status": status,
        "created_at": today.isoformat(),
        "owner": owner,
        "linked_fcode": "",
        "review_cycle": review_cycle.isoformat(),
        "hit_status": "pending",
        "note": "",
    }
    _append_row(path, row)
    return row


def _default_seed(source_type: str) -> str:
    """置信度预设（§3 confidence_seed 列）。"""
    if source_type in {"paper", "sell_side"}:
        return "high"
    if source_type in {"zoo", "logic", "ml_mining"}:
        return "mid"
    return "low"  # forum / observation / chat


def funnel_check(row: dict) -> tuple[bool, str]:
    """漏斗校验：能否从 backlog/hypothesized 进入流水线。

    返回 (ok, reason)。论坛源必须有可证伪假设才放行（§4 硬性闸门）。
    """
    if row["status"] in {"validated", "rejected", "dormant"}:
        return False, f"终态 {row['status']}，不可再进流程"
    if not row["hypothesis"].strip():
        return False, "缺少可证伪假设 hypothesis，留在 backlog"
    if row["source_type"] == "forum" and row["confidence_seed"] != "low":
        return False, "forum 源 confidence_seed 必须为 low"
    return True, "可进流水线"


def promote(path: str, idea_id: str, hypothesis: str, rationale: str = "") -> dict:
    """backlog → hypothesized：补写假设（论坛无假设则卡住）。"""
    rows = load_backlog(path)
    for r in rows:
        if r["idea_id"] == idea_id:
            if not hypothesis.strip():
                raise ValueError("promote 必须提供 hypothesis")
            r["hypothesis"] = hypothesis.strip()
            r["rationale"] = rationale or r["rationale"]
            r["status"] = "hypothesized"
            _rewrite(path, rows)
            return r
    raise KeyError(f"idea_id 不存在: {idea_id}")


def to_pipeline(path: str, idea_id: str, linked_fcode: str = "") -> dict:
    """hypothesized → in_pipeline：触发因子构造前的最终放行。"""
    rows = load_backlog(path)
    for r in rows:
        if r["idea_id"] == idea_id:
            ok, reason = funnel_check(r)
            if not ok:
                raise ValueError(f"未过漏斗: {reason}")
            r["status"] = "in_pipeline"
            if linked_fcode:
                r["linked_fcode"] = linked_fcode
            _rewrite(path, rows)
            return r
    raise KeyError(f"idea_id 不存在: {idea_id}")


def set_hit(path: str, idea_id: str, hit_status: str, note: str = "") -> dict:
    """复盘：标记 hit/miss（review_cycle 到期用）。"""
    if hit_status not in HIT_STATUS:
        raise ValueError(f"hit_status 非法: {hit_status}")
    rows = load_backlog(path)
    for r in rows:
        if r["idea_id"] == idea_id:
            r["hit_status"] = hit_status
            r["note"] = note
            _rewrite(path, rows)
            return r
    raise KeyError(f"idea_id 不存在: {idea_id}")


def _rewrite(path: str, rows: list[dict]) -> None:
    _ensure_file(path)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)


def list_ideas(path: str, status: str | None = None, source_type: str | None = None) -> list[dict]:
    rows = load_backlog(path)
    if status:
        rows = [r for r in rows if r["status"] == status]
    if source_type:
        rows = [r for r in rows if r["source_type"] == source_type]
    return rows


def review_stats(path: str) -> dict:
    """反馈闭环（§5）：按 source_type 统计命中率。

    仅统计 hit_status ∈ {hit, miss} 的行；未到期/pending 不参与。
    返回 {source_type: {n, hits, hit_rate}}。
    """
    rows = load_backlog(path)
    agg: dict[str, dict] = {}
    for r in rows:
        if r["hit_status"] not in {"hit", "miss"}:
            continue
        s = agg.setdefault(r["source_type"], {"n": 0, "hits": 0})
        s["n"] += 1
        if r["hit_status"] == "hit":
            s["hits"] += 1
    for s in agg.values():
        s["hit_rate"] = round(s["hits"] / s["n"], 3) if s["n"] else 0.0
    return agg


# ---- CLI ----
def _cmd_add(args):
    row = add_idea(
        args.path, args.source_type, args.raw_idea,
        hypothesis=args.hypothesis, rationale=args.rationale,
        source_ref=args.source_ref, owner=args.owner,
    )
    flag = "→ hypothesized（可进流程）" if row["status"] == "hypothesized" else "→ backlog（缺假设，留池）"
    print(f"[{row['idea_id']}] {row['source_type']}/{row['confidence_seed']} {flag}")
    return 0


def _cmd_list(args):
    rows = list_ideas(args.path, status=args.status, source_type=args.source_type)
    if not rows:
        print("(空)")
        return 0
    for r in rows:
        print(f"{r['idea_id']:18} {r['source_type']:12} {r['status']:12} {r['hypothesis'][:40]}")
    print(f"--- 共 {len(rows)} 条 ---")
    return 0


def _cmd_funnel(args):
    rows = list_ideas(args.path)
    stuck = [r for r in rows if not funnel_check(r)[0]]
    ok = [r for r in rows if funnel_check(r)[0]]
    print(f"可进流水线: {len(ok)}  卡在漏斗: {len(stuck)}")
    for r in stuck:
        _, reason = funnel_check(r)
        print(f"  [卡] {r['idea_id']:18} {r['source_type']:12} → {reason}")
    return 0


def _cmd_promote(args):
    r = promote(args.path, args.idea_id, args.hypothesis, rationale=args.rationale)
    print(f"[{r['idea_id']}] → {r['status']}")
    return 0


def _cmd_pipeline(args):
    r = to_pipeline(args.path, args.idea_id, linked_fcode=args.fcode)
    print(f"[{r['idea_id']}] → {r['status']} (fcode={r['linked_fcode'] or '-'})")
    return 0


def _cmd_review(args):
    stats = review_stats(args.path)
    if not stats:
        print("(暂无可复盘样本)")
        return 0
    print(f"{'source_type':14} {'n':>4} {'hits':>5} {'hit_rate':>9}")
    for k, v in sorted(stats.items(), key=lambda x: -x[1]["hit_rate"]):
        print(f"{k:14} {v['n']:>4} {v['hits']:>5} {v['hit_rate']:>9}")
    return 0


def main(argv=None):
    import argparse
    p = argparse.ArgumentParser(description="灵感池 idea backlog 管理")
    p.add_argument("--path", default=BACKLOG_PATH, help="CSV 路径（默认 research/idea_backlog.csv）")
    sub = p.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("add", help="新增灵感")
    a.add_argument("source_type", choices=sorted(SOURCE_TYPES))
    a.add_argument("raw_idea")
    a.add_argument("--hypothesis", default=None)
    a.add_argument("--rationale", default="")
    a.add_argument("--source-ref", default="")
    a.add_argument("--owner", default="user")
    a.set_defaults(func=_cmd_add)

    l = sub.add_parser("list", help="列出灵感")
    l.add_argument("--status", default=None, choices=sorted(STATUSES))
    l.add_argument("--source-type", default=None, choices=sorted(SOURCE_TYPES))
    l.set_defaults(func=_cmd_list)

    f = sub.add_parser("funnel", help="漏斗体检：谁可进流程/谁卡住")
    f.set_defaults(func=_cmd_funnel)

    pr = sub.add_parser("promote", help="backlog→hypothesized（补假设）")
    pr.add_argument("idea_id")
    pr.add_argument("hypothesis")
    pr.add_argument("--rationale", default="")
    pr.set_defaults(func=_cmd_promote)

    pl = sub.add_parser("pipeline", help="hypothesized→in_pipeline")
    pl.add_argument("idea_id")
    pl.add_argument("--fcode", default="")
    pl.set_defaults(func=_cmd_pipeline)

    rv = sub.add_parser("review", help="反馈闭环：各源命中率")
    rv.set_defaults(func=_cmd_review)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
