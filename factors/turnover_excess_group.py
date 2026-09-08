"""组内换手异常超出幅度因子（turnover_excess_group）· f0059a。

对应灵感池 i20260805-010（forum）：分组内，过去 21 日中日换手率超过组内 80% 分位
阈值的那些交易日，其**超出幅度均值**越大 → 未来 20 日收益越高。

机制
----
度量的是"相对同类基准的持续异常换手"= 增量资金定向流入，而不是结构性高流动性
（后者是规模/流动性风险暴露，不是 alpha）。分组内取阈值 = 先剥掉同类基准水平，
剩下的超出部分才是资金流信息。

实现（turnover + PIT 流通市值，向后看，W=21）
---------------------------------------------
    mcap_pit_t = median( amount/(turnover/100), 近 5 日 ) 后 **shift(1)**   （前一日口径）
    grp_t      = 按 mcap_pit_t 的当日截面分位三等分（0=小盘 / 1=中盘 / 2=大盘）
    thr_t,g    = 第 g 组当日截面 turnover 的 80% 分位
    excess_t   = max(turnover_t − thr_{t,grp_t}, 0)
    factor     = excess 的近 21 日滚动均值（0 也计入分母，即"异常强度×频率"的联合度量）

⚠️ 与原假设的差异：**行业维度降级**（如实声明，不隐瞒）
--------------------------------------------------------
原条目是"行业 × 市值"双维分组。当前 baostock 面板契约（open/high/low/close/
volume/amount/turnover/market_cap）**不含行业分类列**，故本因子只做**市值三分组**，
行业维度缺失。后果：同组内混合了行业结构性换手差异（如券商板块天然高换手），
阈值因此偏高，会削弱因子。补上行业列后应作为 f0059**b** 重出并与本包对比，
而不是原地改口径（改了口径就无法归因是行业维度的贡献还是噪声）。

🔴 市值列 PIT 纪律
------------------
分组**不用**面板的 `market_cap` 列——该列是 provider 把今日市值快照回填全历史的
假 PIT 列（`nunique()==1`，2026-08-08 事件，见 data/pit.py 与 HANDOFF §0.5）。
用它分组等于"按今天仍然小的公司"选股 = 后视选股。本因子按 pit.py 同一公式现算
流通市值（amount/(turnover/100) = VWAP×流通股本，全为当日可观测量），并取
**前一日**近 5 日中位数，避免当日涨幅推高市值排名而污染分组。

阈值 80% 分位为**原假设给定的构造常数**，非我方调参所得；未做任何阈值搜索。

冗余提示：与 f0011a/f0012a/f0013a/f0017a（各期限平均换手率）都用 turnover，但
那些是**水平量**，本因子是**相对同类基准的超出量**（已剥离组内水平）。须核对
correlation.csv；若相关 >0.8 说明分组去均值没起作用，应降级。

compute_panel 一次性向量化全序列（groupby.quantile + reindex，不用 apply）。
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from factors.interface import register_factor

W = 21              # 滚动窗口（交易日）
MCAP_LOOKBACK = 5   # PIT 流通市值中位数窗口
N_GROUP = 3         # 市值分组数
Q = 0.8             # 组内阈值分位（原假设给定）
MIN_TURNOVER_PCT = 0.01  # 与 data/pit.py 同一下限，低于此视为停牌/异常


class TurnoverExcessGroupFactor:
    """组内换手异常超出幅度：max(turnover − 组内80%分位, 0) 的 21 日均值。"""

    name = "turnover_excess_group"
    fcode = "f0059a"
    universe_hint = None

    def _full(self, panel: pd.DataFrame) -> pd.Series:
        sub = panel.sort_index()
        to = sub["turnover"]
        amount = sub["amount"]

        # --- PIT 流通市值（与 data/pit.py 同公式，全序列向量化） ---
        to_ok = to.where(to >= MIN_TURNOVER_PCT)
        with np.errstate(divide="ignore", invalid="ignore"):
            mcap_raw = amount / (to_ok / 100.0)
        mcap_raw = mcap_raw.replace([np.inf, -np.inf], np.nan)
        MC = mcap_raw.unstack(level="asset")
        # 近 5 日中位数后 shift(1)：只用前一日及更早，防当日涨幅污染分组排序
        MC = MC.rolling(MCAP_LOOKBACK, min_periods=2).median().shift(1)

        # --- 按市值截面分位三等分 ---
        pct = MC.rank(axis=1, pct=True, na_option="keep")
        grp = np.floor(pct * N_GROUP).clip(upper=N_GROUP - 1)   # 0/1/2

        TO = to.unstack(level="asset")
        TO = TO.where(grp.notna())            # 无分组的样本不参与

        # --- 组内当日 80% 分位阈值（长表 groupby.quantile 后 reindex 回宽表） ---
        long = pd.DataFrame({
            "to": TO.stack(),
            "grp": grp.stack(),
        }).dropna()
        if long.empty:
            return pd.Series(dtype=float)
        dates = long.index.get_level_values(0)
        thr_tbl = long.groupby([dates, long["grp"]])["to"].quantile(Q)
        key = pd.MultiIndex.from_arrays([dates, long["grp"].values])
        thr = pd.Series(thr_tbl.reindex(key).values, index=long.index)

        excess = (long["to"] - thr).clip(lower=0.0)
        E = excess.unstack(level="asset").reindex(columns=TO.columns)
        out = E.rolling(W, min_periods=max(5, W // 2)).mean()
        return out.stack().reindex(to.index)

    def compute(self, panel: pd.DataFrame, as_of_date, ctx=None) -> pd.Series:
        t = pd.Timestamp(as_of_date)
        return self._full(panel).xs(t, level="date").dropna().rename(self.name)

    def compute_panel(self, panel: pd.DataFrame) -> pd.DataFrame:
        return self._full(panel).unstack(level="asset")


register_factor(TurnoverExcessGroupFactor())
