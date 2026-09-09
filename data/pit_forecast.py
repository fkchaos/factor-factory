"""PIT 业绩预告服务层（Phase 1 · 2026-09-09）。

数据源：AkShare `stock_yjyg_em`（东财业绩预告，按报告期拉全市场）。
PIT 依据：每条预告带 **公告日期**，严格按 `pubDate <= as_of` 过滤 → 零前视。
          预告发布后阶梯生效（与财报因子同语义），至下一份预告/正式财报覆盖为止。

🔴 实测约束（2026-09-09 全历史拉取验证，勿凭假定推翻）：
1. **覆盖率低**：hs300 内每个报告期仅 **28~36%** 的公司发布预告。因子截面必然稀疏，
   出包卡片须注明；不可用"全市场补齐/前填"等手法粉饰覆盖率。
2. **无修正历史**：同一 (股票, 报告期) 在数据源中**恒为 1 条**（AkShare 已按最新去重）。
   → **预告修正动量（revision momentum）类因子在本源上不可实现**，勿重复尝试。
   若要修正类信号，需换源（如巨潮/万得预告修正明细）。
3. **覆盖随报告期波动**：年报(1231)最广(约2900家) > 中报(0630,约1900家) >>
   一季/三季（2023 年全面注册制后骤降，Q1 仅 200~600 家）。
4. 预告数值为**年初至报告期末累计值**（如"预计1-3月净利润"），故流量项须按报告期
   月份年化，口径与 `factors/fundamentals.py::_ann` 一致（3→4, 6→2, 9→4/3, 12→1）。

取数成本：全历史 26 个报告期约 3.5 分钟（对比财报 prewarm hs300 的 111 分钟），
落单文件 parquet 缓存，不必逐票预热。
"""
from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pandas as pd

CACHE_PATH = Path(".cache/akshare/forecast_all.parquet")

# 预告类型 → 分档打分。语义：正=业绩改善，负=恶化，0=不确定。
# 注：「减亏」虽仍亏损但边际改善记正分，「增亏」记负分（勿与「首亏/续亏」混淆）。
KIND_SCORE = {
    "预增": 3.0,
    "扭亏": 2.5,
    "略增": 1.0,
    "减亏": 1.0,
    "续盈": 0.5,
    "不确定": 0.0,
    "略减": -1.0,
    "续亏": -1.5,
    "增亏": -2.0,
    "首亏": -2.5,
    "预减": -3.0,
}

# 报告期月份 → 年化系数（预告值为年初至报告期末累计数）
_ANN_K = {3: 4.0, 6: 2.0, 9: 4.0 / 3.0, 12: 1.0}


def _norm(code: str) -> str:
    """AkShare 6 位纯数字代码 → 系统统一 `000001.SZ` 格式。"""
    from data.contract import normalize_code

    c = str(code).strip().zfill(6)
    try:
        return normalize_code(c)
    except Exception:  # 极端兜底：按号段判交易所
        if c.startswith(("60", "68", "9")):
            return c + ".SH"
        if c.startswith(("4", "8")):
            return c + ".BJ"
        return c + ".SZ"


def pull_all(refresh: bool = False, verbose: bool = True) -> pd.DataFrame:
    """拉全历史业绩预告并规范化落盘（缓存 `.cache/akshare/forecast_all.parquet`）。

    返回规范化长表：asset / pubDate / period / fc_np / yoy / kind / kind_score / prev_np
    """
    if CACHE_PATH.exists() and not refresh:
        return pd.read_parquet(CACHE_PATH)

    import akshare as ak

    periods = [
        f"{y}{m:02d}{d:02d}"
        for y in range(2020, 2027)
        for m, d in [(3, 31), (6, 30), (9, 30), (12, 31)]
    ]
    frames = []
    for p in periods:
        try:
            d = ak.stock_yjyg_em(date=p)
        except Exception as e:
            if verbose:
                print(f"[forecast] {p} 拉取失败：{e!r}", flush=True)
            continue
        d["报告期"] = p
        frames.append(d)
        if verbose:
            print(f"[forecast] {p}: {len(d)}", flush=True)
    if not frames:
        raise RuntimeError("业绩预告全历史拉取为空（AkShare 接口异常？）")
    raw = pd.concat(frames, ignore_index=True)
    out = _normalize(raw)
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(CACHE_PATH)
    if verbose:
        print(f"[forecast] 落盘 {CACHE_PATH} 共 {len(out)} 条", flush=True)
    return out


