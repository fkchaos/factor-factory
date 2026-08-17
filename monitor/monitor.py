"""监控看板骨架（monitor）：因子分布漂移 / IC 衰减 / 拥挤度 / 组合归因。

Phase 3 第一块。设计（对齐计划「持续迭代节奏」与 RESEARCH_LOG 监控需求）：
- 因子分布漂移：因子值均值/方差突变 = 失效预警（用滚动基线比较）。
- IC 衰减：RankIC 连续 N 期跌破阈值 -> 告警（因子衰退）。
- 拥挤度：组合权重集中度（HHI / 最大权重）-> 过度集中告警。
- 组合归因：按因子切分收益贡献（骨架，真实数据接入后完善）。

骨架原则：纯统计 + 阈值告警，不依赖真实数据源；可直接用 validator 产出的历史 IC 序列 / 组合权重驱动。
未来增强：接数据库存历史、生成日报、与影子账户联动。
"""
from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd


class FactorMonitor:
    def __init__(self,
                 ic_warn_threshold: float = 0.02,
                 ic_breach_months: int = 3,
                 distribution_z_threshold: float = 3.0,
                 crowding_hhi_threshold: float = 0.25):
        self.ic_warn = ic_warn_threshold
        self.ic_breach_months = ic_breach_months
        self.dist_z = distribution_z_threshold
        self.crowding_hhi = crowding_hhi_threshold
        self._history: dict[str, list] = {}

    # ---------- 因子分布漂移 ----------
    def check_distribution_drift(self, factor_name: str, current: pd.Series,
                                 baseline: pd.Series) -> dict:
        """current 与 baseline 截面分布比较，z 分数超阈值即告警。"""
        if len(current) < 5 or len(baseline) < 5:
            return {"drift": False, "z": np.nan, "reason": "insufficient data"}
        b_mean, b_std = baseline.mean(), baseline.std()
        c_mean = current.mean()
        if b_std == 0 or np.isnan(b_std):
            return {"drift": False, "z": np.nan, "reason": "baseline std=0"}
        z = (c_mean - b_mean) / b_std
        return {
            "drift": bool(abs(z) > self.dist_z),
            "z": float(z),
            "baseline_mean": float(b_mean),
            "current_mean": float(c_mean),
        }

    # ---------- IC 衰减 ----------
    def check_ic_decay(self, factor_name: str, ic_series: pd.Series) -> dict:
        """RankIC 序列末 ic_breach_months 期均低于阈值 -> 告警。"""
        recent = ic_series.tail(self.ic_breach_months)
        if len(recent) < self.ic_breach_months:
            return {"decay": False, "recent_mean_ic": float(recent.mean()) if len(recent) else np.nan,
                    "reason": "insufficient history"}
        recent_mean = recent.mean()
        self._history.setdefault(factor_name, []).extend(ic_series.tolist())
        return {
            "decay": bool(recent_mean < self.ic_warn),
            "recent_mean_ic": float(recent_mean),
            "threshold": self.ic_warn,
        }

    # ---------- 拥挤度 ----------
    def check_crowding(self, weights: dict[str, float]) -> dict:
        """组合权重 HHI；> 阈值即过度集中告警。"""
        w = np.array(list(weights.values()), dtype=float)
        if w.sum() != 0:
            w = w / w.sum()
        hhi = float(np.sum(w ** 2))
        max_w = float(w.max()) if len(w) else np.nan
        return {
            "crowded": hhi > self.crowding_hhi,
            "hhi": hhi,
            "max_weight": max_w,
            "threshold": self.crowding_hhi,
        }

    # ---------- 组合归因（骨架） ----------
    def attribute(self, factor_returns: dict[str, float]) -> dict:
        """按因子切分收益贡献（输入：各因子当期收益贡献）。"""
        total = sum(factor_returns.values())
        out = {k: {"contribution": v, "share": (v / total if total else np.nan)}
               for k, v in factor_returns.items()}
        out["total"] = total
        return out
