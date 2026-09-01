"""第三条腿 C1：特征工厂（factor feature factory）。

为纪律化 ML 挖掘提供候选特征矩阵（见 docs/PLAN_THIRD_LEG.md 路线图 C1）。
每个特征是一个 (sub_panel, as_of) -> Series 生成器，输出 asset-indexed 的截面值；
特征工厂本身不直接交付为因子，而是 ML 挖掘的"原料"——ML 在约束下从这些特征里
挑有效组合（见 C2/C3）。

前向防护：所有特征只用 as_of 及之前数据（slice_panel_to_date 双保险），
与内部因子的 Factor 协议同一套纪律。CI 通过 build_feature_matrix 的"全量 vs 切片
等价"测试保证无前视。

特征菜单（覆盖动量/反转/波动/流动性/价格位置/微观结构/规模，共 18 个）：
  mom_5/10/20/60/120, rev_5/10/20, vol_5/20/60, vol_ratio_20_60,
  turnover_avg_20, amt_mom_20, gap_overnight, maxret_20, skew_ret_60,
  illiq_20, price_dist_high_120, beta_60, log_mktcap
"""
from __future__ import annotations
from typing import Callable, Optional
import numpy as np
import pandas as pd

from factors.interface import slice_panel_to_date, winsorize_mad, zscore_cross_section
from data.pit import pit_float_mcap  # PIT 流通市值现算（替代脏 market_cap 快照）


# ---------- 特征注册表 ----------
FeatureFn = Callable[[pd.DataFrame, object], pd.Series]
_FEATURE_REGISTRY: dict[str, FeatureFn] = {}


def _asof_assets(sub: pd.DataFrame, as_of) -> list:
    """返回 as_of（或最近可用日）截面上的资产列表。"""
    dates = sub.index.get_level_values("date")
    if as_of in set(dates):
        return list(sub.xs(as_of, level="date").index)
    avail = sorted(d for d in dates.unique() if d <= as_of)
    if not avail:
        return []
    return list(sub.xs(avail[-1], level="date").index)


def _pick(sub: pd.DataFrame, *cands) -> str:
    """返回 sub 中第一个存在的列名（兼容 turnover/turn 等命名差异）。"""
    for c in cands:
        if c in sub.columns:
            return c
    raise KeyError("/".join(cands))


def _piv(sub: pd.DataFrame, col: str) -> pd.DataFrame:
    """把某列从 (date,asset) 面板展开成 date×asset 矩阵（按日期排序）。"""
    return sub[col].unstack("asset").sort_index()


def _last(piv: pd.DataFrame, as_of) -> pd.Series:
    """取 as_of（或最近可用日）那一行，返回 asset-indexed 序列。"""
    if as_of in piv.index:
        return piv.loc[as_of]
    return piv.iloc[-1]


def register_feature(name: str):
    """装饰器：注册特征生成器，并包裹异常兜底（缺列/数据不足 -> 该 as_of 全 NaN）。"""
    def deco(fn: FeatureFn) -> FeatureFn:
        def safe(sub, as_of):
            try:
                return fn(sub, as_of)
            except Exception:
                return pd.Series(np.nan, index=_asof_assets(sub, as_of), name=name)
        safe.__name__ = name
        _FEATURE_REGISTRY[name] = safe
        return safe
    return deco


def list_features() -> list[str]:
    return list(_FEATURE_REGISTRY.keys())


def get_feature(name: str) -> FeatureFn:
    return _FEATURE_REGISTRY[name]


# ---------- 特征生成器 ----------
@register_feature("mom_5")
def f_mom_5(sub, as_of):
    p = _piv(sub, "close")
    return _last(p / p.shift(5) - 1.0, as_of)

@register_feature("mom_10")
def f_mom_10(sub, as_of):
    p = _piv(sub, "close")
    return _last(p / p.shift(10) - 1.0, as_of)

@register_feature("mom_20")
def f_mom_20(sub, as_of):
    p = _piv(sub, "close")
    return _last(p / p.shift(20) - 1.0, as_of)

@register_feature("mom_60")
def f_mom_60(sub, as_of):
    p = _piv(sub, "close")
    return _last(p / p.shift(60) - 1.0, as_of)

@register_feature("mom_120")
def f_mom_120(sub, as_of):
    p = _piv(sub, "close")
    return _last(p / p.shift(120) - 1.0, as_of)

@register_feature("rev_5")
def f_rev_5(sub, as_of):
    p = _piv(sub, "close")
    return _last(-(p / p.shift(5) - 1.0), as_of)

@register_feature("rev_10")
def f_rev_10(sub, as_of):
    p = _piv(sub, "close")
    return _last(-(p / p.shift(10) - 1.0), as_of)

@register_feature("rev_20")
def f_rev_20(sub, as_of):
    p = _piv(sub, "close")
    return _last(-(p / p.shift(20) - 1.0), as_of)

