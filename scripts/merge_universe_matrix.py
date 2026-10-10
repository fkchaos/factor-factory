"""合并「分片并行」产出的池子矩阵回主矩阵（2026-10-10 新增）。

背景：93 因子 × 7 池 = 651 个验证单元，单进程串行约 31h。
故按池拆成 7 个分片并行跑（scripts/factor_universe_matrix.py --tag <pool> --pools <pool>），
每个分片写 parts/ic_matrix_<tag>.csv，本脚本负责合回主矩阵。

合并规则（重要）：
- **只填主矩阵里的 NaN**，分片不覆盖已有值 → 同一池被拆成多个因子分片时（如 ALL-a / ALL-b），
  两次结果按行互补，不会互相踩。
- index 取并集（分片可能算出主矩阵里没有的因子行）。
- 三张矩阵（ic / icir / dsr）同步合并，index/columns 强制对齐。

用法：
    python scripts/merge_universe_matrix.py                 # 合并到当天主矩阵
    python scripts/merge_universe_matrix.py --date 2026-10-10
    python scripts/merge_universe_matrix.py --dry-run       # 只看覆盖率不动盘

合并完重写卡片「池子矩阵」段：
    python scripts/factor_universe_matrix.py --factors all --pools ""
    （requested 为空 → 跳过计算循环，只用合并后的矩阵重写卡片段并落盘）
"""
from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "deliverables" / "universe_matrix"
PARTS_DIR = OUT_DIR / "parts"
KINDS = ("ic", "icir", "dsr")


def _read(path: Path) -> pd.DataFrame | None:
    return pd.read_csv(path, index_col=0) if path.exists() else None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=date.today().isoformat())
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    main_paths = {k: OUT_DIR / f"{k}_matrix_{args.date}.csv" for k in KINDS}
    mats = {k: _read(p) for k, p in main_paths.items()}
    if mats["ic"] is None:
        # 无主矩阵：以分片并集为骨架新建（首次全量并行时会走到这里）
        print(f"[warn] 主矩阵不存在：{main_paths['ic'].name}，将由分片并集新建")
        mats = {k: None for k in KINDS}

    part_files = sorted(PARTS_DIR.glob("ic_matrix_*.csv")) if PARTS_DIR.exists() else []
    if not part_files:
        print("[warn] parts/ 下没有分片文件，无需合并")
        return

    for pf in part_files:
        tag = pf.name[len("ic_matrix_"):-len(".csv")]
        pic = _read(pf)
        pici = _read(PARTS_DIR / f"icir_matrix_{tag}.csv")
        pdsr = _read(PARTS_DIR / f"dsr_matrix_{tag}.csv")
        if pic is None:
            continue
        filled_before = 0 if mats["ic"] is None else int(mats["ic"].notna().sum().sum())
        for k, part in (("ic", pic), ("icir", pici), ("dsr", pdsr)):
            if part is None:
                continue
            base = mats[k]
            if base is None:
                mats[k] = part.copy()
                continue
            # index / columns 取并集后按标签对齐，只填 NaN
            mats[k] = base.reindex(
                index=base.index.union(part.index),
                columns=base.columns.union(part.columns),
            )
            mats[k] = mats[k].where(mats[k].notna(), part)
        filled_after = int(mats["ic"].notna().sum().sum())
        cols = [c for c in pic.columns if pic[c].notna().any()]
        print(f"[merge] {tag}: 覆盖列 {cols} → 新增 {filled_after - filled_before} 单元格")

    ic = mats["ic"]
    n_rows = int(ic.notna().any(axis=1).sum())
    print("\n== 合并结果 ==")
    print(f"矩阵形状 {ic.shape[0]} 因子 × {ic.shape[1]} 池"
          f"｜含值行 {n_rows}｜含值单元格 {int(ic.notna().sum().sum())}"
          f"｜覆盖率 {ic.notna().sum().sum() / (ic.shape[0] * ic.shape[1]):.1%}")
    print("各池已算因子数：")
    for c in ic.columns:
        print(f"  {c}: {int(ic[c].notna().sum())}/{ic.shape[0]}")
    empty_rows = [str(i) for i in ic.index if ic.loc[i].isna().all()]
    if empty_rows:
        print(f"⚠️ 全空行 {len(empty_rows)} 个（未算/全失败）：{empty_rows[:10]}{' ...' if len(empty_rows) > 10 else ''}")

    if args.dry_run:
        print("\n[dry-run] 未落盘")
        return

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for k in KINDS:
        mats[k].to_csv(main_paths[k])
        print(f"✅ 已写入 {main_paths[k].name}")


if __name__ == "__main__":
    main()
