"""因子研发看板生成器 (Factor Factory Board)。

聚合三处状态为单一信息源，渲染成自包含、美观的 HTML 看板：
  1. 已交付因子  -> deliverables/factors/_REGISTRY.csv (f-code 包)
  2. 研究中因子  -> factors/*.py 里已实现但未交付的 Factor 类 + 灵感池里 in_pipeline 的条目
  3. 灵感池候选  -> research/idea_backlog.csv (backlog / hypothesized)
  4. 已拒绝      -> 灵感池里 status=rejected
  5. 信号线      -> deliverables/signals/_REGISTRY.csv (s-code 包) + signals/*.py 已实现的 Signal 类

用法：
  python scripts/factor_board.py [--out docs/factor_board.html]
纯标准库，无导入副作用（因子模块用 AST 静态扫描）。
"""
import argparse
import ast
import csv
import datetime as dt
import glob
import html
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FACTORS_DIR = os.path.join(ROOT, "factors")
SIGNALS_DIR = os.path.join(ROOT, "signals")
IDEA_CSV = os.path.join(ROOT, "research", "idea_backlog.csv")
REGISTRY_CANDIDATES = [
    # 实际交付注册表位置（factor-factory 把包放在 deliverables/factors/ 下）
    os.path.join(ROOT, "deliverables", "factors", "_REGISTRY.csv"),
    os.path.join(ROOT, "_REGISTRY.csv"),
]
SIGNAL_REGISTRY_CANDIDATES = [
    os.path.join(ROOT, "deliverables", "signals", "_REGISTRY.csv"),
    os.path.join(ROOT, "signals", "_REGISTRY.csv"),
]
CACHE_DIR = os.path.join(ROOT, ".cache", "baostock")
CHANGELOG = os.path.join(ROOT, "deliverables", "CHANGELOG.md")
HS1800_TARGET = 1572  # hs1800 = hs800 ∪ zz1000


# ---------------------------------------------------------------- 数据采集
def collect_implementations():
    """AST 扫描 factors/*.py，找出 Factor 子类与特征工厂函数。"""
    out = []
    for path in sorted(glob.glob(os.path.join(FACTORS_DIR, "*.py"))):
        mod = os.path.basename(path)[:-3]
        if mod in ("__init__", "interface"):
            continue
        try:
            tree = ast.parse(open(path, encoding="utf-8").read())
        except Exception:
            continue
        factor_classes = []
        feature_funcs = 0
        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                # 因子类多为鸭子类型（无显式基类），靠 register_factor() 注册；
                # 用「类名以 Factor 结尾」或「基类含 Factor」双判，覆盖两种风格。
                bases = {b.id if isinstance(b, ast.Name) else getattr(b, "attr", "") for b in node.bases}
                is_factor = node.name.endswith("Factor") or any("Factor" in b for b in bases)
                if is_factor:
                    fcode = None
                    doc = ast.get_docstring(node) or ""
                    for item in node.body:
                        if isinstance(item, ast.Assign):
                            for t in item.targets:
                                if isinstance(t, ast.Name) and t.id == "fcode":
                                    if isinstance(item.value, ast.Constant):
                                        fcode = item.value.value
                    factor_classes.append({
                        "name": node.name,
                        "doc": doc.strip().splitlines()[0] if doc.strip() else "",
                        "fcode": fcode,
                    })
            elif isinstance(node, ast.FunctionDef):
                # 特征工厂里的候选特征函数（返回 Series 的 cross-section 计算）
                if mod == "feature_factory":
                    feature_funcs += 1
        for fc in factor_classes:
            out.append({
                "kind": "factor",
                "name": fc["name"],
                "module": mod,
                "doc": fc["doc"],
                "fcode": fc["fcode"],
            })
        if mod == "feature_factory" and feature_funcs:
            out.append({
                "kind": "feature_factory",
                "name": "特征工厂 (FeatureFactory)",
                "module": mod,
                "doc": f"{feature_funcs} 个候选特征函数（动量/反转/波动/流动性/价格位置/微观结构/规模）",
                "fcode": None,
            })
    return out


