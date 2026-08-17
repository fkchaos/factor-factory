"""时序信号线专项测试（与因子线 test_lookahead.py 平行）。

信号线红线三条，本文件逐条守：
1. 前视防护：Signal.compute 只能用 as_of_date 及之前数据（合规通过 / 违规抛错）。
2. **执行滞后**：叠加回测必须用 state.shift(exec_lag)，禁止当日状态×当日收益（隐性前视，
   对 breadth 这类"当日涨跌统计"型信号几乎是同义反复，会造出假 Sharpe）。
3. 输出可序列化：state_performance 结果必须能 json.dump（转移矩阵 numpy key 是老坑）。
"""
import json

import numpy as np
import pandas as pd
import pytest

from signals.interface import (
    assert_no_lookahead, slice_panel_to_date, LookaheadError,
    register_signal, get_signal, list_signals,
)
from signals.breadth_regime import BreadthRegimeSignal
from validate.signal_validator import state_performance, discretize, _max_dd, _sharpe


# ---------- fixtures：合成市场面板（AR(1) 市场因子 + 个股噪声） ----------

def _make_market_panel(n_days=300, n_assets=40, seed=7, rho=0.85):
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2023-01-02", periods=n_days)
    codes = [f"{600000 + i}.SH" for i in range(n_assets)]
    rows = []
    px = {c: 10.0 for c in codes}
    mkt = 0.0
    for d in dates:
        mkt = rho * mkt + rng.normal(0, 0.008)
        for c in codes:
            r = mkt + rng.normal(0, 0.012)
            px[c] *= 1 + r
            rows.append((d, c, px[c], r))
    panel = pd.DataFrame(rows, columns=["date", "asset", "close", "ret"]).set_index(
        ["date", "asset"]
    )
    return panel, dates


PANEL, DATES = _make_market_panel()


class LeakySignal:
    """违规信号：无视 as_of_date，用全样本末日 breadth（偷未来）。"""
    name = "leaky_breadth"

    def compute(self, panel, as_of_date, ctx=None) -> float:
        last = panel.index.get_level_values("date").max()
        sub = panel.xs(last, level="date")
        return float((sub["ret"] > 0).mean() * 2 - 1)


# ---------- 1. 前视防护 ----------

def test_signal_slice_drops_future():
    d = DATES[100]
    s = slice_panel_to_date(PANEL, d)
    assert s.index.get_level_values("date").max() <= d


def test_breadth_signal_no_lookahead():
    assert assert_no_lookahead(BreadthRegimeSignal(), PANEL, DATES[150]) is True


def test_leaky_signal_raises():
    # 取中间日期，全量面板末日 != as_of_date，违规信号会读到未来那天
    with pytest.raises(LookaheadError):
        assert_no_lookahead(LeakySignal(), PANEL, DATES[150])


def test_breadth_returns_scalar_in_range():
    v = BreadthRegimeSignal().compute(PANEL, DATES[150])
    assert isinstance(v, float)
    assert -1.0 <= v <= 1.0, f"breadth 应在 [-1,1]，实得 {v}"


# ---------- 2. 注册表 ----------

def test_signal_registry_roundtrip():
    sig = BreadthRegimeSignal()
    register_signal(sig)
    assert "breadth_regime" in list_signals()
    assert get_signal("breadth_regime") is not None


# ---------- 3. 验证器：执行滞后红线 ----------

def _raw_and_bench():
    sig = BreadthRegimeSignal()
    raw = pd.Series({d: sig.compute(PANEL, d) for d in DATES[5:]}).sort_index()
    bench = PANEL["ret"].groupby(level=0).mean().reindex(raw.index)
    return raw, bench


def test_state_performance_runs_and_is_json_serializable():
    raw, bench = _raw_and_bench()
    res = state_performance(raw, bench)
    assert "error" not in res, res
    # 转移矩阵 key 必须是 str（numpy int key 会让 json.dump 炸）
    json.dumps(res)  # 不抛异常即通过
    assert set(res["transition"].keys()) <= {"from_0", "from_1"}


def test_overlay_uses_exec_lag_not_contemporaneous():
    """核心红线：overlay 必须是滞后口径，不能等于同期口径。

    同期口径（state 当日 × 收益当日）对 breadth 是同义反复，Sharpe 必然虚高。
    两者若完全相等，说明 exec_lag 没生效 = 前视回来了。
    """
    raw, bench = _raw_and_bench()
    res = state_performance(raw, bench, exec_lag=1)
    assert res["exec_lag"] == 1
    ov = res["overlay"]
    assert np.isfinite(ov["overlay_sharpe"])
    assert np.isfinite(ov["_contemp_sharpe_ref"])
    assert not np.isclose(ov["overlay_sharpe"], ov["_contemp_sharpe_ref"]), (
        "滞后口径与同期口径完全相同 -> exec_lag 未生效，隐性前视"
    )
    # 同期口径不应低于滞后口径（用了当日信息，必然更"好看"）
    assert ov["_contemp_sharpe_ref"] >= ov["overlay_sharpe"] - 1e-9


