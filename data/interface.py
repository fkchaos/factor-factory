"""DataProvider 接口契约。

设计要点（见 ADR-0001 / RESEARCH_LOG R2026-0804-01,03,04,05）：
- 所有行情/财务取数只认此接口，核心逻辑不依赖具体数据源。
- **point-in-time 对齐是本层铁律**：get_pit_financials 必须按"公告日期 <= 交易日期"过滤，
  Tushare 等数据源不原生提供 PIT，由本层适配器负责。
- 适配器：TushareProvider（主）/ AkShareProvider（fallback）/ LocalProvider（测试）。
- **单位 / 格式契约（v61b 教训）**：所有返回值的单位、代码格式、索引名、复权口径由
  data/contract.py 集中定义并强制校验。切换数据源 MUST NOT 改变因子结果——
  详见 data/contract.py 的 PANEL_FIELDS / normalize_code / validate_panel。

返回契约速查（完整版见 data/contract.py）：
- get_panel 返回 MultiIndex(date, asset) 面板；date=datetime64[ns]；asset=规范代码 6位.交易所。
- 价格(open/high/low/close)=前复权 CNY；volume=股(shares)；amount=元；turnover=百分比；market_cap=元。
- get_index_returns 返回 datetime 索引、值为小数(0.01=+1%)的收益率序列。
- 缺失用 NaN，禁止 0 占位、禁止静默前填。
"""
from __future__ import annotations

from typing import Optional, Protocol, runtime_checkable, Iterable

import pandas as pd

from data.contract import INDEX_NAMES


@runtime_checkable
class DataProvider(Protocol):
    """行情与财务数据供给接口。所有方法返回值须满足 data/contract 契约。"""

    def get_panel(self, fields: list[str], start: str, end: str) -> pd.DataFrame:
        """返回 MultiIndex(date, asset) 面板，列=fields，已按契约做复权/单位/缺失对齐。

        实现 MUST 在返回前调用 data.contract.canonicalize_panel + validate_panel，
        确保索引名、代码后缀、价格/成交量/金额单位一致，否则抛错而非污染下游。
        实现 MUST 声明 `adj_policy` 类属性（"qfq"/"raw" 等），供框架复权口径防火墙校验——
        与契约 ADJ_POLICY 不一致时主流程须显式放行，禁止静默混入。
        """
        ...

    def get_index_returns(self, index_code: Optional[str] = None,
                          start: Optional[str] = None, end: Optional[str] = None) -> pd.Series:
        """返回指数日收益率序列（datetime 索引，值为小数 0.01=+1%），作市场收益基准。"""
        ...

    def get_pit_financials(self, fields: list[str], as_of_date: str) -> pd.DataFrame:
        """返回截至 as_of_date 实际可获得的财报字段（按公告日期 <= as_of_date 过滤）。

        这是防幸存者/前视偏差的关键：只暴露当时市场已知的信息。
        """
        ...

    def list_universe(self, date: str) -> list[str]:
        """返回 date 当日的股票池（point-in-time 成分股，不含已退市/未上市），规范代码格式。"""
        ...

    def get_adv(self, date: str, window: int = 20) -> pd.Series:
        """返回各股截至 date 的日均成交量（股），用于成本模型与流动性约束。"""
        ...
