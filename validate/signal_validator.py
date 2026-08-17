"""时序信号验证器（validate_signal）。

与因子线 validate/validator.py（RankIC/ICIR/分层）平行但**指标完全不同**——
时序信号是市场级状态判断，检验的是"状态识别准不准 / 叠加后有没有改善"，不是横截面排序能力。

输入：
- raw_series：信号原始连续值序列（date → 标量），由 build_signal_deliverable 逐日 compute 生成
- benchmark_ret：同期市场基准日收益序列（如等权多头），用于叠加对比与状态绩效

输出（与 docs/PLAN_SIGNAL_LINE.md §4 对齐）：
1. 状态定义（离散化阈值/窗口）
2. 各状态绩效（样本数、均值日收益、Sharpe、胜率、平均未来 N 日收益）
3. 方向命中率（positive 状态后市场是否真涨）
4. 叠加改善（baseline=全样本多头 vs overlay=仅 risk_on 持多，Sharpe/最大回撤改善）
5. 状态转移矩阵（切换频率，过高=抖动需降频）
"""
from __future__ import annotations
from typing import Optional

import numpy as np
import pandas as pd

from validate.overfit_audit import deflated_sharpe

ANN = 252


def _sharpe(r: pd.Series) -> float:
    r = r.dropna()
    if len(r) < 20 or r.std(ddof=1) == 0:
        return float("nan")
    return float(r.mean() / r.std(ddof=1) * np.sqrt(ANN))


def _max_dd(r: pd.Series) -> float:
    r = r.dropna()
    if len(r) == 0:
        return float("nan")
    cum = (1 + r).cumprod()
    return float((cum / cum.cummax() - 1).min())


