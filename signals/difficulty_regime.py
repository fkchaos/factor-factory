"""「难做指数」市场状态信号（Difficulty Regime · 好做/难做）· s0004x。

计划来源：灵感池 i20260903-006（sell_side，《基于市场状态划分的机器学习ALPHA因子构建》）。
补位动机：已交付三信号 s0001x（广度·参与度，一阶矩截面）、s0002x（风险偏好·风格结构，
一阶矩截面）、s0003x（波动率 Regime，二阶矩时序）刻画的都是"市场涨不涨/波不波"。
本信号换一个维度：**当前环境对因子选股本身是否友好**（alpha 可提取难度），
给策略组第四个正交视角——它决定"要不要放开因子暴露"，而非"要不要加仓"。

可证伪假设
----------
截面 alpha 的可提取性随市场状态变化：当**截面收益离散度高**（个股分化大 → 排序噪声大）、
**市场绝对收益大**（beta 主导 → 截面信息被系统性冲击淹没）、**截面排名日间自相关低**
（今天的赢家明天变输家 → 排序不可延续）三者同时出现时，因子打分最难兑现。
故"好做"状态下基准因子的未来 IC 应显著高于"难做"状态。
证伪条件：两态下未来 1/5/20 日收益与 IC 均无差异，或叠加后 Sharpe 与 MaxDD 均不改善。

定义
----
- 三个分量（全部只用 T 日及之前的 close）：
  1. `disp_t`  = 当日跨资产日收益的横截面标准差（离散度）
  2. `absmkt_t`= |当日等权市场日收益|（beta 冲击强度）
  3. `ac_t`    = 当日截面收益排名 与 前一日截面收益排名 的相关（排名延续性）
- 难做指数：`difficulty_t = z(disp_t) + z(absmkt_t) − z(ac_t)`
- raw（交付值，**天然零中枢**）：`raw_t = − difficulty_t / 3`
  raw > 0 → easy（好做，可放开因子暴露）；raw < 0 → hard（难做，宜收敛暴露）。
- 状态（离散，出包阶段由 MA20 平滑后阈值化）：`MA20(raw) > 0` → risk_on(easy)，否则 risk_off(hard)。

🔴 z 用**滚动 250 日**而非样本内中位数（与原条目落地要点②的差异，须明示）
--------------------------------------------------------------------------
原条目建议"用样本内（截止某历史时点）中位数并永久冻结"作阈值。本工厂改用
**滚动 250 日 z-score**，理由是硬门 #2（PLAN_SIGNAL_LINE.md §6.1）：出包脚本的
状态转换固定为 `MA(raw, W) > 0`，raw 必须**构造上**零中枢，否则"挑一个阈值"=
全样本窥探。滚动 z 满足 `E[x_t − mean(x_{t−249..t})] = 0`（同分布样本，与分布形状无关），
因此 0 是构造性分界，而不是拟合出来的常数；同时它自适应长期漂移，
不需要"冻结某个历史时点"这种带有选择自由度的动作。
> 代价：raw 的量纲变成"相对过去一年的相对难度"，无法回答"绝对难度"。
> 这是刻意取舍——绝对水平阈值必然要窥探全样本。

🔴 只交付**状态标量**，不交付分域权重
------------------------------------
原假设后半段（在好做/难做子样本上分别估计因子合成权重，再两套打分等权合成）属于
**策略组职责**（本工厂不产出组合权重、不产出风控参数，见 ARCHITECTURE 交付原则）。
本信号只交付市场级状态标量，策略组可自行按状态分域估权。因此本包**不验证**原假设
中"两套子模型时序相关 <0.6""合成 ICIR 高于单套基线"这两条——它们需要组合层实验，
不在信号线交付范围内，卡片不得声称已验证。

🔴 PIT 字段核验（硬门 #4）
--------------------------
本信号**只读 `close` 一列**，不碰 `market_cap`（今日快照回填全历史的假 PIT 列，
`nunique()==1`，见 data/pit.py 与 HANDOFF §0.5）。close 为 qfq 前复权序列，逐日
变化，本信号只用其**日收益与截面排名**，与 s0001x/s0002x/s0003x 同口径。

冗余提示：出包后必须跑 `scripts/signal_redundancy.py` 与三个已交付信号两两比一致率，
≥85% 说明信息重复须降级。注意 disp 分量与 f0042a（分歧度代理）的截面离散概念邻近，
但本信号是**市场级标量**、且叠加了排名延续性与 beta 冲击两个分量。

前视防护：compute 只读 as_of 及之前的 close（窗口上界 = as_of 当日），
天然通过 assert_no_lookahead。
执行滞后：状态的可交易性由 `exec_lag=1` 在出包阶段强制（禁止同期收益评估）。
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from signals.interface import register_signal, slice_panel_to_date

Z_WIN = 250       # 滚动 z 窗口（约一年交易日）
MIN_STOCKS = 20   # 截面样本下限
MIN_Z_OBS = 200   # 滚动 z 有效样本下限


class DifficultyRegimeSignal:
    name = "difficulty_regime"
    scode = "s0004x"
    universe_hint = "hs800"   # 与 s0001x/s0002x/s0003x 同池，便于四信号状态一致率比对
    state_def = ("raw = −[ z(截面收益离散度) + z(|等权市场日收益|) − z(截面收益排名日间相关) ] / 3，"
                 "z 为滚动 250 日标准化（E[·]=0 → 阈值免拟合）；"
                 "状态 = raw_MA20 > 0 → risk_on(easy 好做，可放开因子暴露)，否则 risk_off(hard 难做)")
    caveat = ("⚠️ 三点必读：①本信号度量的是**因子可提取性**，不是**市场涨跌**——risk_on 不等于"
              "'该加仓'，而是'该放开因子暴露'；直接当择时用属误用。②难做指数公式为**我方自研代理**，"
              "原研报未公开其公式，卡片里的 IC 分组数字（原文 −24.66% 秩相关等）不可视为本实现的实证，"
              "本包只提供自身样本上的实测。③原假设后半段'状态分域估权再合成'属策略组职责，"
              "本包**未验证**该部分，只交付状态标量。④z 窗口 250 日为构造常数（≈一年），"
              "未做窗口搜索；若后续调窗口须作新 s-code 重走审计，不得原地改。")

    def compute(self, panel: pd.DataFrame, as_of_date, ctx=None) -> float:
        as_of = pd.Timestamp(as_of_date)
        sub = slice_panel_to_date(panel, as_of)   # 双保险：只留 as_of 及之前
        dates = sub.index.get_level_values("date").unique()
        if len(dates) == 0:
            return float("nan")
        dates = pd.DatetimeIndex(dates).sort_values()
        if dates[-1] != as_of:
            return float("nan")                  # as_of 非交易日 / 无数据

        need = Z_WIN + 3                          # 250 日 z + pct_change + 排名前一日
        if len(dates) < need:
            return float("nan")

        win = sub.loc[sub.index.get_level_values("date") >= dates[-need]]
        wide = win["close"].unstack("asset")
        if wide.shape[1] < MIN_STOCKS:
            return float("nan")

        R = wide.pct_change(fill_method=None).iloc[1:]
        if len(R) < MIN_Z_OBS + 1:
            return float("nan")

        # 分量 1/2：截面离散度、市场绝对收益
        disp = R.std(axis=1, ddof=1, skipna=True)
        absmkt = R.mean(axis=1, skipna=True).abs()

        # 分量 3：截面排名日间相关（向量化 Spearman：逐行标准化后与前一日逐元素相乘取均值）
        Rr = R.rank(axis=1, na_option="keep")
        mu = Rr.mean(axis=1, skipna=True)
        sd = Rr.std(axis=1, ddof=0, skipna=True).replace(0.0, np.nan)
        Rz = Rr.sub(mu, axis=0).div(sd, axis=0)
        ac = (Rz * Rz.shift(1)).mean(axis=1, skipna=True)

        def _z_last(s: pd.Series) -> float:
            s = s.dropna()
            if len(s) < MIN_Z_OBS:
                return float("nan")
            w = s.iloc[-Z_WIN:]
            m, sd_ = float(w.mean()), float(w.std(ddof=1))
            if not np.isfinite(sd_) or sd_ <= 0:
                return float("nan")
            return (float(s.iloc[-1]) - m) / sd_

        z_disp, z_absmkt, z_ac = _z_last(disp), _z_last(absmkt), _z_last(ac)
        if not all(np.isfinite(v) for v in (z_disp, z_absmkt, z_ac)):
            return float("nan")

        difficulty = z_disp + z_absmkt - z_ac
        return float(-difficulty / 3.0)


# 注册实例（供 get_signal 取用）
register_signal(DifficultyRegimeSignal())
