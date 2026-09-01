"""PIT 基本面访问层（财报类因子专用）。

把 [资产 × as_of] 的 PIT 财报快照取数封装成一个**可复用、内存缓存**的服务，
避免回测逐日循环里每 (资产, 日) 都重读磁盘 / 重联网。

🔴 红线（与 AkShareProvider.get_pit_financials 同一套逻辑，复用 providers._pit_select_snapshot）：
  - 快照严格按 pubDate <= as_of 过滤（无前视）。
  - 字段独立取数（利润表 / 资产负债表各自只带部分字段，互补不覆盖）。
  - 重述取最新版（pubDate 最大）。
  - 取数频率：逐 as_of 取"截至该日最新已披露"快照，回测逐交易日调用 = PIT 安全。

为什么单独一层：harness 的 compute_factor_series 逐日循环调 factor.compute，
若每次都走 get_pit_financials（每 (资产, 日) 重读 parquet）对 hs300×1500 日 = 45 万次
磁盘读，不可接受。本服务在构建时**一次性**把全宇宙每只股票的披露历史载入内存
（provider 内部仍按 .parquet 落盘缓存，断点可续），之后每一个 as_of 只是内存里的
字段独立选择，O(资产) 极快。

数据源：当前只有 AkShare 东财明细表能返 cogs/inventory/accounts_receivable
（baostock 免费接口这三字段在 _PIT_FIELD_UNAVAILABLE）。故服务以 AkShareProvider 为后端。
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from data.contract import normalize_code
from data.providers import _pit_select_snapshot_dated


class PitFinancialsService:
    """[资产 × as_of] → PIT 财报截面快照。构建时一次性载入全宇宙披露历史。"""

    def __init__(self, provider, assets, fields):
        self.provider = provider
        self.fields = list(fields)
        # AkShare 的字段映射（baostock 这三字段在 _PIT_FIELD_UNAVAILABLE，必须 AkShare）
        self.field_map = getattr(provider, "_PIT_FIELD_MAP", {})
        # 预载每只股票的披露历史（provider 内部按 .parquet 缓存：首次联网、之后磁盘读）
        self._hist: dict[str, pd.DataFrame] = {}
        for a in [normalize_code(a) for a in assets]:
            self._ensure_history(a)

    def _ensure_history(self, a: str) -> None:
        """懒加载单只股票的披露历史；缺失才联网/读盘，失败置空表不拖垮整轮。"""
        a = normalize_code(a)
        if a in self._hist:
            return
        try:
            self._hist[a] = self.provider._fetch_financial_history(a)
        except Exception as e:  # 单票拉取失败不应拖垮整轮
            print(f"[warn] PIT 历史拉取失败 {a}: {e}", flush=True)
            self._hist[a] = pd.DataFrame()

    def snapshot(self, assets, as_of, with_dates: bool = False):
        """返回 as_of 截面快照。

        Args:
            assets: 资产列表（规范代码）。
            as_of: 截面日期。
            with_dates: True 时返回 {asset: {field: (value, statDate)}}，
                供财报类因子把流量项（cogs/revenue）按报告期年度化。
        Returns:
            若 with_dates=False：DataFrame，index=asset，columns=fields。
            若 with_dates=True：dict，asset -> {field: (value, statDate)}。
        """
        as_of = pd.Timestamp(as_of)
        assets = [normalize_code(a) for a in assets]
        rows = []
        for a in assets:
            # 🔴 懒加载兜底：build 首切可能漏掉晚上市/晚纳入指数的资产，
            # 这里遇到缺失历史就即时补拉，避免"首建库后永不扩展"的漏数 bug。
            self._ensure_history(a)
            disc = self._hist.get(a, pd.DataFrame())
            vals = _pit_select_snapshot_dated(disc, self.fields, as_of, self.field_map)
            rows.append({"asset": a, **vals})
        if with_dates:
            out = {}
            for r in rows:
                a = r.pop("asset")
                out[a] = {f: r[f] for f in self.fields}
            return out
        if not rows:
            return pd.DataFrame(columns=["asset"] + self.fields).set_index("asset")
        df = pd.DataFrame(rows).set_index("asset")
        return df[[c for c in self.fields if c in df.columns]]


# 模块级单例：因子在 ctx 缺失时兜底自建（测试 / 独立调用路径）。
_DEFAULT_STORE: "PitFinancialsService | None" = None


def default_store(assets=None, fields=None):
    """返回进程内共享的 PitFinancialsService（懒加载 AkShareProvider）。

    因子 compute 若未从 ctx 拿到注入的 pit_service，走此兜底。第一调用构建并缓存，
    后续复用（披露历史是静态的，不随 as_of 变化，安全）。
    """
    global _DEFAULT_STORE
    if _DEFAULT_STORE is None:
        from data.providers import AkShareProvider
        ak = AkShareProvider()
        _DEFAULT_STORE = PitFinancialsService(
            ak, assets or [], fields or ["cogs", "inventory", "accounts_receivable", "revenue"]
        )
    return _DEFAULT_STORE
