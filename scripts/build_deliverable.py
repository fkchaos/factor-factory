"""构建因子交付包（PLAN_DELIVERABLES · Phase 1）。

产出：deliverables/factors/<f-code>/ 下四层文件
  - card.md            详细说明文档（强制交付物，含消费指引）
  - correlation.csv    相关性测试（vs 动物园 + 内部因子）
  - backtest_<pool>.csv 多空收益序列 + 统计（含/不含成本）
  - overfit_audit.json DSR/PBO 信任证书
  - manifest.yaml      元数据/溯源
并同步 _INDEX.md / _REGISTRY.csv。

用法：
  python scripts/build_deliverable.py --factor overnight_intraday --fcode f0001a \
      --pools hs300,hs800 --name "隔夜-日内分解"
  # 组合：
  # 组合因子的 --factor 传"注册名"而不是占位符，写错直接 KeyError：
  python scripts/build_deliverable.py --factor combo_equal_v1 --fcode f0003a \
      --combo --components f0001a,f0002a --pools hs300

注：逐日因子值计算需要 baostock 缓存（hs1800 拉取完成后跑）。纯函数（f-code 分配 /
registry / manifest 渲染）可通过 tests/test_build_deliverable.py 独立单测。
"""
from __future__ import annotations

import argparse
import json
import pickle
import os
import sys
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from data.providers import BaoStockProvider
from factors.interface import (
    winsorize_mad, zscore_cross_section, get_factor, list_factors,
)
from validate.validator import _neutralize_cross_section
from validate.overfit_audit import strategy_returns_from_factor, audit

# 相关性动物园基准 + 内部因子（交付物 correlation.csv 的对照集）
ZOO_FACTORS = ["momentum_20", "reversal_5", "size_log_mcap"]
INTERNAL_FACTORS = ["ivol", "overnight_intraday"]

OUT_ROOT = Path("deliverables/factors")
REGISTRY_CSV = OUT_ROOT / "_REGISTRY.csv"
INDEX_MD = OUT_ROOT / "_INDEX.md"
FIELDS = ["open", "high", "low", "close", "volume", "amount", "turnover", "market_cap"]


# ---------------------------------------------------------------------------
# 纯函数（可独立单测，不依赖 baostock）
# ---------------------------------------------------------------------------

