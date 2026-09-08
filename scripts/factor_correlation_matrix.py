"""生成已交付因子 × 已交付因子的全局相关性矩阵（55×55）。

背景（2026-09-08 外部审核）：
- 交付包 correlation.csv 是「本因子 vs 5 个动物园基准」单池结论，并非全局互相关；
  外部审核自己另算了 55 因子互相关，发现 f0047a↔f0050a ρ=-0.78（同信号正反面）。
- 本脚本补上这张全局矩阵，并自动标 |ρ|≥0.7 的高冗余配对，供策略组/驱动器看正交性。

数据口径（与 build_deliverable.correlation.csv 一致）：
- 直接吃 .cache/factor_series/{module}__{pool}__{start}__{min_mcap}.pkl（**中性化后**因子值，
  去市值/行业暴露，看净 alpha 相关性才有意义；与 PIT 红线不冲突——pkl 已是中性化后产物）。
- 逐日截面 z-score（消规模偏差）后求 Pearson ρ，按交易日时间平均 → N×N 矩阵。
  等价于 build_deliverable.compute_correlation 的口径，但覆盖全 55 因子而非 vs 基准。

用法：
    python scripts/factor_correlation_matrix.py [--pool hs800] [--out-dir deliverables/universe_matrix]
"""
from __future__ import annotations

import argparse
import csv
import pickle
import re
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
FACTOR_ROOT = ROOT / "deliverables" / "factors"
CACHE = ROOT / ".cache" / "factor_series"
OUT_DIR = ROOT / "deliverables" / "universe_matrix"
REDUNDANT_THRESHOLD = 0.70  # |ρ|≥0.7 视为高冗余（同源/近重复，勿重复入模）


def parse_manifest(pkg_dir: Path) -> dict:
    mp = pkg_dir / "manifest.yaml"
    if not mp.exists():
        return {}
    try:
        return yaml.safe_load(mp.read_text(encoding="utf-8")) or {}
    except Exception:
        # 容错：部分 manifest 含未引号冒号（如 neutralization: ...(PIT: ...)）属非法 YAML，
        # safe_load 会抛错。退而用正则取关键字段（本脚本只需 factor 映射到 pkl 前缀）。
        txt = mp.read_text(encoding="utf-8")
        out: dict = {}
        m = re.search(r"^factor:\s*(.+)$", txt, re.M)
        if m:
            out["factor"] = m.group(1).strip()
        return out


def fcode_for_mod(mod: str) -> str:
    """pkl 模块名 -> fcode：直接读 deliverables/factors/*/manifest.yaml 的 factor 字段匹配。"""
    if not FACTOR_ROOT.exists():
        return mod
    for d in sorted(FACTOR_ROOT.iterdir()):
        if not d.is_dir() or d.name.startswith("_"):
            continue
        man = parse_manifest(d)
        if man.get("factor") == mod:
            return d.name  # fcode
    return mod


def module_fcode_map() -> dict[str, str]:
    return {mod: fcode for fcode, mod in load_fcode_module_map().items()}


def collect_factor_pkls() -> dict[str, Path]:
    """mod -> 优先 hs800 的 pkl（覆盖 hs300/hs800 两池，全部已交付因子入库）。"""
    out: dict[str, Path] = {}
    for p in sorted(CACHE.glob("*__*.pkl")):
        if p.name.startswith("_panel"):
            continue
        mod = module_name_of(p)
        pool = p.name.split("__")[1]
        cur = out.get(mod)
        if cur is None or pool == "hs800":
            out[mod] = p
    return out


def load_series(pkl: Path) -> dict:
    with open(pkl, "rb") as f:
        obj = pickle.load(f)
    # pkl 结构：{"stamp": (...), "factor_series": {date: Series(asset->val)}}
    # 只返回 factor_series 本身（中性化后），否则 stamp 元组会被当成日期遍历。
    return obj["factor_series"]


def module_name_of(pkl: Path) -> str:
    """pkl 文件名 = {module}__{pool}__{start}__{min_mcap}.pkl → 取首个 __ 前段。"""
    return pkl.name.split("__")[0]


