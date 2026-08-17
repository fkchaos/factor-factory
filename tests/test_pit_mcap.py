"""PIT 流通市值 + risk_appetite(s0002x) 专项测试。

锁死 2026-08-08 踩的坑：面板里的 `market_cap` 列是"今日快照回填全历史"的假 PIT 数据
（provider 用 df["asset"].map(今日市值)，同一票时序 nunique==1），拿它做历史市值分档
= 后视选股。本文件保证：

1. pit_float_mcap 口径正确（amount / (turnover/100) = vwap × 流通股本）。
2. pit_float_mcap 严格 PIT：as_of 之后的数据改了也不影响结果。
3. 停牌/零换手样本被剔除，不会炸出天量市值。
4. lookback 中位数能压掉单日换手异常。
5. **risk_appetite 完全不读 market_cap 列**——把该列整列污染成反向排序，
   信号值必须一字不变（这是防回归的核心断言）。
6. risk_appetite 用**前一日**市值分组，当日暴涨不重排分档。
"""
import numpy as np
import pandas as pd
import pytest

from data.pit import pit_float_mcap, MIN_TURNOVER_PCT
from signals.interface import get_signal, assert_no_lookahead
from signals.risk_appetite import RiskAppetiteSignal


# ---------- fixtures ----------

def _panel(n_days=30, n_assets=40, seed=3):
    """合成面板：市值跨度 10 亿 ~ 2000 亿，换手率 0.5%~3%，含 market_cap 假列。"""
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2024-01-02", periods=n_days)
    codes = [f"{600000 + i}.SH" for i in range(n_assets)]
    # 真实流通股本：按序号从小到大（asset i 越大 → 股本越大）
    shares = {c: (1e8 * (1 + i * 0.8)) for i, c in enumerate(codes)}
    rows = []
    px = {c: 10.0 for c in codes}
    for d in dates:
        for c in codes:
            r = rng.normal(0, 0.01)
            px[c] *= 1 + r
            turn = float(rng.uniform(0.5, 3.0))              # %
            vol = shares[c] * turn / 100.0
            amt = vol * px[c]
            rows.append((d, c, px[c], vol, amt, turn,
                         # 🔴 假 market_cap：故意反向（序号越大值越小），
                         # 用来验证信号确实没读这列
                         1e12 / (1 + list(codes).index(c))))
    p = pd.DataFrame(rows, columns=["date", "asset", "close", "volume",
                                    "amount", "turnover", "market_cap"])
    return p.set_index(["date", "asset"]).sort_index(), dates, shares, codes


PANEL, DATES, SHARES, CODES = _panel()


# ---------- 1. 口径正确性 ----------

def test_pit_mcap_matches_shares_times_price():
    t = DATES[10]
    mc = pit_float_mcap(PANEL, t, lookback=1)
    day = PANEL.xs(t, level="date")
    for c in CODES[:5]:
        expected = SHARES[c] * day.loc[c, "close"]
        assert mc[c] == pytest.approx(expected, rel=1e-9), c


def test_pit_mcap_ranking_follows_true_size():
    """真实股本递增 → PIT 市值排序应与股本排序高度一致（价格扰动不改变量级差）。"""
    mc = pit_float_mcap(PANEL, DATES[15], lookback=5)
    true_size = pd.Series({c: SHARES[c] for c in mc.index})
    rho = mc.rank().corr(true_size.rank())
    assert rho > 0.99


def test_static_market_cap_column_would_rank_backwards():
    """守卫用例：证明面板里的假 market_cap 列确实与真实规模反向。

    若哪天 provider 修好了 PIT 市值、这个断言开始失败，说明数据层已升级，
    届时应回来重新评估 risk_appetite 是否还需要自己现算。
    """
    day = PANEL.xs(DATES[15], level="date")
    true_size = pd.Series({c: SHARES[c] for c in day.index})
    rho = day["market_cap"].rank().corr(true_size.rank())
    assert rho < -0.9


# ---------- 2. 前视安全 ----------

