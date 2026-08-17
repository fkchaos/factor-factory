"""测试 fixtures：确定性合成面板 + 合规/违规因子样例。

用合成数据（不依赖网络）做可复现测试，重点是验证前视防护。
"""
import numpy as np
import pandas as pd
from factors.interface import Factor


def _make_panel(n_days: int = 10, seed: int = 42):
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2024-01-01", periods=n_days, freq="D")
    assets = ["A", "B", "C"]
    idx = pd.MultiIndex.from_product([dates, assets], names=["date", "asset"])
    # close 含单调递增趋势：未来数据必然 > 历史，便于检测前视
    base = np.arange(len(idx))
    panel = pd.DataFrame(
        {"close": base + rng.random(len(idx)) * 0.1},
        index=idx,
    )
    return panel


PANEL = _make_panel()


class CleanFactor:
    """合规因子：只用 as_of_date 当天（及之前切片后）的数据。"""
    name = "clean_momentum"

    def compute(self, panel, as_of_date, ctx=None) -> pd.Series:
        sub = panel.xs(pd.Timestamp(as_of_date), level="date")
        return sub["close"].rank()


class LeakyFactor:
    """违规因子：无视 as_of_date，偷用全样本最大值（含未来）。用于演示前视危害。"""
    name = "leaky_max"

    def compute(self, panel, as_of_date, ctx=None) -> pd.Series:
        return panel["close"].groupby(level="asset").max()


class GlobalStatFactor:
    """违规因子：用全样本均值做标准化（全局统计量 = 回测作弊）。"""
    name = "leaky_global_z"

    def compute(self, panel, as_of_date, ctx=None) -> pd.Series:
        s = panel.xs(pd.Timestamp(as_of_date), level="date")["close"]
        # BUG: 用全样本 mean/std 而非截面日
        return (s - panel["close"].mean()) / panel["close"].std()
