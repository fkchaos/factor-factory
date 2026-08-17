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
    args = ap.parse_args()
    requested = [p.strip() for p in args.pools.split(",") if p.strip()]

    factors = [OvernightIntradayFactor(), IvolFactor()]
    cfg = BacktestConfig(train_days=252, test_days=126, step_days=63, top_n=20)

    out_dir = ROOT / "deliverables" / "universe_matrix"
    out_dir.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()

    # 全列宽表：永远 6 列，避免"只传部分池"时冲掉已完成列（2026-08-07 修复根因3）
    ic_mat = pd.DataFrame(index=[f.name for f in factors], columns=ALL_POOLS, dtype=float)
    icir_mat = pd.DataFrame(index=[f.name for f in factors], columns=ALL_POOLS, dtype=float)
    dsr_mat = pd.DataFrame(index=[f.name for f in factors], columns=ALL_POOLS, dtype=float)

    # 断点续算：载入最近的已有矩阵（不论日期），保留已填列，只算缺失列（根因1/2）
    def _latest_existing() -> Path | None:
        cands = sorted(out_dir.glob("ic_matrix_*.csv"))
        return cands[-1] if cands else None

    prev = _latest_existing()
    # 2026-08-07 修复：原条件排除了"当天已存在的矩阵"，导致同日二次运行不续算、
    # 六池从零重跑（约 2h 白跑）。注释本意即"不论日期"，此处与实现对齐。
    if prev is not None:
        old = pd.read_csv(prev, index_col=0)
        for col in ALL_POOLS:
            if col in old.columns and not old[col].isna().all():
                ic_mat[col] = old[col]
                if col in (old_icir := pd.read_csv(out_dir / f"icir_matrix_{prev.name.split('_')[-1]}", index_col=0)).columns:
                    icir_mat[col] = old_icir[col]
                if col in (old_dsr := pd.read_csv(out_dir / f"dsr_matrix_{prev.name.split('_')[-1]}", index_col=0)).columns:
                    dsr_mat[col] = old_dsr[col]
        filled = int(ic_mat.notna().sum().sum())
        print(f"[resume] 载入已有矩阵 {prev.name}，保留已填单元格 {filled}/{len(factors) * len(ALL_POOLS)}", flush=True)

    def _flush_csv() -> None:
        ic_mat.to_csv(out_dir / f"ic_matrix_{today}.csv")
        icir_mat.to_csv(out_dir / f"icir_matrix_{today}.csv")
        dsr_mat.to_csv(out_dir / f"dsr_matrix_{today}.csv")

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
        print(f"  ↳ 已落盘 {out_dir.name}/ic_matrix_{today}.csv", flush=True)

    # 主场标注：每因子 IC 最高的池子；反转实例：最高与最低 IC 异号
    print("\n" + "=" * 60)
    print("因子-池子 RankIC 矩阵")
    print(ic_mat.round(4).to_string())
    print("\nICIR 矩阵")
    print(icir_mat.round(2).to_string())
    print("\nDSR 矩阵")
    print(dsr_mat.round(3).to_string())

    home = ic_mat.idxmax(axis=1)
    print("\n== 主场标注 ==")
    for name in ic_mat.index:
        # 防御式读取：因子类以 duck typing 实现 Factor Protocol，可能未声明该可选属性
        # （2026-08-07 修复：OvernightIntradayFactor/IvolFactor 缺属性 → 主场标注整段 AttributeError）
        hint = next((getattr(f, "universe_hint", None) for f in factors if f.name == name), None)
        consistency = ""
        if hint:
            consistency = " ✅一致" if hint == home[name] else f" ⚠️声明={hint}≠实测"
        print(f"  {name}: 主场={home[name]} (IC {ic_mat.loc[name, home[name]]:+.4f}){consistency}")

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
    for name in ic_mat.index:
        card = ROOT / "research" / "factor_cards" / f"{name}.md"
        if not card.exists():
            continue
        section = (f"\n## 池子矩阵（{today}）\n\n"
                   f"- RankIC: {ic_mat.loc[name].round(4).to_dict()}\n"
                   f"- ICIR: {icir_mat.loc[name].round(2).to_dict()}\n"
                   f"- 主场: **{home[name]}**\n")
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