def test_pit_mcap_ignores_future_rows():
    t = DATES[12]
    before = pit_float_mcap(PANEL, t, lookback=5)
    tampered = PANEL.copy()
    future = tampered.index.get_level_values("date") > t
    tampered.loc[future, "amount"] *= 1000.0
    tampered.loc[future, "turnover"] = 0.02
    after = pit_float_mcap(tampered, t, lookback=5)
    pd.testing.assert_series_equal(before, after)


def test_signal_passes_lookahead_audit():
    assert_no_lookahead(RiskAppetiteSignal(), PANEL, DATES[20])


# ---------- 3. 停牌 / 零换手守卫 ----------

def test_zero_turnover_excluded():
    t = DATES[8]
    tampered = PANEL.copy()
    idx = (tampered.index.get_level_values("date") == t) & \
          (tampered.index.get_level_values("asset") == CODES[0])
    tampered.loc[idx, "turnover"] = 0.0
    mc = pit_float_mcap(tampered, t, lookback=1)
    assert CODES[0] not in mc.index


def test_below_floor_turnover_excluded():
    t = DATES[8]
    tampered = PANEL.copy()
    idx = (tampered.index.get_level_values("date") == t) & \
          (tampered.index.get_level_values("asset") == CODES[1])
    tampered.loc[idx, "turnover"] = MIN_TURNOVER_PCT / 10.0
    mc = pit_float_mcap(tampered, t, lookback=1)
    assert CODES[1] not in mc.index


def test_lookback_median_absorbs_single_day_spike():
    """单日换手异常砸出的 10 倍市值，应被 5 日中位数吸收。"""
    t = DATES[20]
    tampered = PANEL.copy()
    idx = (tampered.index.get_level_values("date") == t) & \
          (tampered.index.get_level_values("asset") == CODES[3])
    tampered.loc[idx, "turnover"] = tampered.loc[idx, "turnover"] / 10.0

    spiky = pit_float_mcap(tampered, t, lookback=1)[CODES[3]]
    smooth = pit_float_mcap(tampered, t, lookback=5)[CODES[3]]
    clean = pit_float_mcap(PANEL, t, lookback=5)[CODES[3]]
    assert spiky > 5 * clean            # 单日口径确实被砸飞
    assert smooth == pytest.approx(clean, rel=0.35)  # 中位数把它拉回来


# ---------- 4. 核心防回归：信号不读 market_cap 列 ----------

def test_signal_ignores_fake_market_cap_column():
    sig = RiskAppetiteSignal()
    t = DATES[20]
    base = sig.compute(PANEL, t)

    tampered = PANEL.copy()
    tampered["market_cap"] = 1.0            # 整列拍平
    assert sig.compute(tampered, t) == pytest.approx(base, abs=1e-15)

    dropped = PANEL.drop(columns=["market_cap"])  # 整列删掉也得能算
    assert sig.compute(dropped, t) == pytest.approx(base, abs=1e-15)


def test_signal_grouping_uses_prev_day_size():
    """当日给最小的票灌一个暴涨，不能把它挤出小盘组（分组基于前一日市值）。"""
    sig = RiskAppetiteSignal()
    t = DATES[20]
    base = sig.compute(PANEL, t)

    tampered = PANEL.copy()
    idx = (tampered.index.get_level_values("date") == t) & \
          (tampered.index.get_level_values("asset") == CODES[0])
    tampered.loc[idx, "close"] *= 1.10  # 最小市值票当日 +10%

    after = sig.compute(tampered, t)
    # 小盘组收益被抬高 → raw 必须变大（若分组被当日涨幅重排，它会被踢出小盘组）
    assert after > base


def test_signal_returns_nan_on_thin_cross_section():
    sig = RiskAppetiteSignal()
    thin = PANEL[PANEL.index.get_level_values("asset").isin(CODES[:6])]
    assert np.isnan(sig.compute(thin, DATES[20]))


# ---------- 5. 注册表 ----------

def test_signal_registered_with_scode():
    s = get_signal("risk_appetite")
    assert s.scode == "s0002x"
    assert s.universe_hint == "hs800"
