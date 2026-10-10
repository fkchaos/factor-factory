"""因子-池子矩阵验证：每个因子 × 多个池子跑 RankIC/ICIR，自动标注"主场"。

动机（用户 2026-08-05 决策）：单池验证会漏掉"只在特定池子有效的因子组合"。
本脚本把因子 × 池子做成 IC 矩阵，回答：
1. 每个因子的"主场"（IC 最高的池子）在哪？
2. 是否存在"换池后因子强弱反转"的实例（正是担心的漏网之鱼）？
3. 因子声明的 universe_hint 与实测是否一致？

用法：
    python scripts/factor_universe_matrix.py [--pools sz50,hs300,hs800,ALL] [--start 2020-01-01]

依赖：池子缓存已就绪（见 .cache/cache_universe.py）；ALL 池默认 min_mcap=50亿。
输出：markdown 矩阵 + 写入 research/factor_cards/（追加"池子矩阵"段）。

==== 鲁棒性（2026-08-07 彻底修复）====
- 断点续算：启动时载入最近的 ic_matrix_*.csv，已填列原样保留，只算 NaN/空列；
  进程被杀后重跑可无缝续上，不再白跑几小时（2026-08-06 曾卡在 4/6 池）。
- 全列宽表：DataFrame 永远按 ALL_POOLS 全列构建，绝不会因"只传部分池"而冲掉已完成列。
- 单池异常隔离：单个 (因子,池) 计算抛错只记日志跳过，不中断整轮；其余池照常落盘。
"""
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from data.providers import BaoStockProvider
from factors.overnight_intraday import OvernightIntradayFactor
from factors.ivol import IvolFactor
from engine.interface import BacktestConfig
from validate.validator import validate_factor

