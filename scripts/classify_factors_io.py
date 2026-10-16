"""把注册因子按「是否需要联网取外部数据」分类（2026-10-12）。

背景：P4 矩阵 672 单元跑了 43 小时只落盘 84 个，根因是**财报类因子在大池冷启动联网**，
而 16 路并发把数据源账号打封了（WinError 10054 刷了 9 万次）。
所以要先把因子分成两类分别调度：
  - offline：只用本地价量面板 / 本地 parquet 外部面板（龙虎榜、两融）→ 纯 CPU，可高并发；
  - online：走 PitFinancialsService（AkShare 东财三表）/ 业绩预告 / 需要联网，必须低并发 + 先预热。

判据（静态扫描模块源码里的联网入口关键字，宁可错杀不可漏判，
因为漏一个 online 因子到高并发批次 = 再把数据源打封 = 整批白跑）：
    pit_fundamentals / PitFinancialsService / get_pit_financials /
    akshare / stock_ / baostock / bs.query

用法：
    python scripts/classify_factors_io.py            # 打印两类名单与统计
    python scripts/classify_factors_io.py --emit-csv # 额外落 .cache/factor_io_class.csv
"""
from __future__ import annotations

import argparse
import ast
import inspect
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# 联网/外部取数入口关键字：命中任一即判为 online
# （2026-10-13 收紧：旧判据 `all(x for _ in [0])` 是恒真式写法错误，
#   导致整段过滤失效；hs800 批次因此混入真联网因子，刷 1080 次 WinError。）
ONLINE_KEYS = (
    "pit_fundamentals", "PitFinancialsService", "get_pit_financials",
    "get indust", "akshare", "ak.stock_", "stock_financial",
    "bs.query", "baostock",
)
# 模块里出现「本地 parquet 面板」字样时，允许它同时提到 akshare（多为注释/构建说明）
LOCAL_CACHE_KEYS = ("moneyflow_cache", "lhb_", "margin_balance_panel")


def _import_block(src: str) -> str:
    """只取 import 行，避免注释/docstring 里的 akshare 字样误判。"""
    return "\n".join(l for l in src.splitlines() if re.match(r"\s*(from|import)\s", l))


def _code_tokens(src: str) -> str:
    """把源码解析成**代码词元**（标识符 / 属性名 / 导入模块名），丢掉注释与 docstring。

    🔴 修正（2026-10-16）：旧版正文回退判定用 `k in src` 直接扫原始源码，
    docstring 与注释里的数据源名字也算命中 → 误判。实测 `turnover_excess_group`
    的 docstring 里有一句「当前 baostock 面板契约（open/high/…）不含行业分类列」，
    它其实只 import 了 numpy/pandas/factors.interface，是**纯离线**因子，
    却被判成 online → 白白排除在高并发批次之外（本批 23 个里就有 3 个这类误判）。
    AST 词元只保留真实出现在语法树里的名字，注释/字符串天然不参与。
    """
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return ""
    toks: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            toks.add(node.id)
        elif isinstance(node, ast.Attribute):
            toks.add(node.attr)
        elif isinstance(node, ast.alias):
            toks.add(node.name)
            if node.asname:
                toks.add(node.asname)
        elif isinstance(node, ast.ImportFrom):
            toks.add(node.module or "")
    return " ".join(sorted(toks))


def _sources(obj_or_cls) -> tuple[str, str]:
    """返回 (import 行, 代码词元)，**合并自身模块 + MRO 上全部基类模块**。

    🔴 修正（2026-10-16 第二处）：旧版只看因子自身模块。
    实测 `current_ratio` / `quick_ratio` / `rd_intensity` / `forecast_yoy` / `forecast_kind`
    自身源码里没有联网入口 —— 它们继承 FundamentalFactorBase / ForecastFactorBase，
    取数走基类 → 必须顺着 MRO 看基类模块，否则漏判成 offline，
    高并发跑起来就是把数据源账号打封（10-12 那次 9.3 万次 WinError 的复现路径）。
    """
    cls = obj_or_cls if isinstance(obj_or_cls, type) else type(obj_or_cls)
    mods = []
    for k in [cls] + list(cls.__mro__):
        m = sys.modules.get(k.__module__)
        if m is not None and m not in mods:
            mods.append(m)
    imps, toks = [], []
    for m in mods:
        try:
            s = inspect.getsource(m)
        except Exception:
            continue
        imps.append(_import_block(s))
        toks.append(_code_tokens(s))
    return "\n".join(imps), " ".join(toks)


def classify(names: list[str]) -> tuple[list[str], list[str], dict[str, str]]:
    offline, online, why = [], [], {}
    for n in names:
        f = _registry_get(n)
        imp, toks = _sources(f)
        hits = [k for k in ONLINE_KEYS if k in imp]
        # import 没命中，再看**代码词元**（不含注释/docstring）里有没有真实调用
        if not hits:
            hits = [k for k in ONLINE_KEYS if k in toks]
            if hits:
                hits = [h + "@body" for h in hits]
        # 豁免：只用本地 parquet 面板的（龙虎榜/两融），即便注释里提到数据源名
        # （同样只看代码词元：豁免会把人推向 offline，属"漏判"方向，宜窄不宜宽）
        if hits and not any(lk in toks for lk in LOCAL_CACHE_KEYS):
            online.append(n)
            why[n] = ",".join(hits)
        else:
            offline.append(n)
            if hits:
                why[n] = "本地面板豁免:" + ",".join(hits)
    return offline, online, why


def _registry_get(name: str):
    from factors.interface import get_factor
    return get_factor(name)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--emit-csv", action="store_true")
    ap.add_argument("--offline-only", action="store_true", help="只打印离线名单（逗号分隔，便于直接喂给别的脚本）")
    ap.add_argument("--online-only", action="store_true")
    args = ap.parse_args()

    sys.path.insert(0, str(ROOT))
    import factors  # noqa: F401  触发全量注册
    from factors.interface import list_factors
    names = list_factors()
    offline, online, why = classify(names)

    if args.offline_only:
        print(",".join(offline))
        return
    if args.online_only:
        print(",".join(online))
        return

    print(f"总计 {len(names)} 个注册因子 → 离线 {len(offline)} / 联网 {len(online)}")
    print(f"\n=== 联网类（必须低并发 + 先预热，{len(online)} 个）===")
    for n in online:
        print(f"  {n:28s} 触发关键字={why[n]}")
    print(f"\n=== 离线类（纯本地计算，可高并发，{len(offline)} 个）===")
    print("  " + ", ".join(offline))

    if args.emit_csv:
        out = ROOT / ".cache" / "factor_io_class.csv"
        out.parent.mkdir(exist_ok=True)
        out.write_text("factor,class,hits\n" +
                       "".join(f"{n},offline,\n" for n in offline) +
                       "".join(f"{n},online,{why[n]}\n" for n in online),
                       encoding="utf-8")
        print(f"\n✅ 已写入 {out}")


if __name__ == "__main__":
    main()
