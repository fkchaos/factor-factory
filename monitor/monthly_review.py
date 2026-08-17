"""月度评审：因子 5 项体检 + 决策输出（月报生成器）。

体检项（对齐 docs/MONTHLY_REVIEW_TEMPLATE.md 与计划「持续迭代节奏」）：
1. 健康度：本月 RankIC/ICIR vs 全期均值（因子还在不在干活）
2. 滚动衰减：20/60 日滚动 IC 与长期均值差（信号衰减预警）
3. 拥挤度：组合权重集中度 HHI / 最大权重（复用 FactorMonitor）
4. 组合归因：因子收益贡献拆解（复用 FactorMonitor）
5. 墓地复检：已淘汰因子复苏迹象（读因子卡片"墓地"状态，提示人工复核）

用法：
    # 首次：生成逐日 IC 基线（落盘 .cache/review/ic_{factor}.csv）
    python monitor/monthly_review.py baseline [--pool hs800] [--start 2020-01-01]
    # 月度：读基线生成月报（markdown 输出到 stdout，或 --out 写文件）
    python monitor/monthly_review.py report [--month 2026-07] [--out research/monthly/2026-07.md]

决策输出：每个因子判定 保留/降权/停用/复活 → 更新因子卡片（提示人工确认）。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from data.providers import BaoStockProvider
from factors.overnight_intraday import OvernightIntradayFactor
from factors.ivol import IvolFactor
from engine.interface import BacktestConfig
from validate.validator import validate_factor
from monitor.monitor import FactorMonitor

REVIEW_DIR = ROOT / ".cache" / "review"
FACTORS = [OvernightIntradayFactor(), IvolFactor()]
DEFAULT_POOL = "hs800"
# 残月（如月初仅 2 个交易日）不参与衰减判定，否则 2 天噪声会主导"近 3 月"结论
MIN_DAYS_PER_MONTH = 10


def _to_monthly_ic(ic_daily: pd.Series, min_days: int = MIN_DAYS_PER_MONTH) -> pd.Series:
    """日频 IC → 月频均值 IC（喂给 check_ic_decay 前必须做的单位对齐）。

    🔴 单位对齐红线（2026-08-08 修）：`FactorMonitor.check_ic_decay` 的窗口配置名为
    `ic_breach_months`（默认 3 = 最近 **3 个月**），内部实现是 `ic_series.tail(3)`——
    窗口单位由**调用方喂进来的序列频率**决定。若直接把日频 IC 丢进去，取到的是
    "最近 3 个**交易日**"，纯噪声，且会与月度健康度判定自相矛盾。
    实测（2026-07 首期月报）：本月 IC +0.0184 判 "✅正常"，同条目却 decay=True /
    recent_mean_ic=-0.0909，而 -0.0909 正好等于 `ic.tail(3).mean()`——即最近 3 天。
    故衰减检测一律走本函数聚合到月频后再调用。
    """
    if not isinstance(ic_daily.index, pd.DatetimeIndex):
        ic_daily = ic_daily.copy()
        ic_daily.index = pd.to_datetime(ic_daily.index)
    grp = ic_daily.groupby(pd.Grouper(freq="ME"))
    monthly, counts = grp.mean(), grp.count()
    return monthly[counts >= min_days].dropna()


def _ic_history_path(name: str, pool: str = "sz50") -> Path:
    # 池子感知：避免多池基线互相覆盖（hs300/hs800/ALL 各自独立落盘）
    return REVIEW_DIR / f"ic_{name}_{pool}.csv"


# ---------- baseline：跑验证并落盘逐日 IC ----------
def cmd_baseline(args) -> None:
    REVIEW_DIR.mkdir(parents=True, exist_ok=True)
    prov = BaoStockProvider(universe=args.pool, history_start=args.start)
    cfg = BacktestConfig(train_days=252, test_days=126, step_days=63, top_n=20)
    # validate_factor 不暴露逐日 IC，这里用轻量实现（与 validator 同口径）
    from factors.interface import winsorize_mad, zscore_cross_section
    from validate.validator import _neutralize_cross_section
    from engine.interface import prepare_panel_for_factor

    fields = ["open", "high", "low", "close", "volume", "amount", "market_cap"]
    panel = prov.get_panel(fields, None, None)
    dates = sorted(panel.index.get_level_values("date").unique())
    for factor in FACTORS:
        ics = []
        for idx, t in enumerate(dates):
            ctx = {"start": str(dates[max(0, idx - cfg.train_days)])}
            sub = prepare_panel_for_factor(prov, factor, t, fields, ctx)
            fv = factor.compute(sub, t, ctx).dropna()
            fv = zscore_cross_section(_neutralize_cross_section(winsorize_mad(fv), panel, t, prov))
            if idx + 1 < len(dates):
                close_t = panel.xs(t, level="date")["close"]
                close_t1 = panel.xs(dates[idx + 1], level="date")["close"]
                r = close_t1 / close_t - 1.0
                common = fv.index.intersection(r.index)
                if len(common) >= 5:
                    ic = fv.loc[common].rank().corr(r.loc[common].rank())
                    ics.append((pd.Timestamp(t), float(ic)))
        df = pd.DataFrame(ics, columns=["date", "ic"]).set_index("date")
        df.to_csv(_ic_history_path(factor.name, args.pool))
        print(f"✅ {factor.name}: 基线 {len(df)} 日 IC 已落盘（均值 {df['ic'].mean():+.4f}）")


# ---------- report：5 项体检生成月报 ----------
def cmd_report(args) -> None:
    month = args.month or pd.Timestamp.now().strftime("%Y-%m")
    lines: list[str] = [f"# 因子月报 · {month}",
                        "", f"> 生成日期：{pd.Timestamp.now().date()} | 池子：{args.pool}",
                        "", "## 1. 健康度（本月 vs 全期）", ""]
    monitor = FactorMonitor()
    for factor in FACTORS:
        p = _ic_history_path(factor.name, args.pool)
        if not p.exists():
            lines.append(f"- ⚠️ {factor.name}: 无基线（先跑 `baseline`）")
            continue
        ic = pd.read_csv(p, index_col="date", parse_dates=True)["ic"]
        # 当月切片必须双边闭区间：原实现只有下界，"本月"实际含了之后所有月份
        m_start = pd.Timestamp(f"{month}-01")
        m_end = m_start + pd.offsets.MonthBegin(1)
        month_ic = ic[(ic.index >= m_start) & (ic.index < m_end)]
        long_mean = ic.mean()
        cur = month_ic.mean() if len(month_ic) else np.nan
        delta = cur - long_mean if np.isfinite(cur) else np.nan

        # 2. 滚动衰减（月频对齐后再判，见 _to_monthly_ic 单位对齐红线）
        monthly_ic = _to_monthly_ic(ic)
        decay = monitor.check_ic_decay(factor.name, monthly_ic)

        # 健康度须纳入衰减标记，否则"本月尚可"会掩盖近 N 月方向反转
        if not np.isfinite(delta):
            status = "❌ 无当月数据"
        elif decay.get("decay"):
            status = f"⚠️ 衰减预警（近 {monitor.ic_breach_months} 月均 IC 低于阈值）"
        elif delta > -0.01:
            status = "✅ 正常"
        else:
            status = "⚠️ 偏弱"
        lines.append(f"- **{factor.name}**: 本月 RankIC {cur:+.4f}（{len(month_ic)} 个交易日）"
                     f" vs 全期 {long_mean:+.4f}（差 {delta:+.4f}）→ {status}")

        if decay.get("reason") == "insufficient history":
            lines.append(f"  - 滚动衰减: 可用完整月数 {len(monthly_ic)} < "
                         f"{monitor.ic_breach_months}，样本不足暂不判定")
        else:
            flag = "⚠️ 衰减" if decay["decay"] else "✅ 未衰减"
            lines.append(
                f"  - 滚动衰减（**月频**，末 {monitor.ic_breach_months} 月均 IC）: "
                f"{decay['recent_mean_ic']:+.4f} vs 阈值 {decay['threshold']:.3f} → {flag}"
                f"｜可用完整月数 {len(monthly_ic)}（不足 {MIN_DAYS_PER_MONTH} 个交易日的残月已剔除）")

    lines += ["", "## 2. 拥挤度与归因（组合层面）", "",
              "- 组合权重集中度：由 portfolio/combiner 输出驱动（当前骨架，待接入实盘权重）",
              "- 因子贡献归因：待影子账户月度收益接入", ""]
    lines += ["## 3. 墓地复检", ""]
    graveyard = _scan_graveyard()
    lines.append(f"- 墓地因子：{graveyard if graveyard else '（当前无）'}")
    lines.append("- 复检提示：如市场结构变化（风格切换/流动性拐点），死因子可能复活，建议每季度重测一次。")
    lines += ["", "## 4. 决策输出", "",
              "| 因子 | 判定 | 依据 |", "|---|---|---|"]
    for factor in FACTORS:
        lines.append(f"| {factor.name} | 保留（待人工确认） | 本月体检自动判定，人工复核后更新因子卡片 |")
    lines += ["", "> ⚠️ 本报告为机器体检，最终决策（保留/降权/停用/复活）须人工评审后确认。", ""]

    body = "\n".join(lines)
    print(body)
    if args.out:
        out = ROOT / args.out
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(body, encoding="utf-8")
        print(f"\n📄 月报已保存: {out}")


def _scan_graveyard() -> list[str]:
    """扫描 research/factor_cards/ 中标注了墓地/淘汰状态的因子。"""
    graves = []
    cards_dir = ROOT / "research" / "factor_cards"
    if cards_dir.exists():
        for md in cards_dir.glob("*.md"):
            txt = md.read_text(encoding="utf-8")
            if any(k in txt for k in ("墓地", "淘汰", "状态：❌")):
                graves.append(md.stem)
    return graves


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("baseline")
    b.add_argument("--pool", default=DEFAULT_POOL)
    b.add_argument("--start", default="2020-01-01")
    b.set_defaults(func=cmd_baseline)
    r = sub.add_parser("report")
    r.add_argument("--pool", default=DEFAULT_POOL)
    r.add_argument("--month", default=None)
    r.add_argument("--out", default=None)
    r.set_defaults(func=cmd_report)
    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
