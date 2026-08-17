"""风险偏好 Regime 信号（Risk Appetite Regime）· s0002x。

计划来源：`docs/PLAN_SIGNAL_LINE.md` §6.1 灵感池 #1（P0）。

可证伪假设
----------
小盘股相对大盘股走强 = 市场风险偏好上行，此时横截面 alpha 因子（尤其反转/低波这类
小盘敏感因子）更容易赚钱；反之资金抱团大盘 = 避险环境，应压低因子暴露。
证伪条件：两态未来 1 日收益无差异，或叠加后 Sharpe / MaxDD 均不改善。

定义
----
- raw（连续值，天然零中枢）：
  `小市值组(后 30%) 当日收益均值 − 大市值组(前 30%) 当日收益均值`
  > 为什么必须是"差值型"：出包脚本的状态转换是 `MA(raw, W) > threshold`，默认 threshold=0。
  > 若 raw 恒正（波动率那类），就得人为挑阈值，而"挑一个好阈值"= 全样本窥探 = 隐性前视。
  > 差值型天然以 0 为界，阈值不需要拟合。见 PLAN_SIGNAL_LINE.md §6.1 硬门 #2。
- 状态（离散，在交付阶段由 MA20 平滑后阈值化）：
  `MA20(raw) > 0` → risk_on（风险偏好上行）；否则 risk_off。

🔴 坑 1：分组**不能用面板里的 market_cap 列**（2026-08-08 实测拦下）
------------------------------------------------------------------
`market_cap` 是**今日快照回填全历史**的假 PIT 列（provider 用
`df["asset"].map(今日市值)`，同一只票 26 年时序 nunique==1）。实测 2013 年用它分档，
与真实 PIT 市值的分组一致率只有 **53.7%**，且偏差有方向——被判"小盘"的是"到 2026 年
仍然小的公司"，等于后视选股。用它做小盘/大盘价差，信号会好看但全假。

故本信号一律用 `data.pit.pit_float_mcap()` 现算 PIT 流通市值
（= amount / (turnover/100)，全为当日可观测量）。详见该模块头部注释。

🔴 坑 2：分组必须用**前一交易日**的市值
--------------------------------------
若用当日市值分档，"今天大涨的股票"会被今天的涨幅推高市值排名，分组本身被当日收益
污染 → 小/大盘组收益差里混进机械性偏误（赢家自动变大盘）。故分组用截至 prev_date 的
市值、收益用 prev→as_of，两者严格错开。这不是前视（都是历史数据），是**排序污染**，
但同样会造出虚假区分度。

前视防护：只读 as_of 及之前的数据（分组窗口上界 = prev_date），通过 assert_no_lookahead。

与 s0001x（breadth_regime）的分工：breadth 量"参与度"（多少只股票在涨），
本信号量"风格偏好"（钱往大盘还是小盘去）。出包后须报告两者状态一致率，
一致率过高（>85%）说明信息重复，应降级。
"""
from __future__ import annotations

import pandas as pd

from data.pit import pit_float_mcap
from signals.interface import register_signal, slice_panel_to_date

MIN_STOCKS = 20    # 截面样本下限，不足则返回 NaN
MIN_PER_GROUP = 5  # 单组样本下限
MCAP_LOOKBACK = 5  # PIT 市值取近 5 日中位数，平滑单日换手异常


class RiskAppetiteSignal:
    name = "risk_appetite"
    scode = "s0002x"  # 交付包代号（对齐 deliverables/signals/_REGISTRY.csv）
    universe_hint = "hs800"  # 与 s0001x 同池，便于两信号直接比对状态一致率
    quantile = 0.30  # 前/后 30% 分档
    state_def = ("raw = 小市值组(后30%)日收益均值 − 大市值组(前30%)日收益均值"
                 "（市值=PIT流通市值 amount/换手率 的前一日近5日中位数，非面板 market_cap 快照列）；"
                 "状态 = raw_MA20 > 0 → risk_on（风险偏好上行），否则 risk_off")
    caveat = ("小盘组在流动性枯竭 / 批量停牌时代表性下降；风格极端切换期（2017 蓝筹行情、"
              "2021 抱团瓦解）价差含义会漂移。分组依赖 PIT 流通市值（amount/换手率现算），"
              "若 turnover 字段缺失比例升高会静默降低分组质量，需与其他 regime 信号交叉验证。")

    def compute(self, panel: pd.DataFrame, as_of_date, ctx=None) -> float:
        as_of = pd.Timestamp(as_of_date)
        sub = slice_panel_to_date(panel, as_of)  # 双保险：只留 as_of 及之前
        try:
            day = sub.xs(as_of, level="date")
        except KeyError:
            return float("nan")

        prev_dates = [d for d in sub.index.get_level_values("date").unique() if d < as_of]
        if not prev_dates:
            return float("nan")
        prev_date = prev_dates[-1]
        prev = sub.xs(prev_date, level="date")

        prev_close = prev["close"].reindex(day.index).dropna()
        if len(prev_close) < MIN_STOCKS:
            return float("nan")
        ret = (day["close"].reindex(prev_close.index) / prev_close - 1.0).dropna()

        # 🔴 PIT 市值，窗口上界 = 前一交易日（既防前视，也防当日涨幅污染排序）
        mcap = pit_float_mcap(sub, prev_date, lookback=MCAP_LOOKBACK)
        if mcap.empty:
            return float("nan")
        mcap = mcap.reindex(ret.index).dropna()
        common = ret.index.intersection(mcap.index)
        if len(common) < MIN_STOCKS:
            return float("nan")
        ret, mcap = ret.loc[common], mcap.loc[common]

        lo, hi = mcap.quantile(self.quantile), mcap.quantile(1.0 - self.quantile)
        small, large = ret[mcap <= lo], ret[mcap >= hi]
        if len(small) < MIN_PER_GROUP or len(large) < MIN_PER_GROUP:
            return float("nan")
        return float(small.mean() - large.mean())


# 注册实例（供 get_signal 取用）
register_signal(RiskAppetiteSignal())
