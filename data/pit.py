"""Point-In-Time（PIT）派生量：从当日可观测字段现算，不依赖任何快照回填。

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🔴 本模块存在的理由（2026-08-08 踩坑记录，勿删）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
面板里的 `market_cap` 列**不是 PIT 数据**：BaoStockProvider / AkShareProvider 都是
取"今天"的总市值快照，然后 `df["asset"].map(mcap)` 贴到该股票的**全部历史日期**上
（见 data/providers.py::_share_map / _market_cap_map）。所以同一只票 2000 年那天的
market_cap 等于它 2026 年的市值——时间序列上 nunique == 1。

后果（实测，400 票随机样本）：

    日期           静态 vs PIT 排序相关   大小盘分组一致率
    2013-05-07     0.504                  53.7%
    2022-08-09     0.624                  55.3%
    2026-08-05     0.959                  88.6%

即历史上近一半个股会被分进**错误的**市值档；且偏差有方向性——被判成"小盘"的
是"到今天仍然小的公司"，天然剔除了当年小、后来长成巨头的票。用它做
小盘/大盘分组 = 后视选股，做出来的价差信号会好看但全假。

⚠️ 与 exec_lag 是同一类坑：`assert_no_lookahead` 只检查 **compute 有没有切到 t 之后
的行**，它管不了**面板某一列本身被未来信息污染**。审计过 ≠ 无前视。

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PIT 流通市值口径
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    float_mcap_t = amount_t / (turnover_t / 100)

    amount   当日成交额，单位元，**真实货币**，不受复权影响
    turnover 当日换手率，单位 %，定义 = volume / 流通股本

    => amount / (turnover/100) = vwap_real × 流通股本 = 当日真实流通市值

三个字段全是 t 日当天可观测量，既无前视，也不依赖前复权价格水平
（close 是前复权价，其"水平"本身含未来分红信息，故刻意不用 close × 股本）。

校验：000001.SZ 2026-07-31，amount=2.3188e9 / (1.0435/100) = 2222 亿，
与东财总市值快照 2179 亿量级一致（差异来自流通/总口径与 VWAP/收盘口径）。

局限（已知，可接受）：
1. 得到的是**流通**市值不是总市值；做截面分档无影响，绝对值口径需注明。
2. 停牌/近乎零成交日 turnover→0，会炸出天量市值 → 已用下限过滤 + 多日中位数平滑。
3. 与东财口径存在系统性小偏差；**只用于截面排序**时无影响。
"""
from __future__ import annotations

import numpy as np
import pandas as pd

__all__ = ["pit_float_mcap", "MIN_TURNOVER_PCT"]

# 换手率下限（%）：低于此值视为停牌/异常，不参与市值估算。
# 0.01% 对应千分之一手级别的成交，A 股正常交易日几乎不会触及。
MIN_TURNOVER_PCT = 0.01


def pit_float_mcap(
    panel: pd.DataFrame,
    as_of,
    lookback: int = 5,
    min_turnover_pct: float = MIN_TURNOVER_PCT,
) -> pd.Series:
    """截至 as_of（含）的 PIT 流通市值估计，单位元。

    Args:
        panel: MultiIndex (date, asset) 面板，需含 ``amount`` 与 ``turnover`` 列。
        as_of: 目标日期；**只使用 <= as_of 的行**（前视安全）。
        lookback: 回看交易日数，取窗口内**中位数**以平滑单日换手异常。
                  1 = 只用当日。O(lookback × 截面)，lookback 取个位数即可。
        min_turnover_pct: 换手率下限（%），低于此值的样本剔除。

    Returns:
        Series: index=asset，值=流通市值（元）；无有效样本的票不出现在结果里。

    前视保证：切片上界为 as_of，窗口内所有数据均已发生。
    """
    if not {"amount", "turnover"}.issubset(panel.columns):
        return pd.Series(dtype="float64")

    dates = panel.index.get_level_values("date")
    # 单次掩码：先在"日期唯一值"这个小集合上定位窗口，再一次性切面板。
    # （逐日调用时若先切 hist 再 unique，等于对千万行做两遍扫描，明显更慢。）
    uniq = dates.unique().sort_values()
    uniq = uniq[uniq <= as_of]
    if len(uniq) == 0:
        return pd.Series(dtype="float64")
    window = uniq[-max(1, int(lookback)):]
    win = panel[dates.isin(window)]
    if win.empty:
        return pd.Series(dtype="float64")

    amount = win["amount"].astype("float64")
    turn = win["turnover"].astype("float64")

    mcap = amount / (turn / 100.0)
    valid = (turn >= min_turnover_pct) & (amount > 0) & np.isfinite(mcap) & (mcap > 0)
    mcap = mcap[valid]
    if mcap.empty:
        return pd.Series(dtype="float64")

    out = mcap.groupby(level="asset").median()
    return out.dropna()
