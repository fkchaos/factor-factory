"""月度评审回归测试（2026-08-08 新增）。

锁死两类曾经真实发生过的坑：
1. **单位错配**：`FactorMonitor.check_ic_decay` 的窗口单位由调用方喂进来的序列频率决定
   （配置名 `ic_breach_months`），日频 IC 直接丢进去会变成"最近 3 个交易日"，纯噪声。
   2026-07 首期月报因此出现"本月 +0.0184 ✅正常"与"decay=True/-0.0909"自相矛盾。
2. **当月切片没有上界**：原实现 `ic[ic.index >= f"{month}-01"]` 把之后的月份也算进"本月"。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from monitor.monthly_review import (  # noqa: E402
    MIN_DAYS_PER_MONTH,
    _ic_history_path,
    _to_monthly_ic,
    cmd_report,
)
from monitor.monitor import FactorMonitor  # noqa: E402

TEST_POOL = "pytest_tmp"


def _daily(dates, value):
    return pd.Series(value, index=pd.DatetimeIndex(dates))


# ---------- 1. 月频聚合 ----------
def test_to_monthly_ic_aggregates_and_drops_partial_month():
    idx = list(pd.bdate_range("2026-01-01", "2026-03-31")) + list(
        pd.bdate_range("2026-04-01", "2026-04-02"))  # 4 月只有 2 个交易日 = 残月
    s = _daily(idx, 0.05)
    monthly = _to_monthly_ic(s)
    assert len(monthly) == 3, "残月（交易日数 < MIN_DAYS_PER_MONTH）必须被剔除"
    assert monthly.index.max().month == 3
    assert monthly.iloc[0] == pytest.approx(0.05)


def test_to_monthly_ic_accepts_string_index():
    s = pd.Series(0.03, index=[d.strftime("%Y-%m-%d")
                               for d in pd.bdate_range("2026-01-01", "2026-02-27")])
    assert len(_to_monthly_ic(s)) == 2


# ---------- 2. 单位错配红线 ----------
def test_daily_series_fed_directly_is_noise_but_monthly_is_stable():
    """同一份数据：日频直喂 → 误报衰减；月频对齐 → 不报。这就是当初的 bug。"""
    idx = pd.bdate_range("2026-01-01", "2026-07-31")
    s = pd.Series(0.05, index=idx)
    s.iloc[-3:] = -0.30  # 最后 3 天极端负 IC（噪声）

    m = FactorMonitor(ic_warn_threshold=0.02, ic_breach_months=3)
    naive = m.check_ic_decay("daily_direct", s)          # ❌ 旧口径：最近 3 天
    aligned = m.check_ic_decay("monthly", _to_monthly_ic(s))  # ✅ 新口径：最近 3 月

    assert naive["decay"] is True, "日频直喂会被 3 天噪声带偏（保留此断言以记录旧行为）"
    assert aligned["decay"] is False, "月频对齐后 3 天噪声不应触发衰减告警"
    assert aligned["recent_mean_ic"] > 0.02


# ---------- 3. 月报端到端：状态须纳入 decay，当月切片须有上界 ----------
@pytest.fixture
def _fake_baselines():
    """复刻真实场景：基线跑到 8 月初，8 月只有 2 个交易日且 IC 极端负（噪声残月）。

    f1 = 健康因子（月度全部达标，仅残月噪声）；f2 = 近 3 月真衰减但当月 delta 尚可。
    """
    written = []
    idx = pd.bdate_range("2026-01-01", "2026-07-31")
    healthy = pd.Series(0.05, index=idx)

    decaying = pd.Series(0.018, index=idx)
    decaying[decaying.index >= "2026-05-01"] = 0.012  # 近 3 月均低于 0.02 阈值

    # 8 月残月：既验证"本月"切片有上界，也充当会污染 tail(3) 的日频噪声
    aug = pd.Series(-0.90, index=pd.bdate_range("2026-08-03", "2026-08-04"))

    for name, s in (("overnight_intraday", healthy), ("ivol", decaying)):
        p = _ic_history_path(name, TEST_POOL)
        p.parent.mkdir(parents=True, exist_ok=True)
        full = pd.concat([s, aug])
        full.index.name = "date"
        full.rename("ic").to_csv(p)
        written.append(p)
    yield
    for p in written:
        p.unlink(missing_ok=True)


def _report_body(capsys) -> str:
    args = argparse.Namespace(pool=TEST_POOL, month="2026-07", out=None)
    cmd_report(args)
    return capsys.readouterr().out


def test_report_status_reflects_decay(_fake_baselines, capsys):
    body = _report_body(capsys)
    assert "**overnight_intraday**" in body and "**ivol**" in body
    on_line = [l for l in body.splitlines() if "**overnight_intraday**" in l][0]
    iv_line = [l for l in body.splitlines() if "**ivol**" in l][0]
    assert "✅ 正常" in on_line, "残月噪声不应把健康因子判成衰减"
    assert "衰减预警" in iv_line, "近 3 月均 IC 低于阈值时，健康度必须降级而非仍报正常"


def test_report_residual_month_noise_does_not_flip_health(_fake_baselines, capsys):
    """8 月 2 天 -0.90 若混进衰减窗口，健康因子必被误判——这正是修复前的行为。"""
    body = _report_body(capsys)
    on_block = body.split("**overnight_intraday**")[1].split("- **ivol**")[0]
    assert "✅ 未衰减" in on_block, f"残月噪声污染了衰减判定: {on_block}"


def test_report_month_slice_is_bounded(_fake_baselines, capsys):
    """7 月月报里的'本月'不得包含 8 月数据（8 月被造成 -0.90，混入必然穿帮）。"""
    body = _report_body(capsys)
    on_line = [l for l in body.splitlines() if "**overnight_intraday**" in l][0]
    # 7 月共 23 个工作日，若把 8 月 2 天算进来会变成 25
    assert "（23 个交易日）" in on_line, f"当月切片未按月封顶: {on_line}"
    cur = float(on_line.split("本月 RankIC ")[1].split("（")[0])
    assert np.isclose(cur, 0.05, atol=1e-6), f"本月均值被 8 月数据污染: {cur}"


def test_report_marks_frequency_in_decay_line(_fake_baselines, capsys):
    body = _report_body(capsys)
    assert "滚动衰减（**月频**" in body, "衰减行必须显式标注频率，避免再次单位错配"
    assert f"不足 {MIN_DAYS_PER_MONTH} 个交易日的残月已剔除" in body