# 池子定义：name -> BaoStockProvider 额外参数
POOLS = {
    "sz50": {},
    "hs300": {},
    "zz500": {},
    "hs800": {},
    "zz1000": {},
    "hs1800": {},
    "ALL": {"min_mcap": 50e8},  # 市值 ≥ 50 亿（过滤壳股/流动性差）
}
ALL_POOLS = list(POOLS)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pools", default=",".join(ALL_POOLS))
    ap.add_argument("--start", default="2020-01-01")
    # 🔴 因子集长期硬编码为 2 个老因子（2026-10-10 修复）：传 all 覆盖全量注册因子，
    # 或传逗号分隔的注册名。配合脚本自带的断点续算（ic_matrix_*.csv），可分多批累积。
    ap.add_argument("--factors", default="",
                    help="'all'=全量注册因子；或逗号分隔注册名；留空=默认 2 个老因子")
    # 🔴 2026-10-10 新增分片并行：单进程串行跑 93 因子×7 池 ≈31h，机器 16 核却只用一个。
    # 传 --tag <分片名> 时输出到 parts/ 子目录（ic_matrix_{tag}.csv），各分片互不覆盖，
    # 算完用 scripts/merge_universe_matrix.py 合并回主矩阵。
    # 分片文件放子目录是刻意的：主目录 glob("ic_matrix_*.csv") 取最新做续算基准，
    # 分片文件若落在主目录会被误当成续算基准（只含单池 → 静默丢进度）。
    ap.add_argument("--tag", default="",
                    help="非空=分片并行模式，产物写入 parts/ic_matrix_{tag}.csv")
    args = ap.parse_args()
    requested = [p.strip() for p in args.pools.split(",") if p.strip()]

    spec = (args.factors or "").strip()
    if spec:
        import factors as _factors_pkg  # noqa: F401  触发全量注册
        from factors.interface import get_factor, list_factors
        names = list_factors() if spec == "all" else [n.strip() for n in spec.split(",") if n.strip()]
        factors, missing = [], []
        for n in names:
            try:
                factors.append(get_factor(n))
            except KeyError:
                missing.append(n)
        if missing:
            print(f"[warn] 未注册因子名，跳过：{missing}", flush=True)
        print(f"[factors] 本次纳入 {len(factors)} 个因子", flush=True)
    else:
        factors = [OvernightIntradayFactor(), IvolFactor()]
    cfg = BacktestConfig(train_days=252, test_days=126, step_days=63, top_n=20)

    out_dir = ROOT / "deliverables" / "universe_matrix"
    if args.tag:
        out_dir = out_dir / "parts"
    out_dir.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()
    file_tag = args.tag or today  # 分片模式用 tag 作文件名，避免与主矩阵/其他分片互串

    factor_names = [f.name for f in factors]

    # 断点续算：载入最近的已有矩阵（不论日期），保留已填列/行，只算缺失单元格（根因1/2）
    def _latest_existing() -> Path | None:
        if args.tag:  # 分片模式：只认自己的分片文件，绝不读主矩阵
            p = out_dir / f"ic_matrix_{args.tag}.csv"
            return p if p.exists() else None
        cands = sorted(out_dir.glob("ic_matrix_*.csv"))
        return cands[-1] if cands else None

    prev = _latest_existing()
    # 🔴 2026-10-10 修复断点续算 index 对齐 bug（已造成一次真实数据丢失）：
    # 旧逻辑先按"当前因子集"建空矩阵，再 `ic_mat[col] = old[col]` 按 index 复制——
    # 若本次只跑部分因子（如单因子冒烟），旧矩阵里其余已算因子因 index 不匹配被全丢成 NaN，
    # 随后 flush 把 93×7 完整矩阵压成几行，静默抹掉历史进度。
    # 修复：矩阵 index 取"当前因子 ∪ 旧矩阵全部 index"，复制时 index 对齐不会丢行；
    # 同时去掉 `not isna().all()` 守卫，全列整列复制（全 NaN 列复制是空操作，无害）。
    if prev is not None:
        old_ic = pd.read_csv(prev, index_col=0)
        old_ici = pd.read_csv(out_dir / f"icir_matrix_{prev.name.split('_')[-1]}", index_col=0)
        old_dsr = pd.read_csv(out_dir / f"dsr_matrix_{prev.name.split('_')[-1]}", index_col=0)
        full_index = old_ic.index.union(pd.Index(factor_names))
    else:
        old_ic = old_ici = old_dsr = None
        full_index = pd.Index(factor_names)

    # 全列宽表：永远 7 列；index 取并集，避免"只传部分池/部分因子"时冲掉已完成行
    # （2026-08-07 修根因3：只传部分池不冲掉已完成列；2026-10-10 修：部分因子不冲掉已完成行）
    ic_mat = pd.DataFrame(index=full_index, columns=ALL_POOLS, dtype=float)
    icir_mat = pd.DataFrame(index=full_index, columns=ALL_POOLS, dtype=float)
    dsr_mat = pd.DataFrame(index=full_index, columns=ALL_POOLS, dtype=float)

    if prev is not None:
        for col in ALL_POOLS:
            if col in old_ic.columns:
                ic_mat[col] = old_ic[col]
            if col in old_ici.columns:
                icir_mat[col] = old_ici[col]
            if col in old_dsr.columns:
                dsr_mat[col] = old_dsr[col]
        filled = int(ic_mat.notna().sum().sum())
        print(f"[resume] 载入已有矩阵 {prev.name}，保留已填单元格 {filled}/{len(full_index) * len(ALL_POOLS)}", flush=True)

    def _flush_csv() -> None:
        ic_mat.to_csv(out_dir / f"ic_matrix_{file_tag}.csv")
        icir_mat.to_csv(out_dir / f"icir_matrix_{file_tag}.csv")
        dsr_mat.to_csv(out_dir / f"dsr_matrix_{file_tag}.csv")

    # 续算前先落一次盘，确保从既有进度起步
    _flush_csv()

    for pool in requested:
        prov = BaoStockProvider(universe=pool, history_start=args.start, **POOLS.get(pool, {}))
        print(f"[{pool}] 池子规模={len(prov.list_universe('2024-12-31'))}，验证中...", flush=True)
        for f in factors:
            # 已填则跳过（续算核心）
            if not pd.isna(ic_mat.loc[f.name, pool]):
                print(f"  skip {f.name}/{pool} (已存在，续算跳过)", flush=True)
                continue
            try:
                m = validate_factor(f, prov, cfg)
            except Exception as e:  # 单池异常隔离：记日志、跳过、不中断整轮
                print(f"  ❌ {f.name}/{pool} 计算失败: {e!r}", flush=True)
                continue
            ic_mat.loc[f.name, pool] = m["rank_ic"]
            icir_mat.loc[f.name, pool] = m["icir"]
            dsr_mat.loc[f.name, pool] = m["dsr"]
            print(f"  {f.name}: RankIC={m['rank_ic']:+.4f} ICIR={m['icir']:+.2f} "
                  f"DSR={m['dsr']} PBO={m['pbo']}", flush=True)
        _flush_csv()  # 每池落盘一次，断点可续
        print(f"  ↳ 已落盘 {out_dir.name}/ic_matrix_{file_tag}.csv", flush=True)

    # 主场标注：每因子 IC 最高的池子；反转实例：最高与最低 IC 异号
    print("\n" + "=" * 60)
    print("因子-池子 RankIC 矩阵")
    print(ic_mat.round(4).to_string())
    print("\nICIR 矩阵")
    print(icir_mat.round(2).to_string())
    print("\nDSR 矩阵")
    print(dsr_mat.round(3).to_string())

    # 🔴 2026-10-10 修复：续算后大量未算因子行全 NaN，idxmax 会抛 ValueError。
    # 仅对"至少一列有值"的行求主场；全空行跳过（无主场可标注）。
    _valid = ic_mat.dropna(how="all")
    home = _valid.idxmax(axis=1) if not _valid.empty else pd.Series(dtype=object)
    print("\n== 主场标注 ==")
    for name in home.index:
        # 防御式读取：因子类以 duck typing 实现 Factor Protocol，可能未声明该可选属性
        # （2026-08-07 修复：OvernightIntradayFactor/IvolFactor 缺属性 → 主场标注整段 AttributeError）
        hint = next((getattr(f, "universe_hint", None) for f in factors if f.name == name), None)
        consistency = ""
        if hint:
            consistency = " ✅一致" if hint == home[name] else f" ⚠️声明={hint}≠实测"
        print(f"  {name}: 主场={home[name]} (IC {ic_mat.loc[name, home[name]]:+.4f}){consistency}")
    if _valid.empty:
        print("  （全部因子尚未计算出有效 IC，无主场可标注）")

    # 反转实例检测：同一因子在不同池子 IC 异号
    # （2026-08-07 修复：原 for-else 的 else 在无 break 时恒执行，检出异号也会误报"无异号"）
    print("\n== 换池反转检测（IC 异号 = 池子敏感因子）==")
    flipped = False
    for name in ic_mat.index:
        row = ic_mat.loc[name].dropna()
        if len(row) >= 2 and (row > 0).any() and (row < 0).any():
            print(f"  ⚠️ {name}: 池子间 IC 异号! {row.round(4).to_dict()}")
            flipped = True
    if not flipped:
        print("  （无 IC 异号实例）")

    # 落盘：写入因子卡片（幂等：同名"池子矩阵"段整体替换，重跑不堆叠历史）
    # 🔴 路径修复（2026-10-10）：卡片早已迁到 deliverables/factors/{fcode}/card.md，
    # 旧路径 research/factor_cards/{name}.md 不存在 → 全部 continue 跳过，P4 长期零产出。
    for name in ic_mat.index:
        # 🔴 2026-10-10 修复：续算残留的全 NaN 行（未算/全失败因子）跳过，避免写无效池子矩阵段
        if ic_mat.loc[name].isna().all():
            continue
        fobj = next((f for f in factors if getattr(f, "name", None) == name), None)
        # 🔴 2026-10-10 修复：续算残留行（本次未纳入 factors）解析不出 fcode，
        # 旧逻辑会回退到**已废弃**路径 research/factor_cards/{name}.md 并写入，
        # 污染旧卡片（实测：单因子冒烟把 ivol / overnight_intraday 的池子矩阵写进了废弃路径）。
        # 解析不出 fcode 的行直接跳过——宁可不写，也不写废弃路径。
        fcode = getattr(fobj, "fcode", None)
        if not fcode:
            continue
        card = ROOT / "deliverables" / "factors" / fcode / "card.md"
        if not card.exists():
            print(f"  [skip] {name} 卡片不存在：{card.relative_to(ROOT)}")
            continue
        # 口径修正（2026-09-09）：不再称"主场池"，IC 最高池仅是**观测值**，本厂不推荐配池
        section = (f"\n## 池子矩阵（{today}）\n\n"
                   f"- RankIC: {ic_mat.loc[name].round(4).to_dict()}\n"
                   f"- ICIR: {icir_mat.loc[name].round(2).to_dict()}\n"
                   f"- IC 最高池（**观测值，非推荐**）: {home.get(name, 'N/A')}\n")
        text = card.read_text(encoding="utf-8")
        marker = "\n## 池子矩阵（"
        if marker in text:
            text = text[: text.index(marker)].rstrip("\n") + "\n" + section
        else:
            text = text.rstrip("\n") + "\n" + section
        card.write_text(text, encoding="utf-8")
        print(f"✅ {name} 卡片已写入池子矩阵段（主场={home[name]}）")


if __name__ == "__main__":
    main()
