"""PIT 基本面管线测试（BaoStockProvider.get_pit_financials）。

分层：
  A. 纯逻辑锁死（不联网）：monkeypatch _fetch_financial_history 注入受控披露表，
     验证 🔴 红线——披露日边界 / 无前视 / 季度重述取最新版 / 缺失字段返回 NaN。
  B. 真实联网验证（sh.600000）：真连 baostock，断言 PIT 边界与数量级；
     联网失败/限流则 pytest.skip（明确标注"降级、非伪造"，绝不编造数据）。

字段可用性真相（baostock 免费接口）：
  提供 → revenue / net_profit / total_assets / net_assets
  不提供 → cogs / inventory / accounts_receivable（返回 NaN，故 f0014a/f0015a 无法仅靠 baostock 构建）
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from data.contract import normalize_code
from data.providers import BaoStockProvider

_DISC_COLS = ["statDate", "pubDate", "MBRevenue", "netProfit",
              "performanceExpressTotalAsset", "performanceExpressNetAsset"]


def _disc(rows: list[dict]) -> pd.DataFrame:
    """构造受控披露表（长表）；字段缺省补 NaN。"""
    norm = []
    for r in rows:
        norm.append({c: r.get(c, np.nan) for c in _DISC_COLS})
    return pd.DataFrame(norm)


def _fake_provider(monkeypatch, disc: pd.DataFrame, assets=("600000.SH",)):
    """返回一个 get_pit_financials 走注入披露表的 BaoStockProvider（不联网）。"""
    prov = BaoStockProvider(universe="hs300")   # 构造不联网（懒加载）
    # 把单票披露表做成按 code 查的字典；assets 默认单票即可覆盖逻辑测试
    disc_map = {normalize_code(a): disc for a in assets}

    def _fake_fetch(code):
        return disc_map.get(normalize_code(code), _disc([]))

    monkeypatch.setattr(prov, "_fetch_financial_history", _fake_fetch)
    return prov


def _norm(code: str) -> str:
    return normalize_code(code)


# ===========================================================================
# A. 纯逻辑锁死（不联网）
# ===========================================================================

def test_pit_disclosure_date_boundary(monkeypatch):
    """任务示例：财报 2023-04-30 披露 → 04-29 取不到、05-01 能取到（无前视）。"""
    disc = _disc([{
        "statDate": "2023-12-31", "pubDate": "2023-04-30",
        "MBRevenue": 100.0, "netProfit": 10.0,
    }])
    prov = _fake_provider(monkeypatch, disc)
    before = prov.get_pit_financials(["revenue"], "2023-04-29", assets=["600000.SH"])
    after = prov.get_pit_financials(["revenue"], "2023-05-01", assets=["600000.SH"])
    # 04-29：该财报尚未披露 → 取不到（NaN）
    assert pd.isna(before.loc[("2023-04-29", "600000.SH"), "revenue"])
    # 05-01：已披露 → 取到真实值
    assert after.loc[("2023-05-01", "600000.SH"), "revenue"] == 100.0


def test_pit_no_lookahead_future_annual(monkeypatch):
    """无前视：2023 年报 2024-04-30 才披露，2023-05-01 时绝不可见其数值。"""
    disc = _disc([
        {"statDate": "2022-12-31", "pubDate": "2023-04-15", "MBRevenue": 50.0},  # 2022 年报（先披露）
        {"statDate": "2023-12-31", "pubDate": "2024-04-30", "MBRevenue": 200.0},  # 2023 年报（后披露）
    ])
    prov = _fake_provider(monkeypatch, disc)
    snap = prov.get_pit_financials(["revenue"], "2023-05-01", assets=["600000.SH"])
    val = snap.loc[("2023-05-01", "600000.SH"), "revenue"]
    # 截至 2023-05-01 只知道 2022 年报（50），绝不能泄露 2023 年报（200）
    assert val == 50.0
    # 跨过披露日后才看得到 2023 年报
    snap2 = prov.get_pit_financials(["revenue"], "2024-05-01", assets=["600000.SH"])
    assert snap2.loc[("2024-05-01", "600000.SH"), "revenue"] == 200.0


def test_pit_restatement_takes_latest_version(monkeypatch):
    """季度重述：同一报告期(statDate)多次披露，取最新披露版（pubDate 最大）。"""
    disc = _disc([
        {"statDate": "2023-06-30", "pubDate": "2023-08-30", "MBRevenue": 10.0},   # 初版
        {"statDate": "2023-06-30", "pubDate": "2023-10-15", "MBRevenue": 99.0},   # 修正版
    ])
    prov = _fake_provider(monkeypatch, disc)
    # as_of 落在修正版披露之后：应取修正版 99，而非初版 10
    snap = prov.get_pit_financials(["revenue"], "2023-10-20", assets=["600000.SH"])
    assert snap.loc[("2023-10-20", "600000.SH"), "revenue"] == 99.0


def test_pit_latest_pubdate_selected_when_interim_exists(monkeypatch):
    """截至 as_of 选 pubDate 最大者（最新披露）；重述版被采纳但不覆盖更新的报告期。"""
    disc = _disc([
        {"statDate": "2023-06-30", "pubDate": "2023-10-15", "MBRevenue": 99.0},   # H1 修正版
        {"statDate": "2023-09-30", "pubDate": "2023-10-30", "MBRevenue": 150.0},  # Q3（更晚披露）
    ])
    prov = _fake_provider(monkeypatch, disc)
    snap = prov.get_pit_financials(["revenue"], "2023-11-01", assets=["600000.SH"])
    # Q3 披露更晚 → 取 Q3（150）；H1 重述（99）已被更新报告期取代（重述通道仍生效）
    assert snap.loc[("2023-11-01", "600000.SH"), "revenue"] == 150.0


def test_pit_unavailable_fields_return_nan(monkeypatch):
    """baostock 免费接口缺失的字段（cogs/inventory/accounts_receivable）返回 NaN，不伪造。"""
    disc = _disc([{"statDate": "2023-12-31", "pubDate": "2024-04-30", "MBRevenue": 100.0}])
    prov = _fake_provider(monkeypatch, disc)
    fields = ["revenue", "cogs", "inventory", "accounts_receivable"]
    snap = prov.get_pit_financials(fields, "2024-05-01", assets=["600000.SH"])
    row = snap.loc[("2024-05-01", "600000.SH")]
    assert row["revenue"] == 100.0
    assert pd.isna(row["cogs"])
    assert pd.isna(row["inventory"])
    assert pd.isna(row["accounts_receivable"])
    # 返回列必须完整包含请求字段（不可用字段以 NaN 占位）
    assert list(snap.columns) == fields


def test_pit_return_shape_and_index(monkeypatch):
    """返回 MultiIndex(date, asset)，date 层 = as_of_date，每资产一行。"""
    disc = _disc([{"statDate": "2023-12-31", "pubDate": "2024-04-30", "MBRevenue": 1.0}])
    prov = _fake_provider(monkeypatch, disc, assets=("600000.SH", "600036.SH"))
    snap = prov.get_pit_financials(["revenue"], "2024-05-01",
                                   assets=["600000.SH", "600036.SH"])
    assert isinstance(snap.index, pd.MultiIndex)
    assert snap.index.names == ["date", "asset"]
    assert snap.index.get_level_values("date").unique().tolist() == [pd.Timestamp("2024-05-01")]
    assert set(snap.index.get_level_values("asset")) == {"600000.SH", "600036.SH"}


def test_pit_cross_stream_fields_independent(monkeypatch):
    """🔴 回归锁死前任 total_assets=nan 的坑：

    baostock 免费接口下，revenue/net_profit 来自利润表 report（披露日较晚、资产为 nan），
    total_assets/net_assets 来自业绩快报 express（披露日较早、收入利润为 nan）；二者常共享
    同一 statDate（2023-12-31）。若整行取"最新披露"，年报（nan 资产）会覆盖快报（有值资产）
    → total_assets=nan。正确做法：每个字段独立取 pubDate<=as_of 内最新非缺失值。
    """
    disc = _disc([
        # report 流：年报披露日 2024-04-30，含收入/净利，资产缺失
        {"statDate": "2023-12-31", "pubDate": "2024-04-30",
         "MBRevenue": 100.0, "netProfit": 10.0,
         "performanceExpressTotalAsset": np.nan, "performanceExpressNetAsset": np.nan},
        # express 流：快报披露日 2024-03-21，含资产，收入净利缺失
        {"statDate": "2023-12-31", "pubDate": "2024-03-21",
         "MBRevenue": np.nan, "netProfit": np.nan,
         "performanceExpressTotalAsset": 9000.0, "performanceExpressNetAsset": 700.0},
    ])
    prov = _fake_provider(monkeypatch, disc)
    fields = ["revenue", "net_profit", "total_assets", "net_assets"]
    snap = prov.get_pit_financials(fields, "2024-05-01", assets=["600000.SH"])
    row = snap.loc[("2024-05-01", "600000.SH")]
    # 字段独立取数：revenue 取 report、assets 取 express，互不覆盖
    assert row["revenue"] == 100.0
    assert row["net_profit"] == 10.0
    assert row["total_assets"] == 9000.0     # 修复前此处 = nan
    assert row["net_assets"] == 700.0


def test_pit_cross_stream_pre_express_revenue_only(monkeypatch):
    """边界：截至 express 披露后、年报披露前，资产已知(revenue 取更早报告)，且不前视年报。"""
    disc = _disc([
        {"statDate": "2023-12-31", "pubDate": "2024-04-30",
         "MBRevenue": 100.0, "netProfit": 10.0,
         "performanceExpressTotalAsset": np.nan, "performanceExpressNetAsset": np.nan},
        {"statDate": "2023-12-31", "pubDate": "2024-03-21",
         "MBRevenue": np.nan, "netProfit": np.nan,
         "performanceExpressTotalAsset": 9000.0, "performanceExpressNetAsset": 700.0},
        # 更早的 H1 report，年报未披露时即为其已知最新收入
        {"statDate": "2023-06-30", "pubDate": "2023-08-31",
         "MBRevenue": 50.0, "netProfit": 5.0,
         "performanceExpressTotalAsset": np.nan, "performanceExpressNetAsset": np.nan},
    ])
    prov = _fake_provider(monkeypatch, disc)
    fields = ["revenue", "total_assets"]
    # 2024-04-01：年报(04-30)未披露 → 收入取 H1(50)，资产取快报(9000)；均不前视
    snap = prov.get_pit_financials(fields, "2024-04-01", assets=["600000.SH"])
    row = snap.loc[("2024-04-01", "600000.SH")]
    assert row["revenue"] == 50.0
    assert row["total_assets"] == 9000.0
    # 2024-05-01：年报已披露 → 收入升到 100，资产仍为快报 9000
    snap2 = prov.get_pit_financials(fields, "2024-05-01", assets=["600000.SH"])
    row2 = snap2.loc[("2024-05-01", "600000.SH")]
    assert row2["revenue"] == 100.0
    assert row2["total_assets"] == 9000.0


# ===========================================================================
# B. 真实联网验证（sh.600000）——失败则降级 skip，绝不伪造
# ===========================================================================

def test_pit_real_baostock_sh600000():
    """真实联网：sh.600000 截至 2024-05-01 应能取到 2023 年报（pubDate 2024-04-30）。

    明确标注：本测试为【真实联网】验证；若 baostock 不可达/限流，pytest.skip 降级，
    不编造任何 PIT 数值。数量级断言基于已公开年报（营业收入≈3296亿、总资产≈9.0万亿）。
    """
    try:
        prov = BaoStockProvider(universe="hs300", pit_start_year=2021)
        fields = ["revenue", "net_profit", "total_assets", "net_assets"]
        after = prov.get_pit_financials(fields, "2024-05-01", assets=["600000.SH"])
        before = prov.get_pit_financials(fields, "2024-04-29", assets=["600000.SH"])
    except Exception as e:  # 联网失败 / 限流 / 无 baostock 依赖
        pytest.skip(f"baostock 真实联网降级（非伪造）：{e!r}")

    a = after.loc[("2024-05-01", "600000.SH")]
    b = before.loc[("2024-04-29", "600000.SH")]
    # 数量级合理（元）：营业收入百亿级以上、总资产万亿级
    assert a["revenue"] > 1e10, f"营业收入量级异常: {a['revenue']}"
    assert a["total_assets"] > 1e12, f"总资产量级异常: {a['total_assets']}"
    # PIT 边界：2023 年报 2024-04-30 披露 → 04-29 尚不可见，05-01 可见（值应变化）
    assert not pd.isna(a["revenue"])
    assert b["revenue"] != a["revenue"], "披露日边界未生效（前视！）"
    print(f"[real] sh.600000 截至2024-05-01 PIT: "
          f"revenue={a['revenue']:.3e} net_profit={a['net_profit']:.3e} "
          f"total_assets={a['total_assets']:.3e} net_assets={a['net_assets']:.3e}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
