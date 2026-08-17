"""DSR / PBO 过拟合审计（因子入库门禁）。

依据：
- **DSR**（Deflated Sharpe Ratio，Bailey & Lopez de Prado 2014）：对"研究过程中试过
  n_trials 个策略"的 multiplicity 进行打折。SR 越高、样本越长、偏度越正越易显著；
  试得越多（n_trials 越大），门槛越高。DSR = P(真实 SR > 0 | 经多试打折)。
- **PBO**（Probability of Backtest Overfitting，Bailey, Borwein, Lopez de Prado & Zhu 2015）：
  CSCV 组合划分（S 块取 C(S, S/2) 组合），训练集上选最优策略，看它在测试集上的相对排名
  掉到中位数以下（ω* ≤ 0.5）的比例。PBO > 0.5 即严重过拟合。

调研背景见 docs/RESEARCH_LOG.md R2026-0804-05（结论：复用成熟实现；实测 backtest-audit
为代码审计器非统计器、purgedcv 接口面向 ML 时序 CV，故按论文公式自研，公式公开权威）。

门禁阈值（可配，默认对齐调研结论）：
- DSR ≥ 0.95 → PASS（p>0.95 才算显著）；0.90~0.95 → WARN；< 0.90 → FAIL
- PBO ≤ 0.30 → PASS；0.30~0.50 → WARN；> 0.50 → FAIL
- 综合：任一 FAIL → 不纳入生产组合；两个 WARN 也建议复核。
"""
from __future__ import annotations

import itertools
from typing import Optional

import numpy as np
import pandas as pd
from scipy import stats

ANN = 252  # 日频年化


def deflated_sharpe(returns: np.ndarray, n_trials: int = 10, rf: float = 0.0) -> float:
    """DSR：经多试（n_trials）打折后的策略真实夏普为正的概率。

    Args:
        returns: 策略日收益序列（1D，可含 NaN，内部剔除）。
        n_trials: 研究过程中评估过的策略/变体总数（含失败的、翻转方向前的）。
                  诚实估计：本生产线至今试过的因子方向/参数变体数。
        rf: 无风险日收益（默认 0）。
    Returns:
        DSR ∈ [0, 1]。
    """
    r = np.asarray(returns, dtype=float)
    r = r[np.isfinite(r)]
    n = len(r)
    if n < 30:
        return np.nan
    sr = (r.mean() - rf) / r.std(ddof=1) * np.sqrt(ANN)     # 年化 SR
    skew = stats.skew(r, bias=False)
    kurt = stats.kurtosis(r, fisher=False, bias=False)      # 非超峰度（fisher=False）
    var_sr = (1.0 - skew * sr + (kurt - 1.0) / 4.0 * sr ** 2) / (n - 1)  # SR 估计方差
    if var_sr <= 0:
        return np.nan
    sr0 = np.sqrt(var_sr) * stats.norm.ppf(1.0 - 1.0 / max(n_trials, 1))  # 基准 SR（多试打折）
    if sr0 == 0:
        # n_trials=2 时 ppf(0.5)=0，基准 SR=0 → 退化为普通概率夏普（无 deflation）
        return float(stats.norm.cdf(sr / np.sqrt(var_sr)))
    return float(stats.norm.cdf((sr - sr0) / np.sqrt(var_sr)))


def _sharpe(block_returns: np.ndarray) -> float:
    r = block_returns[np.isfinite(block_returns)]
    if len(r) < 10 or r.std(ddof=1) == 0:
        return np.nan
    return r.mean() / r.std(ddof=1)


