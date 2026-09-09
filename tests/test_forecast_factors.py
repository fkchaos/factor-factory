"""Phase 1 业绩预告因子测试（不联网）。

锁死四件事：
1. PIT 红线 —— 公告日前不可见、公告当日生效。
2. 快路径（compute_panel 事件驱动阶梯）与慢路径（compute 逐日快照）**逐日一致**。
3. 前瞻 EP 的分母与 data.pit.pit_float_mcap 同口径。
4. 三个因子注册到 interface（build 的 --factor 靠注册名取类）。
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from data.pit_forecast import PitForecastService
from data.pit import pit_float_mcap
from factors.forecast import (
    ForecastYoyFactor,
    ForecastKindFactor,
    ForecastEPFactor,
)
from factors.interface import get_factor

ASSETS = ["000001.SZ", "000002.SZ", "600519.SH"]
# 交易日轴：覆盖三次公告日（2024-03 / 2024-08 / 2024-11）
DATES = pd.DatetimeIndex(pd.bdate_range("2024-01-02", periods=260))

_ANN_K = {3: 4.0, 6: 2.0, 9: 4.0 / 3.0, 12: 1.0}


def _mk_table() -> pd.DataFrame:
    """构造规范化预告表：3 票 × 3 次公告。"""
    rows = [
        # asset,        pubDate,      period,       fc_np,   yoy,   kind,     prev_np
        ("000001.SZ", "2024-03-10", "2023-12-31", 2.0e9, 50.0, "预增", 1.333e9),
        ("000001.SZ", "2024-08-20", "2024-06-30", 1.1e9, 10.0, "略增", 1.0e9),
        ("000001.SZ", "2024-11-05", "2024-09-30", 1.2e9, -20.0, "预减", 1.5e9),
        ("000002.SZ", "2024-03-15", "2023-12-31", -5.0e8, -130.0, "首亏", 1.6e9),
        ("000002.SZ", "2024-08-25", "2024-06-30", 3.0e8, 200.0, "扭亏", -3.0e8),
        ("600519.SH", "2024-04-02", "2023-12-31", 8.0e9, 15.0, "略增", 6.96e9),
        ("600519.SH", "2024-11-11", "2024-09-30", 6.0e9, 12.0, "续盈", 5.36e9),
    ]
    df = pd.DataFrame(rows, columns=["asset", "pubDate", "period", "fc_np",
                                     "yoy", "kind", "prev_np"])
    df["pubDate"] = pd.to_datetime(df["pubDate"])
    df["period"] = pd.to_datetime(df["period"])
    from data.pit_forecast import KIND_SCORE

    df["kind_score"] = df["kind"].map(KIND_SCORE)
    assert df["kind_score"].notna().all(), "测试用预告类型必须全部命中 KIND_SCORE"
    df["fc_np_ann"] = df["fc_np"] * df["period"].dt.month.map(_ANN_K)
    df["np_yoy_calc"] = (df["fc_np"] / df["prev_np"].abs() - 1.0) * 100.0
    return df.sort_values(["asset", "pubDate"]).reset_index(drop=True)


def _mk_panel() -> pd.DataFrame:
    idx = pd.MultiIndex.from_product([DATES, ASSETS], names=["date", "asset"])
    rng = np.random.default_rng(7)
    n = len(idx)
    return pd.DataFrame(
        {
            "close": 10.0 + rng.random(n) * 5,
            "volume": 1e6 * (1 + rng.random(n)),
            "amount": 1e8 * (1 + rng.random(n)),
            "turnover": 1.0 + rng.random(n) * 4.0,  # 全部 > MIN_TURNOVER_PCT
        },
        index=idx,
    )


@pytest.fixture(scope="module")
def svc() -> PitForecastService:
    return PitForecastService(table=_mk_table())


@pytest.fixture(scope="module")
def panel() -> pd.DataFrame:
    return _mk_panel()


# ---------------- 1. PIT 红线 ----------------
def test_pit_not_visible_before_pubdate(svc):
    """公告日前一日：该票快照必须为空（否则就是前视）。"""
    t = pd.Timestamp("2024-03-10") - pd.Timedelta(days=1)
    snap = svc.snapshot(["000001.SZ"], t)
    assert snap["000001.SZ"] == {}, "公告日前不应可见任何预告"


def test_pit_visible_on_pubdate(svc):
    """公告当日：快照生效，且取到的正是该次公告的值。"""
    snap = svc.snapshot(["000001.SZ"], pd.Timestamp("2024-03-10"))
    got = snap["000001.SZ"]
    assert got, "公告当日应可见"
    assert got["yoy"] == 50.0
    assert got["kind"] == "预增"


def test_pit_latest_wins(svc):
    """多次公告后，as_of 取的是**截至该日最新一次**（不是最早、也不是未来）。"""
    snap = svc.snapshot(["000001.SZ"], pd.Timestamp("2024-12-31"))
    assert snap["000001.SZ"]["yoy"] == -20.0, "应取 2024-11-05 那次（最新）"


# ---------------- 2. 快路径 vs 慢路径逐日一致 ----------------
@pytest.mark.parametrize(
    "fct",
    [ForecastYoyFactor(), ForecastKindFactor(), ForecastEPFactor()],
    ids=["forecast_yoy", "forecast_kind", "forecast_ep"],
)
def test_fastpath_matches_slowpath(fct, svc, panel):
    """事件驱动阶梯面板必须与逐日快照结果完全一致（快路径不得引入偏差）。"""
    ctx = {"forecast_service": svc}
    fast = fct.compute_panel(panel, ctx)
    assert not fast.empty, "快路径产出不应为空"

    diff_days = 0
    checked = 0
    for t in DATES[40:]:
        slow = fct.compute(panel, t, ctx)
        if t not in fast.index:
            continue
        row = fast.loc[t].dropna()
        common = row.index.intersection(slow.index)
        if len(common) == 0:
            # 两边都无值也算一致
            assert len(row) == 0 or slow.empty
            continue
        checked += 1
        if not np.allclose(row[common].to_numpy(dtype=float),
                           slow[common].to_numpy(dtype=float), rtol=1e-9, atol=0):
            diff_days += 1
    assert diff_days == 0, f"{fct.name} 快/慢路径 {diff_days} 天不一致"
    assert checked > 0, "未做任何有效比对"


# ---------------- 3. 前瞻 EP 市值同口径 ----------------
def test_forecast_ep_uses_pit_mcap(panel, svc):
    """前瞻 EP 分母必须与 pit_float_mcap 同口径（PIT 红线，不得自创算法）。"""
    ctx = {"forecast_service": svc}
    fct = ForecastEPFactor()
    fast = fct.compute_panel(panel, ctx)
    t = DATES[-1]
    row = fast.loc[t].dropna()
    assert len(row) > 0, "样本末日 EP 应有值"

    sub = panel.xs(t, level="date") if t in panel.index.get_level_values("date") else None
    from factors.interface import slice_panel_to_date

    sub = slice_panel_to_date(panel, t)
    mcap = pit_float_mcap(sub, t)
    snap = svc.snapshot(list(row.index), t)
    for a in row.index:
        m = mcap.get(a)
        if m is None or not np.isfinite(m) or m <= 0:
            continue
        expect = snap[a]["fc_np_ann"] / m
        assert abs(row[a] - expect) < 1e-12, f"{a} EP 与 PIT 市值口径不符"


# ---------------- 4. 注册 ----------------
@pytest.mark.parametrize("name", ["forecast_yoy", "forecast_kind", "forecast_ep"])
def test_registered(name):
    f = get_factor(name)
    assert f is not None, f"{name} 未注册（build 的 --factor 会 KeyError）"
    assert f.fcode is not None
