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

数据源：**多后端互补**（Phase A 2026-10-10 起）。
  - AkShare 东财明细表：cogs / inventory / accounts_receivable / **rd_expense**
    （baostock 免费接口无这些行项目，见其 `_PIT_FIELD_UNAVAILABLE`）。
  - BaoStock `query_balance_data`：**currentRatio / quickRatio / cashRatio** 等偿债能力
    与杠杆比率（东财 by_report 的 CURRENT_ASSET_BALANCE / CURRENT_LIAB_BALANCE 实测
    恒 0 / -1000 哨兵 / NaN，**不可用**，故不自算比率而取 baostock 现成口径）。
  两者披露流纵向拼接后由 `_pit_select_snapshot_dated` 做字段独立取数（互补不覆盖）。
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from data.contract import normalize_code
from data.providers import _pit_select_snapshot_dated


class PitFinancialsService:
    """[资产 × as_of] → PIT 财报截面快照。构建时一次性载入全宇宙披露历史。"""

    def __init__(self, provider, assets, fields):
        # Phase A（2026-10-10）：支持**多后端**。不同 provider 能提供的财报字段互补：
        #   AkShare 东财明细表 → cogs / inventory / accounts_receivable / rd_expense
        #   BaoStock           → currentRatio / quickRatio 等偿债能力比率
        # （背景与实测见 docs/dev/PLAN_PHASE_A_DATA.md §0.2 / §0.3）
        self.providers = list(provider) if isinstance(provider, (list, tuple)) else [provider]
        self.provider = self.providers[0]      # 向后兼容：旧代码按单 provider 取用
        self.fields = list(fields)
        # 字段映射取各后端并集；同名以**先加入者**为准（AkShare 优先，保持历史口径稳定）
        self.field_map: dict = {}
        for p in self.providers:
            for k, v in (getattr(p, "_PIT_FIELD_MAP", {}) or {}).items():
                self.field_map.setdefault(k, v)
        # 预载每只股票的披露历史（provider 内部按 .parquet 缓存：首次联网、之后磁盘读）
        self._hist: dict[str, pd.DataFrame] = {}
        for a in [normalize_code(a) for a in assets]:
            self._ensure_history(a)

    def _ensure_history(self, a: str) -> None:
        """懒加载单只股票的披露历史（多后端纵向拼接）；失败置空表不拖垮整轮。"""
        a = normalize_code(a)
        if a in self._hist:
            return
        frames = []
        for p in self.providers:
            try:
                h = p._fetch_financial_history(a)
                if h is not None and len(h):
                    frames.append(h)
            except Exception as e:  # 单后端/单票拉取失败不应拖垮整轮
                print(f"[warn] PIT 历史拉取失败 {a} @{type(p).__name__}: {e}", flush=True)
        if not frames:
            self._hist[a] = pd.DataFrame()
            return
        # 🔴 PIT 安全：各后端的历史帧记录的是各自披露流的 (statDate, pubDate)，
        # 纵向拼接只是把**不同披露流的行**放进同一张表（互补不覆盖）。
        # 真正的前视过滤发生在 _pit_select_snapshot_dated（pubDate <= as_of +
        # 字段独立取最新），这里不做任何时间过滤 → 拼接不会引入"未来行"。
        merged = frames[0] if len(frames) == 1 else pd.concat(frames, ignore_index=True)
        self._hist[a] = merged.reset_index(drop=True)

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


    def disclosure_dates(self, asset) -> pd.DatetimeIndex:
        """该票全部财报公告日（升序去重）—— 供财报因子快路径做**事件驱动**取数。

        为什么需要：财报因子值在两个披露日之间恒定（PIT 快照 = 截至 as_of 最新已披露），
        所以只需在每个公告日算一次、再阶梯 ffill 到交易日轴，复杂度 O(披露次数)
        （每票几十次）而非 O(交易日 × 资产)（hs300×1500 日 = 45 万次）。
        逐日调用 snapshot 走后者，单因子出包实测 >1 小时；事件驱动可降到分钟级。
        """
        a = normalize_code(asset)
        self._ensure_history(a)
        disc = self._hist.get(a)
        if disc is None or len(disc) == 0 or "pubDate" not in getattr(disc, "columns", []):
            return pd.DatetimeIndex([])
        pubs = pd.to_datetime(disc["pubDate"], errors="coerce").dropna().unique()
        return pd.DatetimeIndex(sorted(pubs))


    def disclosure_events(self, asset, field: str = "net_profit_parent") -> pd.DataFrame:
        """该票某字段的**全部披露事件**时间序列（按 pubDate 升序）。

        与 snapshot() 的区别：snapshot 只给 as_of 时点的最新一期，而 SUE 这类
        需要**跨期历史**（同比、波动率）的因子必须拿到整个报告期序列。

        Returns:
            DataFrame[pubDate, statDate, value]，value 为报表**原始累计口径**
            （如净利为年初至今累计），未做任何年度化/单季拆分。

        🔴 PIT 语义：同一报告期可能被多次披露（业绩更正/重述），这里**保留全部事件**，
        消费方按 pubDate 升序遍历、后者覆盖前者，即得到"当时可见的最新版"——
        绝不能先按 statDate 去重取最大 pubDate，否则等于用未来的更正版本算历史。
        """
        a = normalize_code(asset)
        self._ensure_history(a)
        disc = self._hist.get(a)
        col = (self.field_map or {}).get(field)
        if disc is None or len(disc) == 0 or not col or col not in disc.columns:
            return pd.DataFrame(columns=["pubDate", "statDate", "value"])
        d = disc[["pubDate", "statDate", col]].copy()
        d["pubDate"] = pd.to_datetime(d["pubDate"], errors="coerce")
        d["statDate"] = pd.to_datetime(d["statDate"], errors="coerce")
        d = d.rename(columns={col: "value"})
        d["value"] = pd.to_numeric(d["value"], errors="coerce")
        d = d.dropna(subset=["pubDate", "statDate"]).dropna(subset=["value"])
        d = d.sort_values(["pubDate", "statDate"])
        return d.reset_index(drop=True)


