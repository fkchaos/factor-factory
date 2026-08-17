"""监控看板骨架测试（Phase 3 第一块）。

无需联网：用合成序列验证告警逻辑（分布漂移 / IC 衰减 / 拥挤度 / 归因）。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pandas as pd

from monitor.monitor import FactorMonitor


def test_distribution_drift_detected():
    m = FactorMonitor()
    base = pd.Series(np.random.default_rng(1).normal(0, 1, 200))
    cur = pd.Series(np.random.default_rng(2).normal(8, 1, 200))  # 均值显著偏移
    r = m.check_distribution_drift("f1", cur, base)
    assert r["drift"] is True
    assert abs(r["z"]) > 3.0


def test_distribution_no_drift():
    m = FactorMonitor()
    base = pd.Series(np.random.default_rng(1).normal(0, 1, 200))
    cur = pd.Series(np.random.default_rng(3).normal(0.1, 1, 200))
    r = m.check_distribution_drift("f1", cur, base)
    assert r["drift"] is False


def test_ic_decay_alert():
    m = FactorMonitor(ic_warn_threshold=0.02, ic_breach_months=3)
    ic = pd.Series([0.05, 0.04, 0.01, 0.005, 0.0])  # 末 3 期 < 0.02
    r = m.check_ic_decay("f1", ic)
    assert r["decay"] is True


def test_ic_no_decay():
    m = FactorMonitor(ic_warn_threshold=0.02, ic_breach_months=3)
    ic = pd.Series([0.05, 0.04, 0.03, 0.025, 0.02])
    r = m.check_ic_decay("f1", ic)
    assert r["decay"] is False


def test_crowding():
    m = FactorMonitor(crowding_hhi_threshold=0.25)
    concentrated = {"a": 0.8, "b": 0.1, "c": 0.1}   # HHI = 0.66 > 0.25
    diversified = {"a": 0.34, "b": 0.33, "c": 0.33}  # HHI ≈ 0.33 > 0.25 仍集中
    even = {"a": 0.25, "b": 0.25, "c": 0.25, "d": 0.25}  # HHI = 0.25
    assert m.check_crowding(concentrated)["crowded"] is True
    assert m.check_crowding(even)["crowded"] is False


def test_attribution():
    m = FactorMonitor()
    a = m.attribute({"overnight": 0.02, "ivol": -0.01})
    assert abs(a["total"] - 0.01) < 1e-9
    assert abs(a["overnight"]["share"] - 2.0) < 1e-9