def global_factor_corr(all_series: dict[str, dict], names: list[str]) -> pd.DataFrame:
    """逐日截面 Pearson ρ（列=因子，行=asset，Pearson 自动中心化），时间平均 → N×N 矩阵。"""
    dates = sorted(set().union(*[set(s) for s in all_series.values()]))
    acc = pd.DataFrame(0.0, index=names, columns=names)
    cnt = pd.DataFrame(0, index=names, columns=names)
    diag = False
    for t in dates:
        cols = {n: all_series[n][t] for n in names if t in all_series[n]}
        if len(cols) < 2:
            continue
        df = pd.DataFrame(cols)  # asset rows × factor cols
        df = df.apply(pd.to_numeric, errors="coerce")
        if df.shape[0] < 5:  # 资产数太少，相关不可靠
            continue
        # pandas corr 默认 pairwise：逐对因子用共同非 NaN 观测算 Pearson，
        # 不要整行 dropna（否则各因子 asset 交集过小，每天都被跳过 → 全 NaN）
        corr = df.corr(method="pearson")
        if not diag:
            diag = True
            print(f"[diag] 首日 {t}: df={df.shape} 对角={np.diag(corr.to_numpy())[:3]} "
                  f"非NaN比={corr.notna().to_numpy().mean():.2f}")
        acc = acc.add(corr.fillna(0.0))
        cnt = cnt.add(corr.notna().astype(int))
    mat = (acc / cnt.replace(0, np.nan))  # 缺观测对 → NaN
    mat.index.name = "fcode"
    return mat


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pool", default="hs800")
    ap.add_argument("--out-dir", default=str(OUT_DIR))
    ap.add_argument("--threshold", type=float, default=REDUNDANT_THRESHOLD)
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # 只覆盖已交付因子（registry 内 fcode），标签用 fcode，排除研究中未交付模块
    reg_csv = FACTOR_ROOT / "_REGISTRY.csv"
    if not reg_csv.exists():
        print("ERROR: _REGISTRY.csv 缺失")
        return
    all_series: dict[str, dict] = {}
    pool_of: dict[str, str] = {}
    with open(reg_csv, encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            fcode = (row.get("fcode") or "").strip()
            if not fcode:
                continue
            man = parse_manifest(FACTOR_ROOT / fcode)
            mod = man.get("factor") if man else None
            if not mod:
                continue
            pkls = [p for p in CACHE.glob(f"{mod}__*.pkl") if not p.name.startswith("_panel")]
            if not pkls:
                continue
            hs800 = [p for p in pkls if "__hs800__" in p.name]
            pkl = (hs800 or pkls)[0]
            all_series[fcode] = load_series(pkl)
            pool_of[fcode] = pkl.name.split("__")[1]

    if not all_series:
        print("ERROR: 无 factor_series pkl 缓存匹配已交付因子，先跑 build_deliverable 建缓存")
        return
    names = sorted(all_series)
    print(f"载入 {len(names)} 个因子 series（pool={args.pool}）")
    mat = global_factor_corr(all_series, names)

    today = pd.Timestamp.now().strftime("%Y%m%d")
    mat_path = out_dir / f"factor_correlation_matrix_{today}.csv"
    mat.to_csv(mat_path)
    print(f"矩阵已写 → {mat_path}  ({mat.shape[0]}×{mat.shape[1]})")

    # 高冗余配对清单（|ρ|≥threshold，排除对角线）
    pairs = []
    arr = mat.to_numpy()
    idx = list(mat.index)
    for i in range(len(idx)):
        for j in range(i + 1, len(idx)):
            r = arr[i, j]
            if pd.notna(r) and abs(r) >= args.threshold:
                pairs.append((idx[i], idx[j], round(float(r), 3)))
    pairs.sort(key=lambda x: -abs(x[2]))

    rep_path = out_dir / f"redundant_pairs_{today}.csv"
    pd.DataFrame(pairs, columns=["fcode_a", "fcode_b", "pearson_rho"]).to_csv(rep_path, index=False)
    print(f"\n高冗余配对（|ρ|≥{args.threshold}）：{len(pairs)} 对")
    for a, b, r in pairs:
        tag = "⚠ 反向twin" if r < 0 else "同向近重复"
        print(f"  {a} ↔ {b}  ρ={r:+.2f}  {tag}")

    # 最独立因子（与所有其他因子 |ρ| 均值最低，top5）
    mean_abs = mat.abs().mean(axis=1).sort_values()
    print("\n最独立（|ρ|均值最低，候选正交组合核心）：")
    for fc, v in mean_abs.head(8).items():
        print(f"  {fc}  mean|ρ|={v:.3f}")


if __name__ == "__main__":
    main()
