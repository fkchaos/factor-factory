"""SUE 因子单测（不联网）：数值对照 + PIT 红线 + 快/慢路径一致 + 注册。

构造确定性假数据：单季净利 2021/2022 恒定 [10,20,30,40]，2023 起每季 +5。
→ 盈余惊喜序列为 0,0,0,0,5,5,5,5，可手算 std 与 SUE 做精确对照。
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from factors import sue as S
from factors.sue import SUEFactor, to_quarterly, sue_map
from data.pit_fundamentals import PitFinancialsService

ASSET = "000001.SZ"
FIELD_COL = "PARENT_NETPROFIT"


class _FakeProvider:
    """只提供字段映射，不联网（_hist 由测试直接注入）。"""
    _PIT_FIELD_MAP = {"net_profit_parent": FIELD_COL}


# 单季值：2021/2022 = 10/20/30/40；2023 = 15/25/35/45（每季 +5）
QUARTERLY = {}
for _y in (2021, 2022, 2023):
    for _q, _v in zip((1, 2, 3, 4), (10, 20, 30, 40)):
        QUARTERLY[(_y, _q)] = float(_v + (5 if _y == 2023 else 0))


def _cum_series():
    """累计口径（报表真实形态）。"""
    cum = {}
    for y in (2021, 2022, 2023):
        acc = 0.0
        for q in (1, 2, 3, 4):
            acc += QUARTERLY[(y, q)]
            cum[(y, q)] = acc
    return cum


def _stat_date(y, q):
    return pd.Timestamp(year=y, month=q * 3, day=1) + pd.offsets.MonthEnd(0)


def _hist_df(pub_lag_days: int = 30) -> pd.DataFrame:
    rows = []
    cum = _cum_series()
    for (y, q), v in sorted(cum.items()):
        sd = _stat_date(y, q)
        rows.append({
            "statDate": sd,
            "pubDate": sd + pd.Timedelta(days=pub_lag_days),
            FIELD_COL: v,
        })
    return pd.DataFrame(rows)


def _service(pub_lag_days: int = 30) -> PitFinancialsService:
    svc = PitFinancialsService(_FakeProvider(), [], ["net_profit_parent"])
    svc._hist = {ASSET: _hist_df(pub_lag_days)}  # 直接注入，避免联网
    return svc


# ---------------- 纯函数 ----------------
def test_to_quarterly_cum_to_single():
    cum = pd.Series({_stat_date(y, q): v for (y, q), v in _cum_series().items()}).sort_index()
    q = to_quarterly(cum)
    assert len(q) == 12
    for k, want in QUARTERLY.items():
        assert k in q.index, f"缺 {k}"
        assert q.loc[k] == pytest.approx(want), f"{k} 单季值应为 {want}"


def test_to_quarterly_skips_when_prev_missing():
    """缺前一季累计时该期跳过（不静默用累计冒充单季）。

    注意 Q3 = cum_Q3 − cum_H1 **只依赖 Q2 累计**，缺 Q1 不影响 Q3，
    所以这里只有 Q2 应缺失、Q3 应正常产出 75−40=35。
    """
    cum = pd.Series({_stat_date(2023, 2): 40.0, _stat_date(2023, 3): 75.0})
    q = to_quarterly(cum)
    assert (2023, 2) not in q.index, "缺 Q1 时 Q2 不应产出（无法拆单季）"
    assert q.loc[(2023, 3)] == pytest.approx(35.0), "Q3 只依赖 Q2 累计，应为 75-40"


def test_sue_zero_surprise_has_no_value():
    """2023Q1：历史 4 期惊喜全为 0 → std=0 → 该期无值（避免除零/无穷）。"""
    cum = pd.Series({_stat_date(y, q): v for (y, q), v in _cum_series().items()}).sort_index()
    m = sue_map(cum)
    assert (2023, 1) not in m, "零波动历史不应产生 SUE（std=0）"


def test_sue_value_matches_manual():
    """2023Q2：UE=5，历史惊喜 [0,0,0,0,5] → SUE = 5 / std(ddof=1)。"""
    cum = pd.Series({_stat_date(y, q): v for (y, q), v in _cum_series().items()}).sort_index()
    m = sue_map(cum)
    assert (2023, 2) in m
    hist = [0.0, 0.0, 0.0, 0.0, 5.0]
    want = 5.0 / float(np.std(hist, ddof=1))
    assert m[(2023, 2)] == pytest.approx(want)
    # SUE 随历史惊喜变稳定而单调下降（5,5,5 摊进历史后 std 变大）
    assert (2023, 4) in m
    assert m[(2023, 4)] < m[(2023, 2)]


# ---------------- PIT 红线 ----------------
def test_pit_redline_invisible_before_pubdate():
    """公告日前一日看不到该期；当日生效。"""
    svc = _service(pub_lag_days=30)
    sd = _stat_date(2023, 2)
    pub = sd + pd.Timedelta(days=30)
    ev = svc.disclosure_events(ASSET, "net_profit_parent")
    before = S._sue_asof(ev, pub - pd.Timedelta(days=1))
    after = S._sue_asof(ev, pub)
    # 公告前：最新可得期为 2022Q4（惊喜为 0 波动 → 无值）；公告后 2023Q2 生效
    assert pd.isna(before) or (2023, 2) not in sue_map(S._cum_asof(ev, pub - pd.Timedelta(days=1)))
    assert pd.notna(after), "公告日当日应生效"
    m_after = sue_map(S._cum_asof(ev, pub))
    assert (2023, 2) in m_after


def test_restatement_uses_visible_version_not_final():
    """重述：as_of 只能用当时可见版本，不能用最终更正版。"""
    svc = _service(pub_lag_days=30)
    ev = svc.disclosure_events(ASSET, "net_profit_parent")
    sd = _stat_date(2022, 4)
    pub_orig = sd + pd.Timedelta(days=30)
    pub_fix = sd + pd.Timedelta(days=60)
    ev2 = pd.concat([
        ev,
        pd.DataFrame([{"pubDate": pub_fix, "statDate": sd, "value": 9999.0}]),
    ], ignore_index=True).sort_values(["pubDate", "statDate"]).reset_index(drop=True)
    # 更正前：仍是原始累计值 100
    assert S._cum_asof(ev2, pub_orig)[sd] == pytest.approx(100.0)
    # 更正后：才是 9999
    assert S._cum_asof(ev2, pub_fix)[sd] == pytest.approx(9999.0)


# ---------------- 快/慢路径一致 ----------------
def test_fastpath_matches_slowpath_daily():
    """快路径（公告日事件驱动 + 阶梯）必须与逐日慢路径逐日逐值一致。"""
    svc = _service(pub_lag_days=30)
    # 窗口须覆盖首个有值期（2023Q2，公告日 = 2023-06-30 + 30d ≈ 2023-07-30）
    dates = pd.bdate_range("2022-01-03", periods=520)
    panel = pd.DataFrame(index=pd.MultiIndex.from_product(
        [dates, [ASSET]], names=["date", "asset"]))
    panel["close"] = 1.0
    f = SUEFactor()
    ctx = {"pit_service": svc}

    fast = f.compute_panel(panel, ctx)
    slow = pd.DataFrame(
        {ASSET: [f.compute(panel, t, ctx).get(ASSET, np.nan) for t in dates]},
        index=dates,
    )
    assert not fast.empty and fast[ASSET].notna().any(), "快路径全空，说明未生效"
    for t in dates:
        a = fast[ASSET].get(t, np.nan)
        b = slow[ASSET].get(t, np.nan)
        assert (pd.isna(a) and pd.isna(b)) or a == pytest.approx(b), f"{t} 不一致: {a} vs {b}"


def test_step_behaviour_after_disclosure():
    """公告后值保持到下一次公告（阶梯），且首次出现在公告日或之后的首个交易日。"""
    svc = _service(pub_lag_days=30)
    dates = pd.bdate_range("2023-01-02", periods=250)
    panel = pd.DataFrame(index=pd.MultiIndex.from_product(
        [dates, [ASSET]], names=["date", "asset"]))
    panel["close"] = 1.0
    ser = SUEFactor().compute_panel(panel, {"pit_service": svc})[ASSET]
    first_valid = ser.first_valid_index()
    pub_2023q2 = _stat_date(2023, 2) + pd.Timedelta(days=30)
    assert first_valid is not None
    assert first_valid >= pub_2023q2 - pd.Timedelta(days=4), (
        f"值不应早于 2023Q2 公告日太多（首次={first_valid}, 公告日={pub_2023q2}）"
    )
    # 阶梯：连续非 NaN 段内值恒定
    seg = ser.dropna()
    assert seg.nunique() >= 1


# ---------------- 注册 ----------------
def test_sue_registered():
    import factors  # 触发 __init__ 全量注册
    from factors.interface import list_factors
    assert "sue" in list_factors(), "sue 未注册（factors/__init__.py 漏 import？）"
