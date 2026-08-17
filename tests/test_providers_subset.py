"""TushareProvider 股票池子集分发测试（mock 接口，不连网）。

覆盖三种模式：list_status(L/D/P) / 交易所(SZ/SH/BJ) / 指数成分股(hs300 等)。
真实 index_weight / stock_basic 网络调用留待连接探测时验证。
"""
from __future__ import annotations

import pandas as pd
from pathlib import Path
from unittest import mock
import tushare as ts

from data.providers import TushareProvider


def _pro(stock_basic_df=None, index_weight_df=None):
    """构造 mock 的 tushare pro 接口对象。"""
    p = mock.MagicMock()
    if stock_basic_df is not None:
        p.stock_basic.return_value = stock_basic_df
    if index_weight_df is not None:
        p.index_weight.return_value = index_weight_df
    return p


def test_universe_list_status_L(tmp_path):
    sb = pd.DataFrame({"ts_code": ["000001.SZ", "600000.SH"]})
    with mock.patch.object(ts, "set_token"), \
         mock.patch.object(ts, "pro_api", return_value=_pro(stock_basic_df=sb)):
        prov = TushareProvider(token="fake", universe="L", cache_dir=str(tmp_path))
        assert prov._asset_list() == ["000001.SZ", "600000.SH"]
        prov._pro.stock_basic.assert_called_once()
        _, kwargs = prov._pro.stock_basic.call_args
        assert kwargs.get("list_status") == "L"


def test_universe_exchange_SZ(tmp_path):
    sb = pd.DataFrame({"ts_code": ["000001.SZ", "000002.SZ", "300750.SZ"]})
    with mock.patch.object(ts, "set_token"), \
         mock.patch.object(ts, "pro_api", return_value=_pro(stock_basic_df=sb)):
        prov = TushareProvider(token="fake", universe="SZ", cache_dir=str(tmp_path))
        assert prov._asset_list() == ["000001.SZ", "000002.SZ", "300750.SZ"]
        _, kwargs = prov._pro.stock_basic.call_args
        assert kwargs.get("exchange") == "SZ"


def test_universe_index_hs300_latest_snapshot(tmp_path):
    iw = pd.DataFrame({
        "trade_date": ["20231201", "20231201", "20240101", "20240101"],
        "con_code": ["600000.SH", "000001.SZ", "600000.SH", "000002.SZ"],
        "weight": [1.0, 1.0, 0.5, 0.5],
    })
    with mock.patch.object(ts, "set_token"), \
         mock.patch.object(ts, "pro_api", return_value=_pro(index_weight_df=iw)):
        prov = TushareProvider(token="fake", universe="hs300", cache_dir=str(tmp_path))
        assert prov._index_code_for_universe == "000300.SH"
        al = prov._asset_list()                      # 必须先调用，index_weight 才被触发
        prov._pro.index_weight.assert_called_once()  # 指数模式必须走 index_weight
        assert al == ["600000.SH", "000002.SZ"]


def test_universe_invalid_fallback_L(tmp_path):
    sb = pd.DataFrame({"ts_code": ["000001.SZ"]})
    with mock.patch.object(ts, "set_token"), \
         mock.patch.object(ts, "pro_api", return_value=_pro(stock_basic_df=sb)):
        prov = TushareProvider(token="fake", universe="garbage", cache_dir=str(tmp_path))
        assert prov._asset_list() == ["000001.SZ"]
        _, kwargs = prov._pro.stock_basic.call_args
        assert kwargs.get("list_status") == "L"