def allocate_fcode(registry_csv: Path, name: str, ftype: str,
                   components: Optional[list] = None,
                   supersedes: Optional[str] = None) -> str:
    """集中分配下一个 f-code：最大 NNNN +1，字母从 a 起。

    返回 f-code 字符串（如 f0003a）并**追加一行到 registry**（若文件存在）。
    """
    import csv
    next_n = 1
    if registry_csv.exists():
        with open(registry_csv, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        nums = []
        for r in rows:
            code = r.get("fcode", "")
            if code.startswith("f") and code[1:5].isdigit():
                nums.append(int(code[1:5]))
        if nums:
            next_n = max(nums) + 1
    fcode = f"f{next_n:04d}a"
    # 追加注册（若 registry 已存在则 update 行，否则新建）
    row = {
        "fcode": fcode, "name": name, "type": ftype,
        "components": ",".join(components) if components else "",
        "status": "current", "supersedes": supersedes or "",
        "created": pd.Timestamp.now().strftime("%Y-%m-%d"), "note": "",
    }
    _upsert_registry(registry_csv, row)
    return fcode


def _upsert_registry(registry_csv: Path, row: dict) -> None:
    import csv
    cols = ["fcode", "name", "type", "components", "status", "supersedes", "created", "note"]
    rows = []
    if registry_csv.exists():
        with open(registry_csv, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
    rows = [r for r in rows if r.get("fcode") != row["fcode"]]
    rows.append(row)
    registry_csv.parent.mkdir(parents=True, exist_ok=True)
    with open(registry_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)


def render_manifest(**kw) -> str:
    """渲染 manifest.yaml（极简 YAML，避免外部依赖）。"""
    lines = ["# 因子交付包元数据（溯源 / 复现 / 防火墙基准）"]
    for k, v in kw.items():
        if isinstance(v, (list, tuple)):
            v = "[" + ", ".join(str(x) for x in v) + "]" if v else "[]"
        elif v is None:
            v = "null"
        elif isinstance(v, bool):
            v = "true" if v else "false"
        lines.append(f"{k}: {v}")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# 数据密集：逐日因子值 / 相关 / 回测（需 baostock 缓存）
# ---------------------------------------------------------------------------

SERIES_CACHE_DIR = Path(".cache/factor_series")

# 🔴 中性化口径版本号（2026-08-08 新增）
# 缓存的是"中性化之后"的因子值，所以指纹里**必须**含预处理口径版本，否则改了
# 中性化实现、重跑出包会静默命中旧缓存 → 你以为修复生效了，其实卡片上还是旧数字。
# 踩坑实例：v1 的市值中性化读面板 `market_cap` 列（今日快照回填全历史的假 PIT），
# 等于把 −β×未来收益注入残差；v2 改用 data/pit.py 现算 PIT 流通市值。
# **任何改动 _neutralize_cross_section / winsorize / zscore 链路的人，必须 +1。**
NEUTRALIZE_VERSION = "v2-pit-mcap"


def compute_factor_series(factor, provider, fields=FIELDS, use_cache: bool = True) -> tuple[dict, dict]:
    """复算逐日中性化因子值 + 1日前向收益（与 validate_factor 同预处理链）。

    返回 (factor_series: {date->Series(asset)}, fwd_ret_1: {date->Series})。
    中性化状态 = industry + mktcap(PIT)（与交付口径一致）。

    **磁盘缓存**：相关性对照集要把动物园 + 内部因子逐一复算一遍，三个交付包
    合计会把同一批因子重算十几遍（sz50 小池实测单包 8 分钟，hs300 更夸张）。
    这里按 (因子, 池子, 起始日) 缓存到 .cache/factor_series/，并用
    (交易日数, 最后交易日, 中性化口径版本) 做指纹校验——数据或预处理口径一变，
    缓存自动失效，不会吃到陈旧值。
    """
    # ---- panel 磁盘缓存（跨进程复用，避免每次出包重拼 1672×全历史，单包省 ~19min）----
    # 🔴 PIT 安全：缓存的是 get_panel 原始输出（已按披露日切片、未中性化）；
    #    中性化/compute 在缓存读取之后进行，语义不变。指纹含 pool+start+min_mcap+fields+源文件数。
    pool = getattr(provider, "_universe_mode", None) or getattr(provider, "universe", None)
    start = getattr(provider, "_history_start", None) or getattr(provider, "history_start", "")
    min_mcap = getattr(provider, "_min_mcap", 0)
    if pool is not None:
        start_tag = pd.Timestamp(start).strftime("%Y%m%d") if start else "na"
        ftag = abs(hash(tuple(fields))) % 100000
        baostock_dir = SERIES_CACHE_DIR.parent / "baostock"
        n_src = (len([f for f in os.listdir(baostock_dir) if f.endswith(".parquet")])
                 if baostock_dir.exists() else 0)
        panel_cache_fp = (SERIES_CACHE_DIR /
                          f"_panel__{pool}__{start_tag}__{min_mcap:.0f}__{ftag}__src{n_src}.parquet")
        if panel_cache_fp.exists():
            panel = pd.read_parquet(panel_cache_fp)
            print(f"    [panel cache hit] @ {pool}", flush=True)
        else:
            panel = provider.get_panel(fields, None, None)
            SERIES_CACHE_DIR.mkdir(parents=True, exist_ok=True)
            try:
                panel.to_parquet(panel_cache_fp)
            except Exception as e:
                print(f"    [panel cache write failed] {e}", flush=True)
    else:
        panel = provider.get_panel(fields, None, None)
    dates = sorted(panel.index.get_level_values("date").unique())
    N = len(dates)

    # 缓存 key 必须唯一标识"哪个池子、哪段历史"。BaoStockProvider 的属性是私有名
    # (_universe_mode/_history_start)，早期误用 provider.universe 拿到 "unknown"，
    # 会让 sz50 与 hs300 共用同一个缓存文件 —— 静默串池，比慢十倍严重得多。
    # 因此：识别不出池子就直接禁用缓存。
    if pool is None:
        use_cache = False
        cache_fp = None
    else:
        start_tag = pd.Timestamp(start).strftime("%Y%m%d") if start else "na"
        cache_fp = (SERIES_CACHE_DIR /
                    f"{getattr(factor, 'name', 'unknown')}__{pool}__{start_tag}__{min_mcap:.0f}.pkl")
    stamp = (N, str(dates[-1]) if N else "", NEUTRALIZE_VERSION)
    if use_cache and cache_fp is not None and cache_fp.exists():
        try:
            with open(cache_fp, "rb") as fh:
                blob = pickle.load(fh)
            if blob.get("stamp") == stamp:
                print(f"    [cache hit] {getattr(factor, 'name', '?')} @ {pool}", flush=True)  # noqa
                return blob["factor_series"], blob["fwd_ret_1"]
        except Exception:
            pass  # 缓存损坏就当没有，重算

    factor_series: dict = {}
    fwd_ret_1: dict = {}
    for idx, t in enumerate(dates):
        from factors.interface import slice_panel_to_date
        sub = slice_panel_to_date(panel, t)
        fv = factor.compute(sub, t).dropna()
        fv = winsorize_mad(fv)
        fv = _neutralize_cross_section(fv, panel, t, provider)
        fv = zscore_cross_section(fv)
        factor_series[t] = fv
        close_t = panel.xs(t, level="date")["close"]
        if idx + 1 < N:
            close_t1 = panel.xs(dates[idx + 1], level="date")["close"]
            fwd_ret_1[t] = close_t1 / close_t - 1.0

    if use_cache and cache_fp is not None:
        try:
            SERIES_CACHE_DIR.mkdir(parents=True, exist_ok=True)
            with open(cache_fp, "wb") as fh:
                pickle.dump({"stamp": stamp, "factor_series": factor_series,
                             "fwd_ret_1": fwd_ret_1}, fh, protocol=4)
        except Exception as e:
            print(f"    [cache write failed] {e}", flush=True)
    return factor_series, fwd_ret_1


def compute_correlation(factor_series: dict, provider,
                        other_factors: list[str], self_name: str = "__self__") -> pd.DataFrame:
    """本因子 vs 对照因子集的时间平均截面 Pearson ρ 矩阵（对称 N×N）。

    factor_series：本因子的逐日中性化值；对照因子逐一复算同口径中性化值后相关。

    历史 bug（2026-08-06 修复）：原实现把"逐日相关系数列表"直接塞进
    DataFrame(index=names)，1553 天的值配 5 个索引 → ValueError，交付包从未生成成功。
    现改为逐日算完整相关矩阵、再按时序求均值，输出真正的 N×N 平均相关矩阵。
    """
    panel = provider.get_panel(FIELDS, None, None)
    names = [self_name] + [f for f in other_factors if f != self_name]
    # 复算所有因子的逐日 series
    all_series: dict[str, dict] = {self_name: factor_series}
    for fn in names[1:]:
        fac = get_factor(fn)
        fs, _ = compute_factor_series(fac, provider)
        all_series[fn] = fs
    # 逐日截面相关矩阵，按时序求均值
    dates = sorted(set().union(*[set(s.keys()) for s in all_series.values()]))
    acc = pd.DataFrame(0.0, index=names, columns=names)
    cnt = pd.DataFrame(0, index=names, columns=names)
    for t in dates:
        cols = {n: all_series[n][t] for n in names if t in all_series[n]}
        if len(cols) < 2:
            continue
        df = pd.DataFrame(cols).dropna()
        if len(df) < 5:
            continue
        corr = df.corr(method="pearson").reindex(index=names, columns=names)
        mask = corr.notna()
        acc = acc.add(corr.fillna(0.0))
        cnt = cnt.add(mask.astype(int))
    mat = (acc / cnt.replace(0, np.nan)).reindex(index=names, columns=names)
    mat.index.name = "factor"
    return mat


def compute_ic_stats(factor_series: dict, fwd_ret_1: dict) -> dict:
    """RankIC / ICIR / IC 胜率 —— 交付卡片的核心验证指标。

    口径与 validate.validator 完全对齐：逐日 Spearman 秩相关，ICIR = mean/std（日频不年化）。
    早期卡片只印 DSR/PBO 没有 IC，等于交付了一张看不出因子好坏的卡片，这里补上。
    """
    from validate.validator import _rank_ic

    ics = []
    for t, fv in factor_series.items():
        fr = fwd_ret_1.get(t)
        if fr is None or fv is None or len(fv) == 0:
            continue
        ic = _rank_ic(fv, fr)
        if ic is not None and np.isfinite(ic):
            ics.append(float(ic))
    if not ics:
        return {"rank_ic": np.nan, "icir": np.nan, "ic_win_rate": np.nan, "n_days": 0}
    s = pd.Series(ics)
    sd = s.std()
    return {
        "rank_ic": float(s.mean()),
        "icir": float(s.mean() / sd) if sd and sd > 0 else np.nan,
        "ic_win_rate": float((s > 0).mean()),
        "n_days": int(len(s)),
    }


def backtest_stats(bt: pd.DataFrame) -> dict:
    """从回测序列提炼年化收益 / Sharpe / 最大回撤（净值口径，含成本）。"""
    out = {}
    for tag in ("gross", "net"):
        r = bt[f"ls_ret_{tag}"].dropna()
        if len(r) == 0:
            continue
        ann_ret = float((1 + r).prod() ** (252 / len(r)) - 1)
        sharpe = float(r.mean() / r.std() * np.sqrt(252)) if r.std() > 0 else np.nan
        cum = (1 + r).cumprod()
        mdd = float((cum / cum.cummax() - 1).min())
        out[tag] = {"ann_ret": ann_ret, "sharpe": sharpe, "max_dd": mdd}
    return out


def build_backtest(factor_series: dict, fwd_ret_1: dict, cost_rate: float = 0.001) -> pd.DataFrame:
    """多空组合日收益序列（含/不含成本）+ 累计。

    gross：top_n 等权下一日收益（strategy_returns_from_factor）；
    net：gross - cost_rate * 当日换手代理（用因子值排序变化近似）。
    """
    gross = strategy_returns_from_factor(factor_series, fwd_ret_1, top_n=20)
    # 换手代理：相邻日 top_n 名单变动比例（简化）
    dates = sorted(factor_series.keys())
    net = gross.copy()
    prev_picks = None
    for t in gross.index:
        fv = factor_series.get(t)
        if fv is None or prev_picks is None:
            net[t] = gross[t]
            if fv is not None:
                prev_picks = set(fv.nlargest(20).index)
            continue
        picks = set(fv.nlargest(20).index)
        if prev_picks:
            turnover = 1.0 - len(picks & prev_picks) / len(picks)
            net[t] = gross[t] - cost_rate * turnover
        prev_picks = picks
    out = pd.DataFrame({
        "date": gross.index,
        "ls_ret_gross": gross.values,
        "ls_ret_net": net.values,
    }).set_index("date")
    out["cum_gross"] = (1 + out["ls_ret_gross"]).cumprod() - 1
    out["cum_net"] = (1 + out["ls_ret_net"]).cumprod() - 1
    return out


# ---------------------------------------------------------------------------
# 编排
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--factor", required=True)
    ap.add_argument("--fcode", required=True)
    ap.add_argument("--name", default="")
    ap.add_argument("--pools", default="hs300")
    ap.add_argument("--combo", action="store_true")
    ap.add_argument("--components", default="")
    ap.add_argument("--cost-rate", type=float, default=0.001)
    ap.add_argument("--window-start", default="2020-01-01")
    # 相关性只在一个池上算（默认首池）。
    # 历史 bug（2026-08-09 修复）：correlation.csv 原写在逐池循环内，每池覆盖上一池，
    # 6 池只有最后一池活下来且文件里没有池标签 —— 前 5 池的对照因子全量重算是纯浪费
    # （实测占整轮出包约 80% 算力：每池要把 zoo+internal 4 个对照因子逐个重算一遍）。
    # 现在显式指定对照池，并把池名写进 manifest 的 corr_pool 字段。
    ap.add_argument("--corr-pool", default="",
                    help="计算相关性矩阵的池（默认 --pools 的第一个）；设为 none 则跳过相关性")
    args = ap.parse_args()

    factor = get_factor(args.factor)
    comps = [c.strip() for c in args.components.split(",") if c.strip()] if args.components else None
    ftype = "combo" if args.combo else "single"
    pool_list = [p.strip() for p in args.pools.split(",") if p.strip()]

    pkg_dir = OUT_ROOT / args.fcode
    pkg_dir.mkdir(parents=True, exist_ok=True)

    corr_pool = (args.corr_pool or pool_list[0]).strip()

    audit_records = {}
    metric_records = {}
    for pool in pool_list:
        provider = BaoStockProvider(universe=pool, history_start=args.window_start)
        fs, fwd = compute_factor_series(factor, provider)
        # 相关对照集：动物园 + 内部（排除自身）。只在 corr_pool 上算，其余池跳过。
        corr = None
        if pool == corr_pool:
            others = [f for f in (ZOO_FACTORS + INTERNAL_FACTORS) if f != args.factor]
            corr = compute_correlation(fs, provider, others, self_name=args.factor)
        bt = build_backtest(fs, fwd, cost_rate=args.cost_rate)
        ic_stats = compute_ic_stats(fs, fwd)
        bt_stats = backtest_stats(bt)
        # 过拟合审计
        gross = bt["ls_ret_gross"].dropna().values
        result = audit(gross, n_trials=8, n_splits=12)

        # 写文件
        if corr is not None:
            corr.to_csv(pkg_dir / "correlation.csv")
        bt.to_csv(pkg_dir / f"backtest_{pool}.csv")
        with open(pkg_dir / f"metrics_{pool}.json", "w", encoding="utf-8") as f:
            json.dump({"pool": pool, "ic": ic_stats, "backtest": bt_stats,
                       "cost_rate": args.cost_rate}, f, ensure_ascii=False, indent=2,
                      default=lambda o: None if (isinstance(o, float) and not np.isfinite(o)) else str(o))
        audit_records[pool] = result
        metric_records[pool] = {"ic": ic_stats, "bt": bt_stats}
        print(f"  [{pool}] RankIC={ic_stats['rank_ic']:+.4f} ICIR={ic_stats['icir']:+.2f} "
              f"胜率={ic_stats['ic_win_rate']:.1%} n={ic_stats['n_days']}", flush=True)

    # 过拟合审计：循环结束后统一写一次。
    # 历史 bug（2026-08-09 修复）：原写在循环内，每池覆盖上一池 → 落盘的是"最后一个池"的
    # DSR/PBO，且文件里没有池标签，消费方（export_to_strategy_json.py）会误以为是包级结论。
    # 现在顶层扁平字段固定取主池（= pools 第一个，与 manifest.universe 一致，可复现），
    # 并新增 by_pool 给出逐池全景；扁平键名保持不变，下游无需改。
    primary = pool_list[0]
    _pri = audit_records.get(primary, {})
    with open(pkg_dir / "overfit_audit.json", "w", encoding="utf-8") as f:
        json.dump({"pool": primary,
                   "dsr": _pri.get("dsr"), "pbo": _pri.get("pbo"),
                   "verdict": _pri.get("verdict"),
                   "n_trials": 8, "n_splits": 12,
                   "by_pool": {p: {"dsr": r.get("dsr"), "pbo": r.get("pbo"),
                                   "verdict": r.get("verdict")}
                               for p, r in audit_records.items()}},
                  f, ensure_ascii=False, indent=2)

    # manifest
    manifest = render_manifest(
        fcode=args.fcode, factor=args.factor, version="1.0.0", doc_rev=1,
        status="current", supersedes=None, components=comps,
        generated=pd.Timestamp.now().strftime("%Y-%m-%d"),
        contract_version=1, provider="baostock", adj_policy="qfq",
        universe=pool_list[0], pools=pool_list,
        # correlation.csv 是"单池"结论，不是六池平均 —— 把池名显式写进 manifest，
        # 免得消费方把某一个池的相关性当成包级结论（旧版就是这么悄悄误导的）。
        corr_pool=corr_pool,
        window_start=args.window_start,
        # 市值口径写死为 PIT：2026-08-08 前用的是面板 market_cap 快照列（非 PIT），
        # 中性化回归会把未来收益注入残差。修复见 validate/validator.py::_neutralize_cross_section。
        neutralization="industry+mktcap(PIT: amount/turnover)", pit_certified=True,
        reproduce=f"FF_PROVIDER=baostock python scripts/real_research.py --factor {args.factor} --pool {pool_list[0]}",
    )
    (pkg_dir / "manifest.yaml").write_text(manifest, encoding="utf-8")

    # card.md（简化渲染；消费指引取因子已知限制）
    card = _render_card(args, factor, audit_records, pool_list, metric_records)
    (pkg_dir / "card.md").write_text(card, encoding="utf-8")

    # 同步 registry + index
    _upsert_registry(REGISTRY_CSV, {
        "fcode": args.fcode, "name": args.name or args.factor, "type": ftype,
        "components": ",".join(comps) if comps else "", "status": "current",
        "supersedes": "", "created": pd.Timestamp.now().strftime("%Y-%m-%d"), "note": "",
    })
    _render_index()
    print(f"✅ 交付包已生成：{pkg_dir}")


def _fmt(v, spec=".4f", dash="—"):
    try:
        if v is None or (isinstance(v, float) and not np.isfinite(v)):
            return dash
        return format(float(v), spec)
    except Exception:
        return dash


def _pass(cond) -> str:
    if cond is None:
        return "—"
    return "✅" if cond else "❌"


def _render_card(args, factor, audit_records: dict, pool_list: list,
                 metric_records: Optional[dict] = None) -> str:
    r = audit_records.get(pool_list[0], {})
    mr = (metric_records or {}).get(pool_list[0], {})
    ic = mr.get("ic", {})
    bt = mr.get("bt", {})
    net = bt.get("net", {})
    gross = bt.get("gross", {})

    rank_ic = ic.get("rank_ic")
    icir = ic.get("icir")
    win = ic.get("ic_win_rate")
    dsr = r.get("dsr")
    pbo = r.get("pbo")

    combo_line = ""
    if args.combo:
        method = getattr(factor, "combination_method", "等权（成分 z-score 后按方向系数平均）")
        signs = getattr(factor, "signs", None)
        combo_line = (f"\n- 是否组合：是 | combination_method：{method} | "
                      f"成分：{args.components or ','.join(getattr(factor, 'components', []))}"
                      + (f" | 方向系数：{signs}" if signs else "") + "\n")

    direction = "—"
    if rank_ic is not None and np.isfinite(rank_ic or np.nan):
        direction = "正向（因子值越大，未来收益越高）" if rank_ic > 0 else "反向（因子值越大，未来收益越低）"

    # 财报类因子（带财务 pit_fields）专属警示：高 IC 低超额 / 方向或反向 / 年度化口径
    pit = getattr(factor, "pit_fields", None) or []
    fin_caveat = ""
    if pit and ({"cogs", "inventory", "accounts_receivable", "revenue"} & set(pit)):
        fin_caveat = (
            "\n## 财报类因子特别警示\n"
            "- **披露日口径**：值取自截至 as_of 最新*已披露*财报（AkShare NOTICE_DATE 真实公告日对齐，无前视）；"
            "因子值随披露日阶梯跳变是财报特性，非前视。\n"
            "- **高 IC 低超额陷阱**：财报类因子（存货/应收周转天数）常与质量/价值因子高度共线，"
            "RankIC 可能为正但多空净超额极低；方向亦可能反向（高周转=运营高效 OR 渠道压货=质量差，经济含义非单调）。"
            "落地前务必以分池 IC + 多头超额为最终判据，且勿与本池已装价值/质量因子重复入模。\n"
            "- **年度化口径**：cogs/revenue 为流量项，按自身 statDate 月份年化"
            "（Q1→×4 / H1→×2 / Q3→×4/3 / 年报→×1），存货/应收为时点值不年化，使季/年报可比。\n"
        )

    # 分池 IC 表（决策5：覆盖全6池，不再只测 sz50）
    pool_rows = ""
    for p in pool_list:
        m = (metric_records or {}).get(p, {}).get("ic", {})
        pool_rows += (f"| {p} | {_fmt(m.get('rank_ic'))} | {_fmt(m.get('icir'), '.3f')} | "
                      f"{_fmt(m.get('ic_win_rate'), '.1%')} | {m.get('n_days', '—')} |\n")

    return f"""# {args.name or args.factor}（{args.fcode}）

- f-code：{args.fcode}
- 类别 / 方向：{direction}
- 逻辑一句话：{getattr(factor, '__doc__', None) or getattr(factor, 'name', args.factor)}
- 是否组合：{'是' if args.combo else '否'}{combo_line}
## 分池 IC（全样本，决策5：覆盖 {len(pool_list)} 池）
| 池 | RankIC | ICIR | IC胜率 | 样本日 |
|---|---|---|---|---|
{pool_rows}
> 注：RankIC 量级偏低属常态（A股技术因子半衰期~18个月，见 v75 复盘）。**质量高低由策略组选择，内部不设 |IC|≥0.03 出库门槛**（用户决策4）。

## 主池验证指标（池：{pool_list[0]}，窗口 {args.window_start} 起）
| 指标 | 值 | 说明 |
|---|---|---|
| RankIC | {_fmt(rank_ic)} | 参考，非门槛 |
| ICIR | {_fmt(icir, '.3f')} | 参考，非门槛 |
| IC 胜率 | {_fmt(win, '.1%')} | 参考，非门槛 |
| 年化收益(净) | {_fmt(net.get('ann_ret'), '.2%')} | >0 即正向 |
| Sharpe(净) | {_fmt(net.get('sharpe'), '.2f')} | 参考 |
| 最大回撤(净) | {_fmt(net.get('max_dd'), '.2%')} | 关注成本敏感 |
| 年化收益(毛) | {_fmt(gross.get('ann_ret'), '.2%')} | 参考 |
| DSR | {_fmt(dsr, '.3f')} | **过拟合门禁** ≥0.95 |
| PBO | {_fmt(pbo, '.3f')} | **过拟合门禁** <0.25 |
| 审计结论 | {r.get('verdict')} | PASS=未过拟合 |

> 交易成本假设：单边 {args.cost_rate:.2%}（按 top20 名单变动比例计换手）。
> 毛/净差距大 = 该因子换手高、成本敏感，落地前务必核算真实费率。
> DSR/PBO 是**过拟合审计**（防数据窥探），与"因子质量高低"是两回事；质量筛选交策略组。

## 框架一致性字段
- 中性化状态：industry+mktcap(PIT: amount/turnover 现算流通市值)
- PIT 认证：true
- 主场池：{pool_list[0]}（详见 factor_universe_matrix；分池 IC 见上表）

## 消费指引
- 因子值已中性化，可直接 load 进选股模型。
- 适用池子：{', '.join(pool_list)}；不适用：见换池反转预警。
- 成本敏感性：净 alpha 对换手敏感，低换手场景优先。
- 冗余关系：见 correlation.csv（ρ≥0.7 勿重复入模）；该矩阵在 **{args.corr_pool or pool_list[0]}** 单池上计算，非六池平均，换池后相关性可能变化。
- 复现命令：FF_PROVIDER=baostock python scripts/real_research.py --factor {args.factor} --pool {pool_list[0]}

## 聚合视图（本因子在聚合交付中的位置）
- 机器可读发货形态：`../strategy_export/stock_factors.json`（条目 name={args.fcode}，供策略组阶段 0 消费）
- 跨池检验记录：`../universe_matrix/ic_matrix_<最新日期>.csv` 及同批 icir / dsr 三表（本因子行以矩阵实际收录为准）
- 说明：上述为同一交付物的聚合 / 检验视图，由 `scripts/export_to_strategy_json.py` / `scripts/factor_universe_matrix.py` 生成，与本卡同源，不另立交付编号。
- 已知陷阱：特定牛熊阶段 / 流动性枯竭。
{ fin_caveat }
"""


def _render_index():
    if not REGISTRY_CSV.exists():
        return
    import csv
    with open(REGISTRY_CSV, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    lines = ["# 因子库索引（_INDEX.md）\n", "| f-code | 名称 | 类别 | 成分 | 状态 | 创建 |\n",
             "|---|---|---|---|---|---|"]
    for r in rows:
        lines.append(f"| {r['fcode']} | {r['name']} | {r['type']} | {r['components']} | "
                     f"{r['status']} | {r['created']} |")
    INDEX_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