def probability_of_backtest_overfit(returns_matrix: np.ndarray, n_splits: int = 12,
                                    seed: Optional[int] = None) -> float:
    """PBO：CSCV 组合划分下，训练集最优策略在测试集掉到中位数以下的概率。

    Args:
        returns_matrix: 策略收益矩阵，shape (N, T)，N 个候选策略 × T 期收益。
                        PBO 的关键是 N ≥ 2（有"竞争"才有过拟合定义）。
        n_splits: 时间块数 S；组合数 = C(S, S/2)。S=12 → 924 组合，S=16 → 12870。
                  样本不足时自动降级（块内至少 ~20 期）。
    Returns:
        PBO ∈ [0, 1]。> 0.5 严重过拟合；≈0.5 随机（无过拟合也无 alpha）。
    """
    M = np.asarray(returns_matrix, dtype=float)
    N, T = M.shape
    if N < 2 or T < 40:
        return np.nan
    S = n_splits
    while S >= 4 and T // S < 20:
        S -= 2
    blocks = np.array_split(np.arange(T), S)
    omegas: list[float] = []
    rng = np.random.default_rng(seed) if seed is not None else None
    for is_blocks in itertools.combinations(range(S), S // 2):
        is_cols = np.concatenate([blocks[b] for b in is_blocks])
        os_blocks = [b for b in range(S) if b not in is_blocks]
        os_cols = np.concatenate([blocks[b] for b in os_blocks])
        is_sr = np.array([_sharpe(M[i, is_cols]) for i in range(N)])
        if not np.any(np.isfinite(is_sr)):
            continue
        best_i = int(np.nanargmax(is_sr))
        os_sr = np.array([_sharpe(M[i, os_cols]) for i in range(N)])
        valid = np.isfinite(os_sr)
        if valid.sum() < 2:
            continue
        # ω*：IS 最优策略在 OOS 的相对绩效。论文（Bailey et al. 2015）定义
        # ω* = R*/(N+1)，R* 为"从好到差"的排名（1=OOS 最好，N=OOS 最差）；
        # ω* ≤ 0.5 即 IS 最优在 OOS 排后 50%（差于中位数）= 过拟合事件。
        rank = (os_sr[valid] < os_sr[best_i]).sum() + 1.0
        omegas.append(rank / valid.sum())
    if not omegas:
        return np.nan
    return float(np.mean(np.array(omegas) <= 0.5))


def strategy_returns_from_factor(factor_series: dict, fwd_ret: dict,
                                 top_n: int = 20) -> pd.Series:
    """由逐日因子值构造 top_n 等权策略日收益（DSR/PBO 的输入）。

    每日期：因子值前 top_n 的资产，下一日等权收益（已含 1 日持有）。
    注意：这是**简化代理策略**（不含成本/滑点/涨跌停限制），用于显著性审计而非绩效评估。
    """
    rets: dict[pd.Timestamp, float] = {}
    for t, fv in factor_series.items():
        if t not in fwd_ret:
            continue
        fr = fwd_ret[t]
        common = fv.index.intersection(fr.index)
        if len(common) < 5:
            continue
        f, r = fv.loc[common], fr.loc[common]
        picks = f.nlargest(min(top_n, len(common))).index
        rets[t] = float(r.loc[picks].mean())
    s = pd.Series(rets).sort_index()
    return s


def audit(returns: np.ndarray, n_trials: int = 10, n_splits: int = 12,
          pbo_matrix: Optional[np.ndarray] = None) -> dict:
    """综合审计：DSR + PBO + 门禁判定。

    Args:
        returns: 主策略日收益序列（1D）。
        n_trials: DSR 多试次数。
        n_splits: PBO 时间块数。
        pbo_matrix: 候选策略收益矩阵（N, T）；None 时退化为单策略（PBO 返回 NaN，仅用 DSR）。
    Returns:
        {'dsr': float|None, 'pbo': float|None, 'verdict': PASS/WARN/FAIL,
         'detail': str}
    """
    dsr = deflated_sharpe(returns, n_trials=n_trials)
    pbo = probability_of_backtest_overfit(pbo_matrix, n_splits=n_splits) \
        if pbo_matrix is not None else None

    issues = []
    if dsr is not None:
        if dsr >= 0.95:
            dsr_v = "PASS"
        elif dsr >= 0.90:
            dsr_v, issues = "WARN", issues + ["DSR 处于灰区(0.90~0.95)"]
        else:
            dsr_v, issues = "FAIL", issues + [f"DSR={dsr:.2f}<0.90"]
    else:
        dsr_v = "N/A"
    if pbo is not None:
        if pbo <= 0.30:
            pbo_v = "PASS"
        elif pbo <= 0.50:
            pbo_v, issues = "WARN", issues + [f"PBO={pbo:.2f} 处于灰区(0.30~0.50)"]
        else:
            pbo_v, issues = "FAIL", issues + [f"PBO={pbo:.2f}>0.50 严重过拟合"]
    else:
        pbo_v = "N/A"

    verdict = "FAIL" if any("FAIL" in i for i in issues) or (
        "FAIL" in (dsr_v, pbo_v)) else ("WARN" if issues else "PASS")
    dsr_txt = f"DSR={dsr_v}({dsr:.3f})" if dsr is not None else "DSR=N/A"
    pbo_txt = f"PBO={pbo_v}({pbo:.3f})" if pbo is not None else "PBO=N/A"
    return {
        "dsr": dsr, "pbo": pbo, "verdict": verdict,
        "detail": f"{dsr_txt} {pbo_txt}",
    }