def test_exec_lag_zero_reproduces_contemporaneous():
    """反向验证：exec_lag=0 时 overlay 应退化为同期口径（证明参数真的在起作用）。"""
    raw, bench = _raw_and_bench()
    res0 = state_performance(raw, bench, exec_lag=0)
    ov = res0["overlay"]
    assert np.isclose(ov["overlay_sharpe"], ov["_contemp_sharpe_ref"], rtol=1e-9)


def test_state_fwd_corr_not_nan():
    """shift(-1) 末位 NaN 曾让 np.corrcoef 整体返回 nan，回归测试。"""
    raw, bench = _raw_and_bench()
    res = state_performance(raw, bench)
    assert np.isfinite(res["direction_hit"]["state_fwd_corr"])


def test_sample_too_small_returns_error():
    raw = pd.Series(np.random.randn(30), index=pd.bdate_range("2024-01-01", periods=30))
    bench = pd.Series(np.random.randn(30) * 0.01, index=raw.index)
    res = state_performance(raw, bench)
    assert res.get("error") is not None


# ---------- 4. 工具函数 ----------

def test_max_dd_and_sharpe_sanity():
    r = pd.Series([0.01] * 50)
    assert _max_dd(r) == pytest.approx(0.0, abs=1e-12)
    assert _sharpe(r) != _sharpe(r) or np.isinf(_sharpe(r)) or _sharpe(r) > 0  # std=0 -> nan


def test_discretize_shape():
    raw = pd.Series(np.linspace(-1, 1, 100),
                    index=pd.bdate_range("2024-01-01", periods=100))
    st = discretize(raw, window=20, threshold=0.0)
    assert len(st) == len(raw)
    assert set(st.dropna().unique()) <= {0.0, 1.0}


# ---------- 5. s0003x 波动率 Regime（阈值免拟合红线 + 方向约定） ----------

def _vol_sig():
    from signals.volatility_regime import VolatilityRegimeSignal
    return VolatilityRegimeSignal()


def test_volatility_signal_no_lookahead():
    assert assert_no_lookahead(_vol_sig(), PANEL, DATES[200]) is True


def test_volatility_returns_nan_before_warmup():
    """两腿共需 2*WIN+1 个价格日，暖机期内必须返回 NaN 而非瞎算。"""
    from signals.volatility_regime import WIN
    v = _vol_sig().compute(PANEL, DATES[2 * WIN - 2])
    assert np.isnan(v), f"暖机期应 NaN，实得 {v}"


def test_volatility_raw_is_zero_centered():
    """🔴 阈值免拟合红线：平稳面板上 raw 均值必须贴近 0。

    若有人把两腿改成不等长（如 ln(RV60/RV5)），小样本 E[ln s] 向下偏会让均值系统性
    偏离 0，默认 threshold=0 就不再是"构造上的自然分界"而是隐性拟合值。
    """
    sig = _vol_sig()
    vals = pd.Series({d: sig.compute(PANEL, d) for d in DATES[60:]}).dropna()
    assert len(vals) > 100
    assert abs(vals.mean()) < 0.06, f"raw 均值 {vals.mean():.4f} 偏离 0，两腿可能不等长"


def test_volatility_sign_means_contraction():
    """方向约定：近期波动 < 前期波动 → raw > 0（risk_on = 波动收缩）。"""
    from signals.volatility_regime import WIN
    rng = np.random.default_rng(11)
    dates = pd.bdate_range("2023-01-02", periods=2 * WIN + 1)
    codes = [f"{600000 + i}.SH" for i in range(30)]
    rows, px = [], {c: 10.0 for c in codes}
    for i, d in enumerate(dates):
        sigma = 0.030 if i <= WIN else 0.003  # 前段高波动，后段骤然平静
        for c in codes:
            px[c] *= 1 + rng.normal(0, sigma)
            rows.append((d, c, px[c]))
    p = pd.DataFrame(rows, columns=["date", "asset", "close"]).set_index(["date", "asset"])
    v = _vol_sig().compute(p, dates[-1])
    assert v > 0, f"波动收缩应为正，实得 {v}"


def test_volatility_registered_in_package_init():
    """导入即注册纪律（2026-08-07 KeyError 事故）：新信号必须在 signals/__init__ 有 import。"""
    import signals  # noqa: F401
    assert "volatility_regime" in list_signals()
    assert get_signal("volatility_regime") is not None