def discretize(raw: pd.Series, window: int = 20, threshold: float = 0.0) -> pd.Series:
    """连续值 → 离散状态。默认对 raw 取 window 日 MA，> threshold → 1(risk_on) 否则 0(risk_off)。"""
    ma = raw.rolling(window, min_periods=max(5, window // 2)).mean()
    state = ((ma > threshold).astype(float)).reindex(raw.index)
    return state


def state_performance(raw: pd.Series, benchmark_ret: pd.Series,
                      window: int = 20, threshold: float = 0.0,
                      fwd_horizons=(1, 5, 20), exec_lag: int = 1) -> dict:
    """逐状态绩效 + 方向命中 + 叠加改善 + 转移矩阵。

    **exec_lag（关键红线）**：T 日信号由 T 日收盘数据算出，最早只能在 T+1 建仓。
    因此叠加回测一律用 state.shift(exec_lag) 作为持仓态；直接用当日 state × 当日收益
    是隐性前视（对 breadth 这类"当日涨跌统计"型信号几乎是同义反复，会造出假 Sharpe）。
    同期口径仅作描述性诊断保留，字段名带 _contemp 后缀，禁止当作可交易结论。
    """
    aligned = pd.concat([raw, benchmark_ret.reindex(raw.index)], axis=1, keys=["raw", "ret"])
    aligned = aligned.dropna()
    if len(aligned) < 60:
        return {"error": "样本不足(<60)", "n": int(len(aligned))}
    raw_a = aligned["raw"]
    ret_a = aligned["ret"]

    ma = raw_a.rolling(window, min_periods=max(5, window // 2)).mean()
    state = (ma > threshold).astype(int)          # 信号态：T 日收盘后可观测
    state_exec = state.shift(exec_lag)            # 可执行态：T 日信号 → T+lag 日持仓

    out: dict = {
        "window": window, "threshold": threshold, "exec_lag": exec_lag,
        "n": int(len(aligned)),
        "raw_mean": float(raw_a.mean()), "raw_std": float(raw_a.std()),
        "states": {}, "direction_hit": {}, "overlay": {}, "transition": {},
    }

    # 1) 各状态绩效
    #    mean_ret_contemp/win_rate_contemp = 同期口径（诊断用，含当日信息，不可交易）
    #    fwd_ret_Xd = 真正的预测性统计（T 日信号 → T+1..T+h 收益）
    for s in (1, 0):
        mask = state == s
        sub = ret_a[mask]
        rec = {
            "count": int(mask.sum()),
            "mean_ret_contemp": float(sub.mean()) if len(sub) else float("nan"),
            "sharpe_contemp": _sharpe(sub) if len(sub) >= 20 else float("nan"),
            "win_rate_contemp": float((sub > 0).mean()) if len(sub) else float("nan"),
        }
        # 平均未来 N 日收益（可交易口径）
        for h in fwd_horizons:
            fwd = ret_a.shift(-h)[mask].dropna()
            rec[f"fwd_ret_{h}d"] = float(fwd.mean()) if len(fwd) else float("nan")
            rec[f"fwd_win_{h}d"] = float((fwd > 0).mean()) if len(fwd) else float("nan")
        out["states"][f"state_{s}"] = rec

    # 2) 方向命中率（可交易口径：T 日状态 → T+1 日收益）
    fwd1 = ret_a.shift(-1)
    pos_f = fwd1[state == 1].dropna()
    neg_f = fwd1[state == 0].dropna()
    out["direction_hit"] = {
        "risk_on_days": int((state == 1).sum()),
        "risk_on_fwd1_up_rate": float((pos_f > 0).mean()) if len(pos_f) else float("nan"),
        "risk_off_fwd1_up_rate": float((neg_f > 0).mean()) if len(neg_f) else float("nan"),
        "hit_spread": (float((pos_f > 0).mean()) - float((neg_f > 0).mean()))
        if len(pos_f) and len(neg_f) else float("nan"),
        # 状态值与未来1日收益的相关性（正=状态能预告方向）
        # 用 pandas.corr 而非 np.corrcoef：shift(-1) 末位为 NaN，np 版本会整体返回 nan
        "state_fwd_corr": float(state.astype(float).corr(fwd1))
        if len(state) > 5 else float("nan"),
    }

    # 3) 叠加改善：baseline=全样本多头；overlay=仅可执行 risk_on 持多（risk_off 空仓，收益 0）
    baseline = ret_a
    overlay_full = ret_a.where(state_exec == 1, 0.0)
    out["overlay"] = {
        "baseline_sharpe": _sharpe(baseline),
        "baseline_max_dd": _max_dd(baseline),
        "baseline_ann_ret": float(baseline.mean() * ANN) if len(baseline) else float("nan"),
        "overlay_sharpe": _sharpe(overlay_full),
        "overlay_max_dd": _max_dd(overlay_full),
        "overlay_ann_ret": float(overlay_full.mean() * ANN) if len(overlay_full) else float("nan"),
        "sharpe_improve": (_sharpe(overlay_full) - _sharpe(baseline)),
        "dd_improve": (_max_dd(overlay_full) - _max_dd(baseline)),
        "long_days_ratio": float((state_exec == 1).mean()),
        "note": f"overlay 用 state.shift({exec_lag})，T日信号T+{exec_lag}日建仓，无前视",
    }
    # 叠加策略 DSR（过拟合审计）
    dsr = deflated_sharpe(overlay_full.dropna().values, n_trials=4)
    out["overlay"]["dsr"] = float(dsr) if np.isfinite(dsr) else None

    # 3b) 同期口径叠加（诊断对照：若与 exec 口径差距悬殊，说明信号高度依赖当日信息）
    contemp_full = ret_a.where(state == 1, 0.0)
    out["overlay"]["_contemp_sharpe_ref"] = _sharpe(contemp_full)

    # 4) 状态转移矩阵（key 统一转字符串，避免 numpy int 导致 json.dump 失败）
    prev = state.shift(1)
    valid = prev.notna()
    trans = pd.crosstab(prev[valid].astype(int), state[valid])
    out["transition"] = {
        f"from_{int(i)}": {f"to_{int(c)}": int(trans.loc[i, c]) for c in trans.columns}
        for i in trans.index
    }
    switch_cnt = int((state != prev).sum())
    out["switch_rate"] = float(switch_cnt / max(1, int(valid.sum())))

    return out
