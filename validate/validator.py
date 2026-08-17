"""因子验证器（validate_factor）。

单因子体检指标（对齐 RESEARCH_LOG R2026-0804-02,05）：
- RankIC / ICIR / IC 胜率（逐日）
- 衰减曲线（1 / 5 / 10 / 20 日 RankIC）
- 分层单调性（5 组多空平均收益，肉眼验单调）
- 换手率 / 成本敏感性（占位）
- DSR / PBO 过拟合审计（接口预留，P1 落地；见计划）

预处理三件套在验证时施加：MAD 去极值 -> 截面 Z-score（行业/市值中性化需额外数据，接口预留）。
"""
from __future__ import annotations
from typing import Any, Optional

import numpy as np
import pandas as pd
from scipy import stats

from factors.interface import (
    Factor, winsorize_mad, zscore_cross_section, neutralize,
)
from engine.interface import BacktestConfig, prepare_panel_for_factor
from validate.overfit_audit import (
    strategy_returns_from_factor, deflated_sharpe, probability_of_backtest_overfit,
)

# DSR 多试次数：诚实估计本生产线至今评估过的策略/方向/参数变体总数
# （含 overnight 翻转前后两个方向、组合加权变体等；n_trials 越大门槛越严）
N_TRIALS_DEFAULT = 8


def _neutralize_cross_section(fv: pd.Series, panel: pd.DataFrame, t, provider) -> pd.Series:
    """截面行业+市值中性化（回归残差）。数据不可得时逐级降级：
    有市值 → 仅市值中性化；无市值/样本不足 → 原样返回。

    🔴 市值口径（2026-08-08 修，勿回退）
    ------------------------------------
    原实现读面板的 `market_cap` 列。该列**不是 PIT**：provider 把"今日"市值快照
    `map` 到全部历史日期（时序 nunique==1），详见 `data/contract.py` PIT 分级与
    `data/pit.py` 头部实测数据。

    在中性化里用它，危害比在因子里用它**更隐蔽也更严重**：中性化是**回归扣除**，
    `residual = fv − β·log(mcap_今日)`，而 `log(mcap_今日) ≈ log(mcap_t) + t 之后的累计收益`，
    于是残差里被**注入了 −β×未来收益**——这不是噪声，是货真价实的前视注入，会系统性
    偏移 IC。改用 `data.pit.pit_float_mcap()`（当日 amount/换手率 现算）。

    降级策略刻意收紧：PIT 市值算不出来时**跳过市值中性化**（只做行业），
    **绝不回退到 `market_cap` 列**——静默回退到脏数据正是当初埋雷的方式。
    """
    from data.pit import pit_float_mcap  # 局部导入：避免 validate ← data 顶层循环依赖

    mc = pit_float_mcap(panel, t, lookback=5)
    if mc.empty:
        return fv
    mcap = mc.reindex(fv.index).dropna()
    if len(mcap) < 10 or (mcap <= 0).any():
        return fv
    log_mktcap = np.log(mcap)
    dummies = None
    try:
        ind_map = getattr(provider, "get_industries", lambda: {})() or {}
        if ind_map:
            ind = pd.Series({a: ind_map.get(a, "UNKNOWN") for a in fv.index})
            dummies = pd.get_dummies(ind).astype(float)
    except Exception:
        dummies = None
    try:
        return neutralize(fv.loc[mcap.index], dummies, log_mktcap)
    except Exception:
        return fv


