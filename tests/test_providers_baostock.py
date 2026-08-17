"""BaoStockProvider 单元测试：代码转换 / 结果集迭代 / 契约扩列（不依赖网络）。

网络相关的真实取数验证走 scripts/cross_source_check.py --source baostock 与
.cache 下 smoke 脚本（见 docs/PLAN_BAOSTOCK_PROVIDER.md 测试计划）。
"""
from __future__ import annotations

import pandas as pd
import pytest

from data.contract import PANEL_FIELDS, normalize_code
from data.providers import BaoStockProvider


# ---- 代码转换 ----
@pytest.mark.parametrize("raw,expected", [
    ("600000.SH", "sh.600000"),
    ("000001.SZ", "sz.000001"),
    ("300750.SZ", "sz.300750"),
    ("830000.BJ", "bj.830000"),
    ("430047.BJ", "bj.430047"),
    ("600519", "sh.600519"),      # 无后缀兜底：6 开头 → sh
    ("000001", "sz.000001"),      # 无后缀兜底：0/3 开头 → sz
    ("830000", "bj.830000"),      # 无后缀兜底：4/8 开头 → bj
])
def test_to_bs_code(raw, expected):
    assert BaoStockProvider._to_bs_code(raw) == expected


# ---- contract.normalize_code 新增 sh.600000 格式（baostock 带点前缀）----
@pytest.mark.parametrize("raw,expected", [
    ("sh.600000", "600000.SH"),
    ("sz.000001", "000001.SZ"),
    ("bj.830000", "830000.BJ"),
    ("sh.600028", "600028.SH"),
    ("600000.SH", "600000.SH"),   # 原有格式不回归
    ("sz000001", "000001.SZ"),    # 原有格式不回归
    ("000001", "000001.SZ"),      # 原有格式不回归
])
def test_normalize_code_baostock_format(raw, expected):
    assert normalize_code(raw) == expected


# ---- _collect_rows：手动迭代（绕开 pandas2 兼容 bug 的核心）----
class _FakeRS:
    """模拟 baostock resultset：error_code/fields/next()/get_row_data()。"""

    def __init__(self, rows, error_code="0"):
        self.error_code = error_code
        self.fields = ["date", "code", "close"]
        self._rows = rows
        self._i = 0

    def next(self):
        if self._i < len(self._rows):
            self._i += 1
            return True
        return False

    def get_row_data(self):
        return self._rows[self._i - 1]


def test_collect_rows_ok():
    rs = _FakeRS([["2024-01-02", "sh.600000", "10.5"], ["2024-01-03", "sh.600000", "10.6"]])
    rows = BaoStockProvider._collect_rows(rs)
    assert len(rows) == 2
    assert rows[0] == {"date": "2024-01-02", "code": "sh.600000", "close": "10.5"}
    assert rows[1]["close"] == "10.6"


def test_collect_rows_empty():
    assert BaoStockProvider._collect_rows(_FakeRS([])) == []


def test_collect_rows_error_code():
    rs = _FakeRS([["2024-01-02", "sh.600000", "10.5"]], error_code="10000")
    assert BaoStockProvider._collect_rows(rs) == []


def test_collect_rows_none():
    assert BaoStockProvider._collect_rows(None) == []


# ---- 契约扩列：baostock 独有字段 ----
def test_contract_has_baostock_markers():
    assert "tradestatus" in PANEL_FIELDS
    assert "is_st" in PANEL_FIELDS
    # 0/1 标记字段语义区间正确
    assert PANEL_FIELDS["tradestatus"][2] == (0.0, 1.0)
    assert PANEL_FIELDS["is_st"][2] == (0.0, 1.0)


# ---- _safe_float：空串/非法 → default ----
def test_safe_float():
    f = BaoStockProvider._safe_float
    assert f("3.14") == 3.14
    assert f("") is None
    assert f(None) is None
    assert f("abc", 0.0) == 0.0
