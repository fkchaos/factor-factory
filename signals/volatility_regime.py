"""波动率 Regime 信号（Volatility Regime · 波动收缩/扩张）· s0003x。

计划来源：`docs/PLAN_SIGNAL_LINE.md` §6.1 灵感池（volatility 类）；
补位动机见 `docs/dev/HANDOFF.md`「下一步待办 #2」——前两个信号（s0001x 广度、
s0002x 风险偏好）都是**截面结构**类（多少只在涨 / 钱往大小盘去），类别不够散，
本信号从**时序二阶矩**切入，给策略组第三个正交视角。

可证伪假设
----------
波动率聚集（volatility clustering）+ 杠杆效应：市场波动**扩张**期通常伴随下跌与
尾部风险，波动**收缩**期风险调整后收益更优。故"近期波动低于前期波动"应是更适合
放开因子暴露的环境。
证伪条件：两态未来 1/5/20 日收益无差异，或叠加后 Sharpe 与 MaxDD 均不改善。

定义
----
- raw（连续值，**天然零中枢**）：
  `ln( RV_prior20 / RV_recent20 )`
  其中 `RV_recent20` = 最近 20 个交易日等权市场日收益的标准差，
  `RV_prior20` = 再往前 20 个交易日（与 recent **不重叠**）的同口径标准差。
  raw > 0 → 波动收缩（相对平静）；raw < 0 → 波动扩张（风险升温）。
- 状态（离散，交付阶段由 MA20 平滑后阈值化）：
  `MA20(raw) > 0` → risk_on（波动收缩，可放开暴露）；否则 risk_off。

🔴 为什么两条腿必须**等长且不重叠**（阈值免拟合，硬门 #2）
------------------------------------------------------------
出包脚本的状态转换固定为 `MA(raw, W) > threshold`，默认 threshold=0。
若 raw 是"波动率水平"这类恒正量，就必须人为挑一个阈值——而"挑一个好阈值"
= 全样本窥探 = 隐性前视（PLAN_SIGNAL_LINE.md §6.1 硬门 #2）。

本信号用两个**同样长度**的窗口做对数比值：平稳性假设下二者是同分布样本标准差，
`E[ln s_recent − ln s_prior] = 0` **精确成立**（对称性，不依赖分布形状），
所以 0 不是拟合出来的阈值，而是构造上的自然分界。
> 反例（本可采用但被否掉的写法）：`ln(RV60 / RV5)`。短窗样本标准差的
> `E[ln s]` 有向下偏（Jensen），窗口长度不同 → 比值存在系统性正偏，
> 阈值 0 会被这个偏置带跑，等于偷偷引入了一个"看过全样本才知道该减多少"的常数。

🔴 PIT 字段核验（硬门 #4，2026-08-08 假市值事件后新增）
--------------------------------------------------------
本信号**只读 `close` 一列**，不碰 `market_cap`（该列是今日快照回填全历史的假 PIT 列，
`nunique()==1`，详见 `data/pit.py` 与 docs/dev/HANDOFF.md §0.5）。close 为 qfq 前复权序列，
逐日随时间变化（非快照回填），且本信号只用其**日收益比值**，与 s0001x/s0002x
同口径。
> 已知残留：qfq 会在新分红除权时重算历史价格水平，但对**跨除权日之外的日收益**
> 无影响；全线信号/因子沿用同一约定，不在本信号单独处理。

与已交付信号的分工
------------------
- s0001x 广度：量"参与度"（多少只股票在涨）——一阶矩、截面。
- s0002x 风险偏好：量"风格偏好"（钱往大盘还是小盘）——一阶矩、截面结构。
- s0003x 本信号：量"风险温度"（市场波动在收缩还是扩张）——**二阶矩、时序**。
出包后必须跑 `scripts/signal_redundancy.py`，一致率 ≥85% 说明信息重复须降级。

前视防护：compute 只读 as_of 及之前的 close（窗口上界 = as_of 当日），
天然通过 assert_no_lookahead。
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from signals.interface import register_signal, slice_panel_to_date

WIN = 20          # 单腿窗口长度（交易日）；两腿等长是阈值免拟合的前提，改动前先读上文
MIN_STOCKS = 20   # 截面样本下限，不足则返回 NaN
MIN_OBS = 5       # 单腿有效收益样本下限


class VolatilityRegimeSignal:
    name = "volatility_regime"
    scode = "s0003x"          # 交付包代号（对齐 deliverables/signals/_REGISTRY.csv）
    universe_hint = "hs800"   # 与 s0001x/s0002x 同池，便于三信号直接比对状态一致率
    state_def = ("raw = ln( RV_prior20 / RV_recent20 )，RV = 等权市场日收益标准差，"
                 "两腿各 20 交易日且不重叠（等长 → 平稳性下期望为 0，阈值免拟合）；"
                 "状态 = raw_MA20 > 0 → risk_on（波动收缩），否则 risk_off（波动扩张）")
    caveat = ("🔴 实测方向与经济先验相反，不可按字面 risk_on 加仓：hs800 / 2015 起 2776 日样本"
              "（2026-08-12 出包 s0003x）显示 risk_off（波动扩张）后次日上涨率 55.3% 反而高于 "
              "risk_on 的 53.3%，命中率价差 −2.0%，叠加后 Sharpe 0.76→0.50（−0.26）。"
              "原因推测：A 股波动扩张多由**放量上涨**贡献（上行波动），并非只有下跌尾部。"
              "本信号的实际价值集中在**回撤削减**（MaxDD −45.49%→−34.12%，+11.38pct），"
              "宜作风险闸门而非收益增强器；按对方 §7.2 门槛（Sharpe>1.5 有效 / <1.0 证伪）判 refuted。"
              "⚠️ 我方刻意不因这个观测结果反转符号——那是看过全样本才改方向 = 数据窥探；"
              "若要用反向读法，须作为**新信号重新走一遍出包与审计**。")

    def compute(self, panel: pd.DataFrame, as_of_date, ctx=None) -> float:
        as_of = pd.Timestamp(as_of_date)
        sub = slice_panel_to_date(panel, as_of)  # 双保险：只留 as_of 及之前
        dates = sub.index.get_level_values("date").unique()
        if len(dates) == 0:
            return float("nan")
        dates = pd.DatetimeIndex(dates).sort_values()
        if dates[-1] != as_of:
            return float("nan")  # as_of 非交易日 / 无数据

        need = 2 * WIN + 1  # 40 个收益需要 41 个价格日
        if len(dates) < need:
            return float("nan")

        win = sub.loc[sub.index.get_level_values("date") >= dates[-need]]
        wide = win["close"].unstack("asset")
        if wide.shape[1] < MIN_STOCKS:
            return float("nan")

        # 等权市场日收益：先算个股收益再截面平均（不是"均价的收益"，避免高价股主导）
        mkt = wide.pct_change(fill_method=None).mean(axis=1, skipna=True).iloc[1:]
        mkt = mkt.dropna()
        if len(mkt) < 2 * MIN_OBS:
            return float("nan")

        recent, prior = mkt.iloc[-WIN:], mkt.iloc[-2 * WIN:-WIN]
        if len(recent) < MIN_OBS or len(prior) < MIN_OBS:
            return float("nan")

        rv_r, rv_p = float(recent.std(ddof=1)), float(prior.std(ddof=1))
        if not np.isfinite(rv_r) or not np.isfinite(rv_p) or rv_r <= 0 or rv_p <= 0:
            return float("nan")
        return float(np.log(rv_p / rv_r))


# 注册实例（供 get_signal 取用）
register_signal(VolatilityRegimeSignal())