@register_feature("vol_5")
def f_vol_5(sub, as_of):
    p = _piv(sub, "close").pct_change(1)
    return _last(p.rolling(5).std(), as_of)

@register_feature("vol_20")
def f_vol_20(sub, as_of):
    p = _piv(sub, "close").pct_change(1)
    return _last(p.rolling(20).std(), as_of)

@register_feature("vol_60")
def f_vol_60(sub, as_of):
    p = _piv(sub, "close").pct_change(1)
    return _last(p.rolling(60).std(), as_of)

@register_feature("vol_ratio_20_60")
def f_vol_ratio_20_60(sub, as_of):
    p = _piv(sub, "close").pct_change(1)
    r20 = p.rolling(20).std()
    r60 = p.rolling(60).std()
    return _last(r20 / r60, as_of)

@register_feature("turnover_avg_20")
def f_turnover_avg_20(sub, as_of):
    p = _piv(sub, _pick(sub, "turnover", "turn"))
    return _last(p.rolling(20).mean(), as_of)

@register_feature("amt_mom_20")
def f_amt_mom_20(sub, as_of):
    p = _piv(sub, "amount")
    return _last(p / p.shift(20) - 1.0, as_of)

@register_feature("gap_overnight")
def f_gap_overnight(sub, as_of):
    o = _piv(sub, "open")
    c = _piv(sub, "close")
    return _last(o / c.shift(1) - 1.0, as_of)

@register_feature("maxret_20")
def f_maxret_20(sub, as_of):
    p = _piv(sub, "close").pct_change(1)
    return _last(p.rolling(20).max(), as_of)

@register_feature("skew_ret_60")
def f_skew_ret_60(sub, as_of):
    p = _piv(sub, "close").pct_change(1)
    return _last(p.rolling(60).skew(), as_of)

@register_feature("illiq_20")
def f_illiq_20(sub, as_of):
    ret = _piv(sub, "close").pct_change(1)
    amt = _piv(sub, "amount")
    illiq = ret.abs() / amt.replace(0, np.nan)
    return _last(illiq.rolling(20).mean(), as_of)

@register_feature("price_dist_high_120")
def f_price_dist_high_120(sub, as_of):
    p = _piv(sub, "close")
    return _last(p / p.rolling(120).max() - 1.0, as_of)

@register_feature("beta_60")
def f_beta_60(sub, as_of):
    p = _piv(sub, "close")
    ret = p.pct_change(1)
    mkt = ret.mean(axis=1)
    w = 60
    out = {}
    for a in ret.columns:
        s = ret[a]
        dfw = pd.concat([s, mkt], axis=1).dropna().tail(w)
        if len(dfw) < max(30, w // 2):
            out[a] = np.nan
        else:
            cov = dfw.iloc[:, 0].cov(dfw.iloc[:, 1])
            var = dfw.iloc[:, 1].var()
            out[a] = cov / var if var and not np.isnan(var) else np.nan
    return pd.Series(out, name="beta_60")

@register_feature("log_mktcap")
def f_log_mktcap(sub, as_of):
    # 🔴 2026-09-01 PIT 体检：原读脏 market_cap 快照（nunique==1，今日市值回填全历史）
    # 改为 PIT 流通市值现算（amount/(turnover/100)，取前一日近 5 日中位数）。
    mcap = pit_float_mcap(sub, as_of)
    if mcap is None or len(mcap) == 0:
        return pd.Series(dtype=float)
    return np.log(mcap.where(mcap > 0))


# ---------- 矩阵装配 ----------
def build_feature_matrix(panel: pd.DataFrame, as_of_date,
                         feature_names: Optional[list[str]] = None,
                         standardize: bool = True) -> pd.DataFrame:
    """返回 as_of 截面特征矩阵：行 = asset，列 = feature。

    - 前向防护：内部 slice_panel_to_date 只保留 as_of 及之前。
    - standardize=True：先以列中位数填 NaN，再 MAD 去极值 + 截面 Z-score（ML 友好）。
    - 任一特征在 as_of 缺失/异常 -> 该列全 NaN，不影响其他特征。
    """
    as_of = pd.Timestamp(as_of_date)
    sub = slice_panel_to_date(panel, as_of)
    names = feature_names or list_features()
    cols = {}
    for nm in names:
        fn = _FEATURE_REGISTRY[nm]
        cols[nm] = fn(sub, as_of)
    mat = pd.DataFrame(cols)
    if standardize:
        for c in mat.columns:
            col = mat[c].fillna(mat[c].median())
            # 全 NaN 特征：保持 NaN（不伪造成均值 0，下游应丢弃）
            if col.notna().sum() == 0:
                continue
            # 近常数特征（std≈0）无截面区分度：直接置 0，
            # 避免 zscore 近常数除零产生浮点垃圾值
            if col.std() < 1e-12 * (col.abs().mean() + 1e-12):
                mat[c] = 0.0
                continue
            mat[c] = zscore_cross_section(winsorize_mad(col))
    return mat