def _benchmark_returns(fwd_ret_1: dict, mode: str) -> pd.Series:
    """基准策略收益序列（PBO 候选集用）：
    - equal：全截面等权（市场基准）
    - reversal：昨收最低 20% 等权（1 日反转）
    - momentum：昨收最高 20% 等权（1 日动量）
    """
    rets = {}
    for t, fr in fwd_ret_1.items():
        fr = fr.dropna()
        if len(fr) < 5:
            continue
        if mode == "equal":
            rets[t] = float(fr.mean())
        elif mode == "reversal":
            rets[t] = float(fr.nsmallest(max(1, len(fr) // 5)).mean())
        elif mode == "momentum":
            rets[t] = float(fr.nlargest(max(1, len(fr) // 5)).mean())
    return pd.Series(rets).sort_index()


def _rank_ic(factor: pd.Series, fwd_ret: pd.Series) -> float:
    common = factor.index.intersection(fwd_ret.index)
    if len(common) < 5:
        return np.nan
    return stats.spearmanr(factor.loc[common], fwd_ret.loc[common]).correlation


def validate_factor(factor: Factor, provider: Any,
                    config: Optional[BacktestConfig] = None, fields=None) -> dict:
    config = config or BacktestConfig()
    fields = fields or ["open", "high", "low", "close", "volume", "amount", "market_cap"]

    panel = provider.get_panel(fields, None, None)
    dates = sorted(panel.index.get_level_values("date").unique())
    N = len(dates)

    factor_series: dict = {}
    fwd_ret_1: dict = {}
    fwd_ret_n: dict[int, dict] = {h: {} for h in (5, 10, 20)}

    for idx, t in enumerate(dates):
        ctx = {"start": str(dates[max(0, idx - config.train_days)])}
        sub = prepare_panel_for_factor(provider, factor, t, fields, ctx)
        fv = factor.compute(sub, t, ctx).dropna()
        # 预处理：MAD 去极值 -> 行业/市值中性化（数据可得时）-> 截面 Z
        fv = winsorize_mad(fv)
        fv = _neutralize_cross_section(fv, panel, t, provider)
        fv = zscore_cross_section(fv)
        factor_series[t] = fv

        close_t = panel.xs(t, level="date")["close"]
        if idx + 1 < N:
            t1 = dates[idx + 1]
            close_t1 = panel.xs(t1, level="date")["close"]
            fwd_ret_1[t] = close_t1 / close_t - 1.0
        for h in fwd_ret_n:
            if idx + h < N:
                th = dates[idx + h]
                close_th = panel.xs(th, level="date")["close"]
                fwd_ret_n[h][t] = close_th / close_t - 1.0

    # 逐日 RankIC
    ics = []
    for t in factor_series:
        if t in fwd_ret_1:
            ic = _rank_ic(factor_series[t], fwd_ret_1[t])
            if np.isfinite(ic):
                ics.append(ic)
    ics = pd.Series(ics)
    rank_ic = ics.mean()
    icir = rank_ic / ics.std() if ics.std() > 0 else np.nan
    ic_win = (ics > 0).mean()

    # 衰减
    decay = {}
    for h, m in fwd_ret_n.items():
        seq = []
        for t in factor_series:
            if t in m:
                ic = _rank_ic(factor_series[t], m[t])
                if np.isfinite(ic):
                    seq.append(ic)
        decay[f"ic_{h}d"] = np.mean(seq) if seq else np.nan

    # 分层单调性（摊平所有 date-asset 对，5 组平均收益）
    flat_f, flat_r = [], []
    for t in factor_series:
        if t in fwd_ret_1:
            f = factor_series[t]
            r = fwd_ret_1[t]
            common = f.index.intersection(r.index)
            flat_f.extend(f.loc[common].values)
            flat_r.extend(r.loc[common].values)
    flat_f = np.array(flat_f, dtype=float)
    flat_r = np.array(flat_r, dtype=float)
    if len(flat_f) > 50:
        qr = pd.qcut(flat_f, 5, labels=False, duplicates="drop")
        grp_ret = [float(flat_r[qr == g].mean()) if (qr == g).any() else np.nan
                   for g in range(5)]
    else:
        grp_ret = [np.nan] * 5

    # DSR / PBO 过拟合审计（Bailey & Lopez de Prado 2014 / 2015）：
    # - DSR：由 top_n 等权策略收益序列计算经多试打折的真实夏普为正的概率；
    # - PBO：候选集 = [本因子, 等权, 1日反转, 1日动量]，CSCV 组合划分下
    #   IS 最优在 OOS 掉到中位数以下的概率（>0.5 严重过拟合）。
    rets_main = strategy_returns_from_factor(factor_series, fwd_ret_1, top_n=config.top_n)
    dsr = deflated_sharpe(rets_main.values, n_trials=N_TRIALS_DEFAULT)
    bench = {m: _benchmark_returns(fwd_ret_1, m) for m in ("equal", "reversal", "momentum")}
    align = rets_main.index
    cand = [rets_main] + [bench[m].reindex(align) for m in bench]
    cand = np.vstack([c.values for c in cand])
    pbo = probability_of_backtest_overfit(cand, n_splits=12)

    return {
        "rank_ic": float(rank_ic) if np.isfinite(rank_ic) else np.nan,
        "icir": float(icir) if np.isfinite(icir) else np.nan,
        "ic_win_rate": float(ic_win) if np.isfinite(ic_win) else np.nan,
        "n_obs": int(len(ics)),
        "decay": {k: (float(v) if np.isfinite(v) else np.nan) for k, v in decay.items()},
        "quantile_returns": grp_ret,
        # DSR / PBO 过拟合审计（因子入库门禁）
        "dsr": float(dsr) if np.isfinite(dsr) else None,
        "pbo": float(pbo) if np.isfinite(pbo) else None,
    }