# 模块级单例：因子在 ctx 缺失时兜底自建（测试 / 独立调用路径）。
_DEFAULT_STORE: "PitFinancialsService | None" = None

# Phase 0 财报扩面（2026-09-08）：共享服务默认加载全集字段，
# 任何因子（含新增财报因子）都能从单例取到所需字段，不必各自重建。
_DEFAULT_PIT_FIELDS = [
    "revenue", "cogs", "inventory", "accounts_receivable",
    "operate_profit", "total_profit", "net_profit", "net_profit_parent",
    "deduct_net_profit", "eps", "operate_income_yoy", "net_profit_parent_yoy",
    "total_assets", "total_equity", "parent_equity", "ocf",
    # --- Phase A 数据源扩展（2026-10-10）---
    "rd_expense",                       # AkShare 东财：研发支出（金融股天然 NaN）
    "current_ratio", "quick_ratio", "cash_ratio",      # BaoStock：偿债能力
    "liability_to_asset", "asset_to_equity", "liability_yoy",   # BaoStock：杠杆
]


def default_store(assets=None, fields=None):
    """返回进程内共享的 PitFinancialsService（**多后端**：AkShare + BaoStock）。

    因子 compute 若未从 ctx 拿到注入的 pit_service，走此兜底。第一调用构建并缓存，
    后续复用（披露历史是静态的，不随 as_of 变化，安全）。

    🔴 始终用 ``_DEFAULT_PIT_FIELDS`` 全集构建单例（忽略传入的 ``fields`` 参数）：
    避免首个调用方若只带少量字段（如 f0014a 的 [inventory,cogs]）就把单例钉死，
    导致后续新增财报因子取不到扩展字段 → 静默 NaN。
    """
    global _DEFAULT_STORE
    if _DEFAULT_STORE is None:
        from data.providers import AkShareProvider, BaoStockProvider
        providers = [AkShareProvider()]
        try:
            providers.append(BaoStockProvider())
        except Exception as e:      # baostock 不可用不应拖垮财报服务整体
            print(f"[warn] baostock 后端不可用，财报仅走东财: {e}", flush=True)
        _DEFAULT_STORE = PitFinancialsService(providers, assets or [], _DEFAULT_PIT_FIELDS)
    return _DEFAULT_STORE