def collect_ideas():
    if not os.path.exists(IDEA_CSV):
        return []
    with open(IDEA_CSV, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def collect_registry():
    for cand in REGISTRY_CANDIDATES:
        if os.path.exists(cand):
            with open(cand, encoding="utf-8") as f:
                return list(csv.DictReader(f))
    return []


def hs1800_progress():
    if not os.path.isdir(CACHE_DIR):
        return 0
    n = sum(1 for _ in glob.glob(os.path.join(CACHE_DIR, "*.parquet")))
    return n


def changelog_unreleased_count():
    """CHANGELOG [Unreleased] 段下的待发布条目数（非空非标题行）。"""
    if not os.path.exists(CHANGELOG):
        return 0
    n = 0
    in_section = False
    with open(CHANGELOG, encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            if line.startswith("## "):
                in_section = line.strip().startswith("## [Unreleased]")
                continue
            if in_section:
                s = line.strip()
                if s and not s.startswith("#"):
                    n += 1
    return n


# ---------------------------------------------------------------- 信号线采集
def collect_signal_implementations():
    """AST 扫描 signals/*.py，找出 Signal 子类（鸭子类型，类名以 Signal 结尾）。"""
    out = []
    if not os.path.isdir(SIGNALS_DIR):
        return out
    for path in sorted(glob.glob(os.path.join(SIGNALS_DIR, "*.py"))):
        mod = os.path.basename(path)[:-3]
        if mod in ("__init__", "interface"):
            continue
        try:
            tree = ast.parse(open(path, encoding="utf-8").read())
        except Exception:
            continue
        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                bases = {b.id if isinstance(b, ast.Name) else getattr(b, "attr", "") for b in node.bases}
                is_signal = node.name.endswith("Signal") or any("Signal" in b for b in bases)
                if not is_signal:
                    continue
                scode = None
                doc = ast.get_docstring(node) or ""
                for item in node.body:
                    if isinstance(item, ast.Assign):
                        for t in item.targets:
                            if isinstance(t, ast.Name) and t.id == "scode":
                                if isinstance(item.value, ast.Constant):
                                    scode = item.value.value
                out.append({
                    "kind": "signal",
                    "name": node.name,
                    "module": mod,
                    "doc": doc.strip().splitlines()[0] if doc.strip() else "",
                    "scode": scode,
                })
    return out


def collect_signal_registry():
    for cand in SIGNAL_REGISTRY_CANDIDATES:
        if os.path.exists(cand):
            with open(cand, encoding="utf-8") as f:
                return list(csv.DictReader(f))
    return []


def collect_strategy_export():
    """扫描 deliverables/strategy_export/*.json（策略组阶段 0 输入包，机器可读真源）。"""
    d = os.path.join(ROOT, "deliverables", "strategy_export")
    out = []
    if not os.path.isdir(d):
        return out
    desc = {
        "stock_factors.json": "横截面选股因子（f-code）",
        "timing_signals.json": "市场级择时信号（s-code，含 exec_lag 钢印）",
        "risk_params.json": "风控参数（策略层范围，本厂占位）",
    }
    array_key = {
        "stock_factors.json": "factors",
        "timing_signals.json": "signals",
        "risk_params.json": "params",
    }
    for fn in sorted(os.listdir(d)):
        if not fn.endswith(".json"):
            continue
        try:
            with open(os.path.join(d, fn), encoding="utf-8") as f:
                data = json.load(f)
            n = len(data.get(array_key.get(fn, ""), []))
            generated = (data.get("generated") or "").split(" ")[0]
        except Exception:
            n, generated = "?", ""
        out.append({
            "stage": "strategy_export",
            "title": fn,
            "code": fn.replace(".json", ""),
            "source": "deliverables/strategy_export/",
            "detail": f"{n} 条 · {desc.get(fn, '')}",
            "meta": f"generated {generated} ｜ 机器可读真源",
        })
    return out


def collect_universe_matrix():
    """扫描 deliverables/universe_matrix/*.csv，按日期聚合为矩阵快照批次。"""
    d = os.path.join(ROOT, "deliverables", "universe_matrix")
    out = []
    if not os.path.isdir(d):
        return out
    batches = {}
    for fn in sorted(os.listdir(d)):
        if not fn.endswith(".csv"):
            continue
        date = fn.rsplit("_", 1)[1][:-4]  # ic_matrix_2026-08-06.csv -> 2026-08-06
        batches.setdefault(date, []).append(fn)
    today = dt.date.today()
    for date in sorted(batches, reverse=True):
        kinds = sorted(fn.split("_")[0] for fn in batches[date])
        days = (today - dt.date.fromisoformat(date)).days
        stale = "⚠️ " if days > 3 else ""
        out.append({
            "stage": "universe_matrix",
            "title": f"矩阵快照 {date}",
            "code": date,
            "source": "deliverables/universe_matrix/",
            "detail": " · ".join(kinds) + " 全因子矩阵（冗余/ICIR/过拟合）",
            "meta": f"{stale}{len(batches[date])} 件 · {days} 天前",
        })
    return out


# ---------------------------------------------------------------- 状态归类
def build_rows(impls, ideas, registry):
    delivered_codes = {r.get("fcode") for r in registry if r.get("fcode")}
    delivered_names = {r.get("name") for r in registry if r.get("name")}
    rows = []

    # 1) 已交付
    for r in registry:
        rows.append({
            "stage": "delivered",
            "title": r.get("name") or r.get("fcode") or "?",
            "code": r.get("fcode") or "",
            "source": f"registry / {r.get('type','')}",
            "detail": r.get("rationale") or r.get("note") or "",
            "meta": r.get("delivered_at") or r.get("updated") or "",
        })

    # 2) 研究中：已实现但未交付的因子
    for it in impls:
        if it["fcode"] in delivered_codes or it["name"] in delivered_names:
            continue  # 已交付优先，不重复
        if it["kind"] == "feature_factory":
            stage = "researching"
            code = "特征库"
            detail = it["doc"]
        else:
            stage = "researching"
            code = it["fcode"] or "待分配 f-code"
            detail = it["doc"]
        rows.append({
            "stage": stage,
            "title": it["name"],
            "code": code,
            "source": f"factors/{it['module']}.py",
            "detail": detail,
            "meta": "已实现 · 待交付",
        })

    # 3) 灵感池 / 研究中(in_pipeline)
    # 2026-08-07 修复：in_pipeline 灵感若其 fcode 已有实现类或已交付，则该灵感已晋升，
    # 不再单列一行，否则看板同一因子重复出现两次（如 f0003a 组合因子）。
    impl_codes = {it["fcode"] for it in impls if it.get("fcode")}
    for r in ideas:
        status = (r.get("status") or "backlog").strip()
        if status == "rejected":
            continue  # 单独归类
        idea_code = r.get("fcode")
        if status == "in_pipeline" and idea_code and (
            idea_code in impl_codes or idea_code in delivered_codes
        ):
            continue  # 已晋升为实现/交付，避免重复计数
        st = r.get("source_type", "")
        hypo = (r.get("hypothesis") or "").strip()
        if status == "in_pipeline":
            stage = "researching"
            code = r.get("fcode") or "in_pipeline"
            detail = hypo
            meta = f"管线中 · seed={r.get('confidence_seed','')}"
        else:
            stage = "idea"
            code = r.get("idea_id", "")
            detail = hypo or (r.get("raw_idea") or "")
            meta = f"{st} · seed={r.get('confidence_seed','')}"
        rows.append({
            "stage": stage,
            "title": (r.get("raw_idea") or code)[:48],
            "code": code,
            "source": f"{st} / {r.get('source_ref','')[:40]}",
            "detail": detail,
            "meta": meta,
        })

    # 4) 已拒绝
    for r in ideas:
        if (r.get("status") or "").strip() == "rejected":
            rows.append({
                "stage": "rejected",
                "title": (r.get("raw_idea") or r.get("idea_id","")).strip()[:48],
                "code": r.get("idea_id", ""),
                "source": f"{r.get('source_type','')}",
                "detail": (r.get("hypothesis") or ""),
                "meta": f"拒绝原因: {r.get('reject_reason','')}",
            })

    # 5) 信号线：已交付（deliverables/signals/_REGISTRY.csv）
    sig_registry = collect_signal_registry()
    sig_impls = collect_signal_implementations()
    delivered_scodes = {r.get("scode") for r in sig_registry if r.get("scode")}
    for r in sig_registry:
        rows.append({
            "stage": "sig_delivered",
            "title": r.get("name") or r.get("scode") or "?",
            "code": r.get("scode") or "",
            "source": f"sig-registry / {r.get('type','')}",
            "detail": r.get("note") or "",
            "meta": r.get("created") or "",
        })
    # 6) 信号线：研究中（已实现未交付的 Signal 类）
    for it in sig_impls:
        if it["scode"] in delivered_scodes:
            continue
        rows.append({
            "stage": "sig_researching",
            "title": it["name"],
            "code": it["scode"] or "待分配 s-code",
            "source": f"signals/{it['module']}.py",
            "detail": it["doc"],
            "meta": "已实现 · 待交付",
        })

    # 7) 策略导出（strategy_export）：JSON 输入包
    rows.extend(collect_strategy_export())
    # 8) 跨因子矩阵（universe_matrix）：按日快照
    rows.extend(collect_universe_matrix())
    return rows


# ---------------------------------------------------------------- 渲染
STAGE_META = {
    "delivered":  ("因子已交付",   "#16a34a", "f-code 包已产出，含说明文档+相关性+回测"),
    "researching":("因子研究中",   "#2563eb", "代码已实现 / 已进入管线，等待或正在检验"),
    "idea":       ("灵感池",   "#d97706", "候选假设，待 promote 进管线"),
    "rejected":   ("已拒绝",   "#9333ea", "检验未过或被证伪"),
    "sig_delivered":("信号已交付", "#16a34a", "s-code 包已产出，含状态定义+叠加改善"),
    "sig_researching":("信号研究中", "#2563eb", "Signal 类已实现，等待或正在检验"),
    "strategy_export":("策略导出", "#0d9488", "附属：机器可读发货形态（不另立编号）"),
    "universe_matrix":("跨因子矩阵", "#ea580c", "附属：跨池检验记录（不另立编号）"),
}

# 2026-08-18 主从架构（用户决策）：核心交付=因子/信号（带编号）；
# strategy_export / universe_matrix 是附属视图，tile 区拆出、section 标题加"附属 · "前缀。
MAIN_STAGES = ["delivered", "researching", "idea", "rejected",
               "sig_delivered", "sig_researching"]
ATTACH_STAGES = ["strategy_export", "universe_matrix"]


def esc(s):
    return html.escape(str(s or ""), quote=True)


def render_html(rows, generated, unreleased=0):
    counts = {k: 0 for k in STAGE_META}
    for r in rows:
        counts[r["stage"]] = counts.get(r["stage"], 0) + 1

    def _tile_html(k, lbl, c, n, attach=False):
        cls = ' tile-a' if attach else ''
        return (
            f'<div class="tile{cls}"><div class="tile-n" style="color:{c}">{n}</div>'
            f'<div class="tile-l">{lbl}</div>'
            f'<div class="bar"><i style="width:{min(100, n*12)}%"></i></div></div>'
        )

    tiles_main = "".join(_tile_html(k, *STAGE_META[k][:2], counts[k]) for k in MAIN_STAGES)
    tiles_attach = "".join(
        _tile_html(k, *STAGE_META[k][:2], counts[k], attach=True) for k in ATTACH_STAGES
    )

    sections = ""
    order = MAIN_STAGES + ATTACH_STAGES
    for st in order:
        srows = [r for r in rows if r["stage"] == st]
        if not srows and st == "delivered":
            # 已交付为空时给友好提示
            label, color, hint = STAGE_META[st]
            sections += (
                f'<section><h2 class="h2"><span class="dot" style="background:{color}"></span>{label} '
                f'<span class="cnt">{counts[st]}</span></h2>'
                f'<p class="empty">暂无已交付因子包。交付流水线产出 f0001a / f0002a 等后，'
                f'看板会自动出现在此区。</p></section>'
            )
            continue
        if not srows:
            continue
        label, color, hint = STAGE_META[st]
        prefix = "附属 · " if st in ATTACH_STAGES else ""
        cards = ""
        for r in srows:
            cards += (
                f'<div class="card" style="border-left-color:{color}">'
                f'<div class="card-h"><span class="badge" style="background:{color}">{esc(r["code"])}</span>'
                f'<span class="ttl">{esc(r["title"])}</span></div>'
                f'<div class="src">{esc(r["source"])}</div>'
                f'<div class="det">{esc(r["detail"])}</div>'
                f'<div class="meta">{esc(r["meta"])}</div>'
                f'</div>'
            )
        sections += (
            f'<section><h2 class="h2"><span class="dot" style="background:{color}"></span>{prefix}{label} '
            f'<span class="cnt">{counts[st]}</span></h2>'
            f'<p class="hint">{esc(hint)}</p><div class="grid">{cards}</div></section>'
        )

    legend = "".join(
        f'<span><span class="dot" style="background:{c}"></span>'
        f'{"附属 · " if k in ATTACH_STAGES else ""}{lbl}</span>'
        for k, (lbl, c, _) in STAGE_META.items()
    )

    # 2026-08-18：缓存进度（hs1800）已从看板移除，pct/hs 渲染全部删除，仅 console 摘要保留。
    if unreleased:
        unreleased_html = (
            f'<div class="unreleased">📦 待发布交付物（CHANGELOG [Unreleased]）：'
            f'<span class="n">{unreleased}</span> 项</div>'
        )
    else:
        unreleased_html = (
            f'<div class="unreleased ok">✅ CHANGELOG [Unreleased] 已清空，交付物均已归档</div>'
        )

    # 2026-08-18：交付物查看入口从 footer 提升到 hero（红框位置），重跑不再丢。
    # 2026-08-18 15:2x：补 strategy_export（组合导出）+ universe_matrix（跨因子矩阵）两个入口。
    # 2026-08-18 15:3x：每条一句一行，避免长句折行难看。
    # 2026-08-18 15:5x：用户定调主从架构——核心交付只有因子/信号（带编号），
    #   策略导出与跨因子矩阵是附属视图（发货形态/检验记录），加说明小字并标注"附属"。
    deliv_html = (
        '<div class="deliv-hint">📦 交付物查看'
        '<div class="note">核心交付 = 因子 / 信号包（f-code / s-code，带编号）；'
        '策略导出与跨因子矩阵为其附属视图（机器可读发货形态 / 跨池检验记录），不另立编号</div>'
        '<div class="l">因子明细 <code>deliverables/factors/&lt;fcode&gt;/card.md</code></div>'
        '<div class="l">信号明细 <code>deliverables/signals/&lt;scode&gt;/card.md</code></div>'
        '<div class="l">附属 · 机器可读发货形态 <code>deliverables/strategy_export/*.json</code></div>'
        '<div class="l">附属 · 跨池检验记录 <code>deliverables/universe_matrix/</code></div>'
        '<div class="l">完整查阅地图见 '
        '<a href="https://github.com/fkchaos/factor-factory/blob/main/docs/DELIVERABLES.md">docs/DELIVERABLES.md</a></div>'
        '</div>'
    )

    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>因子研发看板 · Factor Factory Board</title>
<style>
:root{{--bg:#eef1f8;--card:#ffffff;--ink:#1f2330;--muted:#6b7280;
 --line:#e6e9f0;--brand:#4f46e5;--brand2:#7c3aed}}
*{{box-sizing:border-box}}
body{{margin:0;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;
 background:var(--bg);color:var(--ink);line-height:1.65}}
.wrap{{max-width:1080px;margin:0 auto;padding:0 24px 56px}}
.hero{{background:linear-gradient(120deg,#4f46e5 0%,#7c3aed 55%,#9333ea 100%);color:#fff;
 padding:34px 24px 30px;box-shadow:0 6px 24px rgba(79,70,229,.25)}}
.hero .inner{{max-width:1080px;margin:0 auto}}
.hero h1{{margin:0;font-size:25px;letter-spacing:.4px;display:flex;align-items:center;gap:10px}}
.hero .logo{{font-size:26px}}
.hero .sub{{margin-top:8px;font-size:13px;color:rgba(255,255,255,.9)}}
.unreleased{{display:inline-flex;align-items:center;gap:7px;background:rgba(255,255,255,.16);
 border:1px solid rgba(255,255,255,.32);color:#fff;font-size:12.5px;font-weight:600;
 padding:5px 13px;border-radius:20px;margin-top:14px}}
.unreleased.ok{{background:rgba(255,255,255,.12);border-style:dashed}}
.unreleased .n{{background:#fff;color:var(--brand);border-radius:12px;padding:0 8px;font-size:12px;font-weight:800}}
.deliv-hint{{margin-top:12px;background:rgba(255,255,255,.14);border:1px solid rgba(255,255,255,.30);
 color:#fff;font-size:14px;padding:8px 14px;border-radius:10px;line-height:1.85;word-break:break-all}}
.deliv-hint code{{background:rgba(255,255,255,.20);padding:1px 7px;border-radius:5px;font-size:13px;font-weight:500}}
.deliv-hint .l{{margin-top:2px}}
.deliv-hint .note{{margin-top:6px;font-size:12px;color:rgba(255,255,255,.78);line-height:1.6}}
.deliv-hint a{{color:#fff;text-decoration:underline;font-weight:600}}
.tiles{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:14px;margin:24px 0}}
.tile{{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:16px 18px;
 box-shadow:0 2px 8px rgba(31,35,48,.04);transition:transform .15s,box-shadow .15s}}
.tile:hover{{transform:translateY(-3px);box-shadow:0 8px 20px rgba(31,35,48,.08)}}
.tile-n{{font-size:30px;font-weight:800;line-height:1}}
.tile-l{{font-size:13px;color:var(--muted);margin-top:6px}}
.tile .bar{{height:5px;border-radius:4px;background:#eef0f6;margin-top:12px;overflow:hidden}}
.tile .bar>i{{display:block;height:100%;background:linear-gradient(90deg,#6366f1,#a855f7)}}
.attach-head{{font-size:12.5px;color:var(--muted);font-weight:600;margin:22px 0 -10px}}
.tiles.attach{{margin-top:14px}}
.tiles.attach .tile{{background:rgba(255,255,255,.55);border:1px dashed var(--line);box-shadow:none}}
.tiles.attach .tile:hover{{transform:none;box-shadow:none}}
.tiles.attach .tile-n{{font-size:20px}}
.tiles.attach .tile-l{{font-size:12px}}
section{{margin:30px 0 8px}}
.h2{{font-size:18px;font-weight:700;display:flex;align-items:center;gap:9px;margin:0 0 4px}}
.dot{{width:11px;height:11px;border-radius:50%;display:inline-block;flex:none}}
.cnt{{background:#eef0f6;color:var(--muted);border-radius:20px;font-size:12px;padding:1px 10px;font-weight:600}}
.hint{{color:var(--muted);font-size:12.5px;margin:2px 0 14px}}
.empty{{background:var(--card);border:1px dashed var(--line);border-radius:12px;padding:16px 18px;color:var(--muted);font-size:13px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:14px}}
.card{{background:var(--card);border:1px solid var(--line);border-left:4px solid var(--line);
 border-radius:12px;padding:15px 16px;box-shadow:0 2px 8px rgba(31,35,48,.04);transition:transform .15s,box-shadow .15s}}
.card:hover{{transform:translateY(-3px);box-shadow:0 10px 22px rgba(31,35,48,.09)}}
.card-h{{display:flex;align-items:center;gap:9px;margin-bottom:7px;flex-wrap:wrap}}
.badge{{color:#fff;font-size:11px;font-weight:700;padding:3px 9px;border-radius:7px;white-space:nowrap;letter-spacing:.3px}}
.ttl{{font-weight:700;font-size:14.5px}}
.src{{color:var(--muted);font-size:11px;margin-bottom:7px;word-break:break-all}}
.det{{font-size:13px;margin-bottom:7px;color:#374151}}
.meta{{color:#9333ea;font-size:11px;font-weight:500}}
.legend{{display:flex;flex-wrap:wrap;gap:16px;margin:20px 0 0;font-size:12.5px;color:var(--muted)}}
.legend span{{display:inline-flex;align-items:center;gap:6px}}
footer{{margin-top:40px;border-top:1px solid var(--line);padding-top:16px;color:#9aa1ad;font-size:11.5px;line-height:1.7}}
</style></head><body>
<div class="hero"><div class="inner">
<h1><span class="logo">🧪</span>因子研发看板 · Factor Factory Board</h1>
<div class="sub">生成时间：{generated} ｜ 数据源：factors/ + research/idea_backlog.csv + deliverables/*/_REGISTRY.csv</div>
{unreleased_html}
{deliv_html}
</div></div>
<div class="wrap">
<div class="tiles">{tiles_main}</div>
<div class="attach-head">附属视图 · 无编号（机器可读发货形态 / 跨池检验记录）</div>
<div class="tiles attach">{tiles_attach}</div>
{sections}
<div class="legend">{legend}</div>
<footer>双事业部：横截面因子线（f-code，选股打分）+ 时序信号线（s-code，市场状态 overlay）。
生命周期：灵感池 → 研究中 → 已交付。｜ 本看板由 <code>scripts/factor_board.py</code> 生成，重跑即刷新。
</footer>
</div></body></html>"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(ROOT, "docs", "factor_board.html"))
    args = ap.parse_args()

    impls = collect_implementations()
    ideas = collect_ideas()
    registry = collect_registry()
    rows = build_rows(impls, ideas, registry)
    generated = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    hs_n = hs1800_progress()
    unreleased = changelog_unreleased_count()

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    html_out = render_html(rows, generated, unreleased)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(html_out)

    # 控制台摘要
    c = {k: 0 for k in STAGE_META}
    for r in rows:
        c[r["stage"]] += 1
    print(f"[factor_board] 已生成: {args.out}")
    print(f"  因子 已交付={c['delivered']} 研究中={c['researching']} 灵感池={c['idea']} 已拒绝={c['rejected']}")
    print(f"  信号 已交付={c['sig_delivered']} 研究中={c['sig_researching']}")
    print(f"  hs1800 缓存: {hs_n}/{HS1800_TARGET}")
    print(f"  CHANGELOG [Unreleased]: {unreleased} 项")
    return 0


if __name__ == "__main__":
    sys.exit(main())
