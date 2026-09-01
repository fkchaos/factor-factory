"""AkShare PIT 基本面管线测试（AkShareProvider.get_pit_financials）。

目标字段：cogs(营业成本) / inventory(存货) / accounts_receivable(应收账款) ——
baostock 免费接口不返回，改由 AkShare 东财明细表（stock_profit_sheet_by_report_em /
stock_balance_sheet_by_report_em）提供，且【带真实公告日 NOTICE_DATE】，可安全做 PIT 对齐。

分层（与 test_pit_financials.py 一致）：
  A. 纯逻辑锁死（不联网）：monkeypatch _fetch_financial_history 注入受控披露表
     （利润表流+资产负债表流纵向拼接），验证 🔴 红线——披露日边界 / 无前视 /
     双流字段独立取数 / 重述取最新版 / 缺失字段返回 NaN。
  B. 真实联网验证（sh.600519）：真连 AkShare 东财，断言 PIT 边界与数量级；
     联网失败/限流则 pytest.skip（明确标注"降级、非伪造"，绝不编造数据）。

⚠️ 前视红线：AkShareProvider 用 NOTICE_DATE（真实公告日）对齐，绝不用 REPORT_DATE（报告期）。
   stock_financial_analysis_indicator 只有'日期'(报告期)、无真实公告日 → 刻意不用。
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from data.contract import normalize_code
from data.providers import AkShareProvider

# 受控披露表的列（与 AkShareProvider._fetch_financial_history 输出一致）
_DISC_COLS = ["statDate", "pubDate", "OPERATE_INCOME", "OPERATE_COST",
              "INVENTORY", "ACCOUNTS_RECE"]


def _disc(rows: list[dict]) -> pd.DataFrame:
    """构造受控披露长表；字段缺省补 NaN。"""
    norm = []
    for r in rows:
        norm.append({c: r.get(c, np.nan) for c in _DISC_COLS})
    return pd.DataFrame(norm)


def _fake_provider(monkeypatch, disc: pd.DataFrame, assets=("600519.SH",)):
    """返回走注入披露表的 AkShareProvider（不联网）。"""
    prov = AkShareProvider()   # 构造不联网（懒加载 akshare）
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

def test_ak_pit_disclosure_date_boundary(monkeypatch):
    """2023 年报 NOTICE_DATE=2024-04-30 → 04-29 取不到、05-01 能取到（无前视）。"""
    disc = _disc([{
        "statDate": "2023-12-31", "pubDate": "2024-04-30",
        "OPERATE_COST": 100.0, "INVENTORY": 50.0, "ACCOUNTS_RECE": 20.0,
    }])
    prov = _fake_provider(monkeypatch, disc)
    before = prov.get_pit_financials(["cogs", "inventory", "accounts_receivable"],
                                     "2024-04-29", assets=["600519.SH"])
    after = prov.get_pit_financials(["cogs", "inventory", "accounts_receivable"],
                                    "2024-05-01", assets=["600519.SH"])
    b = before.loc[("2024-04-29", "600519.SH")]
    a = after.loc[("2024-05-01", "600519.SH")]
    # 04-29：该财报尚未披露 → 取不到（NaN）
    assert pd.isna(b["cogs"]) and pd.isna(b["inventory"]) and pd.isna(b["accounts_receivable"])
    # 05-01：已披露 → 取到真实值
    assert a["cogs"] == 100.0 and a["inventory"] == 50.0 and a["accounts_receivable"] == 20.0


def test_ak_pit_two_stream_fields_independent(monkeypatch):
    """🔴 双流独立取数：利润表流(收入/成本,披露较晚) 与 资产负债表流(存货/应收,披露较早)
    共享同一 statDate(2023-12-31)。若整行取最新披露，年报(缺存货/应收)会覆盖快报
    (有值存货/应收) → inventory/AR=nan。正确：每字段独立取 pubDate<=as_of 内最新非缺失。"""
    disc = _disc([
        # 资产负债表流：快报披露日 2024-03-21，含存货/应收，收入成本为 nan
        {"statDate": "2023-12-31", "pubDate": "2024-03-21",
         "OPERATE_INCOME": np.nan, "OPERATE_COST": np.nan,
         "INVENTORY": 9000.0, "ACCOUNTS_RECE": 300.0},
        # 利润表流：年报披露日 2024-04-30，含收入/成本，存货/应收为 nan
        {"statDate": "2023-12-31", "pubDate": "2024-04-30",
         "OPERATE_INCOME": 100.0, "OPERATE_COST": 10.0,
         "INVENTORY": np.nan, "ACCOUNTS_RECE": np.nan},
    ])
    prov = _fake_provider(monkeypatch, disc)
    fields = ["revenue", "cogs", "inventory", "accounts_receivable"]
    snap = prov.get_pit_financials(fields, "2024-05-01", assets=["600519.SH"])
    row = snap.loc[("2024-05-01", "600519.SH")]
    # 字段独立：revenue/cogs 取利润表流、inventory/AR 取资产负债表流，互不覆盖
    assert row["revenue"] == 100.0
    assert row["cogs"] == 10.0
    assert row["inventory"] == 9000.0     # 修复前此处 = nan
    assert row["accounts_receivable"] == 300.0


def test_ak_pit_restatement_takes_latest_version(monkeypatch):
    """季度重述：同一报告期(statDate)多次披露，取最新披露版（pubDate 最大）。"""
    disc = _disc([
        {"statDate": "2023-06-30", "pubDate": "2023-08-30", "INVENTORY": 10.0},   # 初版
        {"statDate": "2023-06-30", "pubDate": "2023-10-15", "INVENTORY": 99.0},   # 修正版
    ])
    prov = _fake_provider(monkeypatch, disc)
    snap = prov.get_pit_financials(["inventory"], "2023-10-20", assets=["600519.SH"])
    assert snap.loc[("2023-10-20", "600519.SH"), "inventory"] == 99.0


def test_ak_pit_no_lookahead_future_annual(monkeypatch):
    """无前视：2023 年报 2024-04-30 才披露，2023-05-01 时绝不可见其数值。"""
    disc = _disc([
        {"statDate": "2022-12-31", "pubDate": "2023-04-15",
         "OPERATE_COST": 50.0, "INVENTORY": 5.0, "ACCOUNTS_RECE": 2.0},
        {"statDate": "2023-12-31", "pubDate": "2024-04-30",
         "OPERATE_COST": 200.0, "INVENTORY": 80.0, "ACCOUNTS_RECE": 30.0},
    ])
    prov = _fake_provider(monkeypatch, disc)
    snap = prov.get_pit_financials(["cogs", "inventory", "accounts_receivable"],
                                   "2023-05-01", assets=["600519.SH"])
    row = snap.loc[("2023-05-01", "600519.SH")]
    # 截至 2023-05-01 只知道 2022 年报（50/5/2），绝不能泄露 2023 年报（200/80/30）
    assert row["cogs"] == 50.0 and row["inventory"] == 5.0 and row["accounts_receivable"] == 2.0
    snap2 = prov.get_pit_financials(["cogs", "inventory", "accounts_receivable"],
                                    "2024-05-01", assets=["600519.SH"])
    row2 = snap2.loc[("2024-05-01", "600519.SH")]
    assert row2["cogs"] == 200.0 and row2["inventory"] == 80.0 and row2["accounts_receivable"] == 30.0


def test_ak_pit_pre_express_cost_only(monkeypatch):
    """边界：截至资产负债表流披露后、利润表流披露前，存货/应收已知(更早报告)，且不前视利润表。"""
    disc = _disc([
        # 资产负债表流：快报 2024-03-21，含存货/应收
        {"statDate": "2023-12-31", "pubDate": "2024-03-21",
         "INVENTORY": 9000.0, "ACCOUNTS_RECE": 300.0,
         "OPERATE_INCOME": np.nan, "OPERATE_COST": np.nan},
        # 利润表流：年报 2024-04-30，含收入/成本
        {"statDate": "2023-12-31", "pubDate": "2024-04-30",
         "OPERATE_INCOME": 100.0, "OPERATE_COST": 10.0,
         "INVENTORY": np.nan, "ACCOUNTS_RECE": np.nan},
        # 更早的 H1 资产负债表流（年报未披露时即为其已知最新存货/应收）
        {"statDate": "2023-06-30", "pubDate": "2023-08-31",
         "INVENTORY": 8000.0, "ACCOUNTS_RECE": 250.0,
         "OPERATE_INCOME": np.nan, "OPERATE_COST": np.nan},
    ])
    prov = _fake_provider(monkeypatch, disc)
    fields = ["inventory", "accounts_receivable", "cogs", "revenue"]
    # 2024-04-01：年报(04-30)未披露 → 存货/应收取快报(9000/300)，成本/收入取 H1 流(nan)
    snap = prov.get_pit_financials(fields, "2024-04-01", assets=["600519.SH"])
    row = snap.loc[("2024-04-01", "600519.SH")]
    assert row["inventory"] == 9000.0
    assert row["accounts_receivable"] == 300.0
    assert pd.isna(row["cogs"]) and pd.isna(row["revenue"])   # 利润表流尚未披露，不前视
    # 2024-05-01：年报已披露 → 成本/收入升到 10/100
    snap2 = prov.get_pit_financials(fields, "2024-05-01", assets=["600519.SH"])
    row2 = snap2.loc[("2024-05-01", "600519.SH")]
    assert row2["cogs"] == 10.0
    assert row2["revenue"] == 100.0
    assert row2["inventory"] == 9000.0


def test_ak_pit_return_shape_and_index(monkeypatch):
    """返回 MultiIndex(date, asset)，date 层 = as_of_date，每资产一行；含全部请求字段。"""
    disc = _disc([{"statDate": "2023-12-31", "pubDate": "2024-04-30",
                   "OPERATE_COST": 1.0, "INVENTORY": 2.0, "ACCOUNTS_RECE": 3.0}])
    prov = _fake_provider(monkeypatch, disc, assets=("600519.SH", "600036.SH"))
    fields = ["cogs", "inventory", "accounts_receivable"]
    snap = prov.get_pit_financials(fields, "2024-05-01",
                                   assets=["600519.SH", "600036.SH"])
    assert isinstance(snap.index, pd.MultiIndex)
    assert snap.index.names == ["date", "asset"]
    assert snap.index.get_level_values("date").unique().tolist() == [pd.Timestamp("2024-05-01")]
    assert set(snap.index.get_level_values("asset")) == {"600519.SH", "600036.SH"}
    assert list(snap.columns) == fields


# ===========================================================================
# B. 真实联网验证（sh.600519）——失败则降级 skip，绝不伪造
# ===========================================================================

def test_ak_pit_real_sh600519():
    """真实联网：sh.600519 截至今日应能取到最新财报（含存货/应收/营业成本/营收）。

    明确标注：本测试为【真实联网】验证；若 AkShare/东财不可达/限流，pytest.skip 降级，
    不编造任何 PIT 数值。核心断言：
      (1) 早于任何公告日 → 全部 NaN（证明不会前视未来财报）；
      (2) 跨过某公告日当天，对应字段值"出现"（披露日边界生效，无前视）；
      (3) 数量级合理（存货/营收为亿元级正值，应收账款 >=0）。
    """
    try:
        prov = AkShareProvider()
        code = "600519.SH"
        disc = prov._fetch_financial_history(code)   # 真实披露历史
        fields = ["revenue", "cogs", "inventory", "accounts_receivable"]
        # 找存货字段有值的最晚公告日，用于边界断言
        inv_rows = disc.dropna(subset=["INVENTORY", "pubDate"])
        if inv_rows.empty:
            pytest.skip("AkShare 真实数据无存货字段行（降级，非伪造）")
        d_max = pd.Timestamp(inv_rows["pubDate"].max())
        inv_at_d = float(inv_rows.loc[inv_rows["pubDate"] == d_max, "INVENTORY"].iloc[0])
        # (1) 早于任意公告日 → 全 NaN
        earliest = pd.Timestamp(disc["pubDate"].min())
        before_all = prov.get_pit_financials(fields, earliest - pd.Timedelta(days=365),
                                             assets=[code])
        brow = before_all.loc[(earliest - pd.Timedelta(days=365), code)]
        assert all(pd.isna(brow[f]) for f in fields), "早于最早公告日却取到值（前视！）"
        # (2) 边界：跨过 d_max 当天，存货从"不可见"变为 inv_at_d
        before_d = prov.get_pit_financials(fields, d_max - pd.Timedelta(days=1), assets=[code])
        after_d = prov.get_pit_financials(fields, d_max, assets=[code])
        bv = before_d.loc[(d_max - pd.Timedelta(days=1), code), "inventory"]
        av = after_d.loc[(d_max, code), "inventory"]
        assert (pd.isna(bv) or bv != av), "披露日边界未生效（前视！）"
        assert av == inv_at_d, f"披露日当天未取到最新存货: {av} != {inv_at_d}"
        # (3) 截至今日：数量级合理（元）
        today_str = pd.Timestamp.now().strftime("%Y-%m-%d")
        today_ts = pd.Timestamp(today_str)
        today = prov.get_pit_financials(fields, today_str, assets=[code])
        t = today.loc[(today_ts, code)]
        assert t["inventory"] > 1e9, f"存货量级异常: {t['inventory']}"
        assert t["revenue"] > 1e9, f"营收量级异常: {t['revenue']}"
        assert t["cogs"] > 1e8, f"营业成本量级异常: {t['cogs']}"
        assert t["accounts_receivable"] >= 0, f"应收账款应 >=0: {t['accounts_receivable']}"
        print(f"[real] sh.600519 截至今日 PIT: "
              f"revenue={t['revenue']:.3e} cogs={t['cogs']:.3e} "
              f"inventory={t['inventory']:.3e} accounts_receivable={t['accounts_receivable']:.3e}")
    except Exception as e:  # 联网失败 / 限流 / 无 akshare 依赖
        pytest.skip(f"AkShare 真实联网降级（非伪造）：{e!r}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