def _normalize(raw: pd.DataFrame) -> pd.DataFrame:
    """原始全市场宽表 → 规范化长表（只保留「归母净利润」口径预告）。"""
    df = raw.copy()
    # 只取归母净利润口径（另有扣非/营收/每股收益等，混用会污染量纲）
    mask = df["预测指标"].astype(str).str.contains("归属于上市公司股东的净利润", na=False)
    df = df[mask].copy()
    df["asset"] = df["股票代码"].map(_norm)
    df["pubDate"] = pd.to_datetime(df["公告日期"], errors="coerce")
    df["period"] = pd.to_datetime(df["报告期"], errors="coerce")
    df["fc_np"] = pd.to_numeric(df["预测数值"], errors="coerce")
    df["yoy"] = pd.to_numeric(df["业绩变动幅度"], errors="coerce")
    df["prev_np"] = pd.to_numeric(df["上年同期值"], errors="coerce")
    df["kind"] = df["预告类型"].astype(str).str.strip()
    df["kind_score"] = df["kind"].map(KIND_SCORE)
    # 用预测数值与上年同期值兜底算同比（yoy 列在「不确定」等类型常缺失）
    with np.errstate(divide="ignore", invalid="ignore"):
        calc = (df["fc_np"] / df["prev_np"].abs() - 1.0) * 100.0
    df["np_yoy_calc"] = calc.where(np.isfinite(calc))
    # 年化预告净利（流量项，按报告期月份）
    df["fc_np_ann"] = df["fc_np"] * df["period"].dt.month.map(_ANN_K)

    df = df[df["pubDate"].notna() & df["period"].notna()]
    df = df[df["fc_np"].notna() | df["yoy"].notna() | df["kind_score"].notna()]
    cols = ["asset", "pubDate", "period", "fc_np", "fc_np_ann", "yoy",
            "np_yoy_calc", "prev_np", "kind", "kind_score"]
    df = df[cols].sort_values(["asset", "pubDate"]).reset_index(drop=True)
    # 同一 asset 同一 pubDate 可能有多个报告期 → 保留报告期最新的一条
    df = df.drop_duplicates(subset=["asset", "pubDate"], keep="last")
    return df.reset_index(drop=True)


class PitForecastService:
    """业绩预告 PIT 服务：按公告日对齐，提供事件驱动阶梯面板（快路径）。"""

    def __init__(self, assets=None, table: pd.DataFrame | None = None):
        self._tbl = table if table is not None else pull_all(verbose=False)
        if assets is not None:
            want = set(assets)
            self._tbl = self._tbl[self._tbl["asset"].isin(want)]
        self._by_asset: dict[str, pd.DataFrame] = {}
        for a, g in self._tbl.groupby("asset", sort=False):
            self._by_asset[a] = g.sort_values("pubDate")

    # ---------- 逐日慢路径（供单测 / 独立调用）----------
    def snapshot(self, assets, as_of, with_dates: bool = False):
        """返回 {asset: {field: value}}，严格 pubDate <= as_of（PIT 红线）。"""
        t = pd.Timestamp(as_of)
        out: dict[str, dict] = {}
        for a in assets:
            g = self._by_asset.get(a)
            if g is None or g.empty:
                out[a] = {}
                continue
            g = g[g["pubDate"] <= t]
            if g.empty:
                out[a] = {}
                continue
            row = g.iloc[-1]
            out[a] = {c: row[c] for c in
                      ["period", "fc_np", "fc_np_ann", "yoy", "np_yoy_calc",
                       "prev_np", "kind", "kind_score"]}
            if with_dates:
                out[a]["pubDate"] = row["pubDate"]
        return out

    def disclosure_dates(self, asset) -> pd.DatetimeIndex:
        g = self._by_asset.get(asset)
        return pd.DatetimeIndex(g["pubDate"]) if g is not None else pd.DatetimeIndex([])

    # ---------- 事件驱动快路径（O(披露次数)，非 O(交易日×资产)）----------
    def stepped(self, dates, assets, field: str) -> pd.DataFrame:
        """返回 date × asset 阶梯面板：预告在公告日跳变，之后沿用至下一条。"""
        dates = pd.DatetimeIndex(dates)
        cols = {}
        for a in assets:
            g = self._by_asset.get(a)
            if g is None or g.empty:
                continue
            g = g[(g["pubDate"] >= dates[0]) & (g["pubDate"] <= dates[-1])]
            ser = pd.Series(g[field].to_numpy(), index=pd.DatetimeIndex(g["pubDate"]))
            ser = ser[ser.notna()]
            if ser.empty:
                continue
            # 公告当日即生效（与 snapshot 的 pubDate<=as_of 口径一致），之后 ffill
            cols[a] = ser.reindex(dates.union(ser.index)).ffill().reindex(dates)
        return pd.DataFrame(cols, index=dates) if cols else pd.DataFrame(index=dates)


_default_svc: PitForecastService | None = None


def default_service(assets=None) -> PitForecastService:
    """进程内共享单例（披露历史静态，不随 as_of 变化，安全复用）。"""
    global _default_svc
    if _default_svc is None:
        _default_svc = PitForecastService()
    return _default_svc
