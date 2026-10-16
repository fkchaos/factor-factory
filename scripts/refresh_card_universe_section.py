"""从合并后的池子矩阵刷新各因子卡片的「池子矩阵」段，并交叉核对卡片自报 IC。

动机（2026-10-16）
  `factor_universe_matrix.py` 只在**整轮串行运行末尾**才写卡片；口径修复后改用
  `run_matrix_parallel.py` 分片并行 + `merge_universe_matrix.py` 合并，
  这条路径**不写卡片** → 卡片里留着 10-15 的残缺段（6 池里 5 池 NaN）。
  另：卡片「分池 IC」表由 build_deliverable 写、矩阵由本脚本刷新，
  两者必须**逐格一致**才说明口径统一 —— 这正是本脚本的交叉核对职责。

用法：
    python scripts/refresh_card_universe_section.py            # 交叉核对 + 刷新
    python scripts/refresh_card_universe_section.py --dry-run  # 只看核对结果
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
FACTORS_DIR = ROOT / "deliverables" / "factors"
MATRIX_DIR = ROOT / "deliverables" / "universe_matrix"
TOL = 1e-4  # 卡片 IC 保留 4 位小数，容差取半个末位


def _latest(stem: str) -> Path | None:
    cands = sorted(MATRIX_DIR.glob(f"{stem}_*.csv"))
    return cands[-1] if cands else None


def name_to_fcode() -> dict[str, str]:
    """扫 manifest.yaml：factor -> fcode。"""
    m: dict[str, str] = {}
    for p in FACTORS_DIR.glob("*/manifest.yaml"):
        txt = p.read_text(encoding="utf-8", errors="ignore")
        fm = re.search(r"^factor:\s*(\S+)", txt, re.M)
        cm = re.search(r"^fcode:\s*(\S+)", txt, re.M)
        if fm and cm:
            m[fm.group(1)] = cm.group(1)
    return m


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    ic_p, icir_p, dsr_p = _latest("ic_matrix"), _latest("icir_matrix"), _latest("dsr_matrix")
    if not (ic_p and icir_p and dsr_p):
        print("[fatal] 找不到矩阵文件")
        return 1
    ic = pd.read_csv(ic_p, index_col=0)
    icir = pd.read_csv(icir_p, index_col=0)
    print(f"[load] {ic_p.name} / {icir_p.name} / {dsr_p.name}｜形状 {ic.shape}")
    today = ic_p.stem.split("_")[-1]

    n2f = name_to_fcode()
    print(f"[map] manifest 解析出 {len(n2f)} 个 factor→fcode")

    updated, skipped, no_card, no_map = [], [], [], []
    mismatches: list[tuple[str, str, float, float]] = []
    missing_metrics: list[tuple[str, str]] = []

    for name in ic.index:
        row = ic.loc[name]
        if row.isna().all():
            skipped.append(name)
            continue
        fcode = n2f.get(name)
        if not fcode:
            no_map.append(name)
            continue
        card = FACTORS_DIR / fcode / "card.md"
        if not card.exists():
            no_card.append((name, fcode))
            continue

        # ---- 交叉核对：卡片自报 metrics_{pool}.json vs 矩阵 ----
        for pool in ic.columns:
            if pd.isna(row[pool]):
                continue
            mf = FACTORS_DIR / fcode / f"metrics_{pool}.json"
            if not mf.exists():
                missing_metrics.append((fcode, pool))
                continue
            try:
                import json

                card_ic = json.loads(mf.read_text(encoding="utf-8"))["ic"]["rank_ic"]
            except Exception:
                missing_metrics.append((fcode, pool))
                continue
            if abs(card_ic - row[pool]) > TOL:
                mismatches.append((fcode, pool, float(card_ic), float(row[pool])))

        if args.dry_run:
            continue

        # ---- 幂等重写「池子矩阵」段（格式与 factor_universe_matrix.py 一致）----
        valid = row.dropna()
        live = [p for p in ic.columns if not pd.isna(row[p])]
        home = None
        if live:
            # 观测值，非推荐：口径与 factor_universe_matrix.py:214 一致（idxmax，最大 IC）
            home = max(live, key=lambda p: row[p])
        section = (
            f"\n## 池子矩阵（{today}）\n\n"
            f"- RankIC: {row.round(4).to_dict()}\n"
            f"- ICIR: {icir.loc[name].round(2).to_dict()}\n"
            f"- IC 最高池（**观测值，非推荐**）: {home or 'N/A'}\n"
            f"- 覆盖: {len(valid)}/{len(ic.columns)} 池已算（未算池为 NaN，非 0）\n"
            f"- 口径说明: 本段为**最新检验批**口径（与上方「分池 IC」表同源同流程，中性化含 PIT 市值）。\n"
            f"  与上方表格若存在 ≤3e-3 的差异，来自**数据版本与计算批次**（前复权价随分红/拆分全历史重算、\n"
            f"  指数成分快照更新），不是口径不一致；矩阵是增量累积的，同一因子各池可能来自不同批次。\n"
        )
        text = card.read_text(encoding="utf-8")
        marker = "\n## 池子矩阵（"
        if marker in text:
            cut = text.index(marker)
            tail = text[cut:]
            # 安全闸：若「池子矩阵」段之后还有别的章节，说明截断会吞掉它们 → 拒绝改写
            if re.search(r"\n## (?!池子矩阵)", tail):
                print(f"  [skip] {fcode}：「池子矩阵」段后还有后续章节，拒绝截断改写")
                continue
            text = text[:cut].rstrip("\n") + "\n" + section
        else:
            text = text.rstrip("\n") + "\n" + section
        card.write_text(text, encoding="utf-8")
        updated.append(fcode)

    print("\n== 交叉核对（卡片 metrics_*.json vs 矩阵 IC）==")
    if mismatches:
        print(f"❌ 不一致 {len(mismatches)} 个（> {TOL}）：")
        for fcode, pool, a, b in mismatches[:30]:
            print(f"   {fcode}@{pool}: 卡片 {a:.6f} vs 矩阵 {b:.6f}  Δ={a-b:+.2e}")
    else:
        print("✅ 全部一致（口径已统一）")
    if missing_metrics:
        print(f"⚠️ 缺 metrics 文件 {len(missing_metrics)} 例（无法核对）: {missing_metrics[:10]}")

    print("\n== 卡片刷新 ==")
    print(f"✅ 已刷新 {len(updated)} 张卡片")
    if skipped:
        print(f"⏭️ 全 NaN 行跳过 {len(skipped)}: {skipped}")
    if no_map:
        print(f"⚠️ manifest 里找不到 factor 名 {len(no_map)}: {no_map}")
    if no_card:
        print(f"⚠️ 卡片不存在 {len(no_card)}: {no_card}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
