"""数据源适配器：LocalProvider(测试) / TushareProvider(主) / AkShareProvider(fallback)。

均实现 data.interface.DataProvider 契约（见 ADR-0001 / RESEARCH_LOG R2026-0804-01,03,04）。

- LocalProvider：生成确定性合成面板（几何随机游走 + 随机成交量），供 CI / 冒烟测试，无需联网、无第三方依赖。
- TushareProvider / AkShareProvider：真实源适配器（已实现）；运行需 `pip install tushare|akshare` + 配置 token / 网络。
  设计要点：懒导入第三方库（无依赖环境不报错）、本地缓存（.cache/ 避免重复调用、应对限流）、
  字段单位统一（vol 手->股、amount 千元->元、total_mv 万元->元，避免 v61b 式单位坑）。
  真实 point-in-time 财报过滤 / 严格复权细节见 docs/RESEARCH_LOG（Phase 4 改进）。
"""
from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from data.contract import canonicalize_panel, normalize_code, validate_panel, validate_returns

_FIELDS = ["open", "high", "low", "close", "volume", "amount", "turnover", "market_cap"]

# 市值快照共享缓存：BaoStock / AkShare 两个 provider 共用同一份 AkShare 东财 spot 快照，
# 避免同一数据写两份、口径漂移（见 RESEARCH_LOG R2026-0805-06）。
_SHARED_MARKET_CAP_CACHE = Path(".cache/akshare/market_cap.csv")

# 固定股票池（模拟 point-in-time 成分股；真实源应返回当日实际成分股）
_UNIVERSE = [f"000{str(i).zfill(3)}.SZ" for i in range(1, 51)]

# 指数成分股子集映射（供 FF_UNIVERSE=hs300 等使用，走 index_weight 接口）
# 注：index_weight 通常需要 500 积分；若积分不足请改用交易所子集（FF_UNIVERSE=SZ）。
_INDEX_MAP = {
    "hs300": "000300.SH",   # 沪深300
    "csi500": "000905.SH",  # 中证500
    "zz500": "000905.SH",   # 中证500（别名）
    "sz50": "000016.SH",    # 上证50
    "cyb": "399006.SZ",     # 创业板指
    "zxb": "399005.SZ",     # 中小板指
}
# 交易所子集（走 stock_basic exchange 参数，基础积分即可）
_EXCHANGE_SET = {"SH", "SZ", "BJ"}
# list_status 合法值
_LIST_STATUS_SET = {"L", "D", "P"}


class LocalProvider:
    """确定性合成数据源，供测试。生成几何随机游走价格 + 随机成交量。

    设计：所有随机性由 seed 固定，保证测试可重复；价格序列含 open/high/low/close，
    使隔夜-日内因子可测；vol/amount/turnover/market_cap 齐备，使二次冲击成本模型可测。
    """

    adj_policy = "raw"  # 合成数据无分红/拆分，raw 即等价 qfq；仅供测试，不参与主流程防火墙

    def __init__(self, seed: int = 42, n_assets: int = 20,
                 start: str = "2022-01-01", end: str = "2024-12-31"):
        self._seed = seed
        self._universe = _UNIVERSE[:n_assets]
        self._dates = pd.bdate_range(start, end)  # 工作日近似交易日
        self._panel = self._build_panel()

    def _build_panel(self) -> pd.DataFrame:
        rng = np.random.default_rng(self._seed)
        n = len(self._dates)
        assets = self._universe
        records = []
        for a in assets:
            rets = rng.normal(0.0005, 0.02, n)            # 日收益率：微正漂移 + 噪声
            close = 10.0 * np.cumprod(1.0 + rets)
            prev_close = np.concatenate([[10.0], close[:-1]])
            open_ = prev_close * (1.0 + rng.normal(0.0, 0.005, n))
            high = np.maximum(open_, close) * (1.0 + np.abs(rng.normal(0.0, 0.004, n)))
            low = np.minimum(open_, close) * (1.0 - np.abs(rng.normal(0.0, 0.004, n)))
            volume = rng.integers(int(1e5), int(1e6), n).astype(float)
            amount = volume * close
            turnover = rng.uniform(0.5, 5.0, n)           # 百分比
            market_cap = rng.uniform(20.0, 500.0, n) * 1e8
            for i, d in enumerate(self._dates):
                records.append((d, a, open_[i], high[i], low[i], close[i],
                                volume[i], amount[i], turnover[i], market_cap[i]))
        df = pd.DataFrame(records, columns=["date", "asset"] + _FIELDS)
        return df.set_index(["date", "asset"]).sort_index()

    def get_panel(self, fields: list[str], start, end) -> pd.DataFrame:
        dlevel = self._panel.index.get_level_values("date")
        lo = pd.Timestamp(start) if start is not None else dlevel.min()
        hi = pd.Timestamp(end) if end is not None else dlevel.max()
        sub = self._panel.loc[(dlevel >= lo) & (dlevel <= hi)]
        sub = sub[[c for c in fields if c in sub.columns]]
        sub = canonicalize_panel(sub)   # 契约：统一索引名/代码后缀
        validate_panel(sub, "Local", fields)  # 契约：单位/格式校验
        return sub

    def get_pit_financials(self, fields: list[str], as_of_date) -> pd.DataFrame:
        # 合成：返回空（Phase 2 因子暂未用财报；真实源须按公告日 <= as_of_date 过滤）
        return pd.DataFrame(columns=["date", "asset"] + list(fields)).set_index(["date", "asset"])

    def list_universe(self, date: str) -> list[str]:
        # point-in-time：返回 date 当日池（此处恒定；真实源须按公告日过滤，剔除退市/未上市）
        d = pd.Timestamp(date)
        if d < self._dates[0] or d > self._dates[-1]:
            return []
        return list(self._universe)

    def get_adv(self, date: str, window: int = 20) -> pd.Series:
        d = pd.Timestamp(date)
        dlevel = self._panel.index.get_level_values("date")
        valid = sorted(set(dlevel[dlevel <= d]))
        if not valid:
            return pd.Series(dtype=float)
        recent = valid[-window:]
        sub = self._panel.loc[dlevel.isin(recent)]
        return sub.groupby(level="asset")["volume"].mean()


class TushareProvider:
    """主数据源适配器（真实实现）。需 `pip install tushare` + 环境变量 TUSHARE_TOKEN。

    设计：
    - 懒导入 tushare；无依赖/无 token 时不破坏其他测试（LocalProvider 路径不受影响）。
    - 本地缓存（.cache/tushare/*.parquet）：首次拉取慢、依赖积分/限流，缓存避免重复调用。
    - get_panel：拉日线(OHLCV+amount) + daily_basic(turnover,total_mv) 合并；单位统一见下方注释。
    - **复权口径（免费 token 约束）**：adj_factor 免费档限频 1次/小时，pro_bar(adj=qfq)
      无法全市场拉取，故当前 ADJ_POLICY=不复权(raw)；升级积分后可改回 qfq（改 pro_bar 加
      adj='qfq' 即可）。raw 价在除权除息日会产生收益率毛刺，预处理层 MAD 剪枝可缓解。
    - **daily_basic 熔断**：免费档限频 1次/分钟，首次超限整轮跳过（turnover/market_cap=NaN）。
    - get_index_returns：拉指数日线（默认沪深300）作为市场收益基准，供 IVOL 残差回归使用。
    - 真实 point-in-time 财报过滤见 docs/RESEARCH_LOG（Phase 4 改进）。
    - 注意：list_universe 当前返回 stock_basic 上市列表（近似全A），非严格 PIT——会引入轻微幸存者偏差，
      接真实数据后请优先用指数成分股或历史成分股接口（TODO）。
    """

    adj_policy = "raw"  # 免费 token 无法拉 qfq（adj_factor 限频），实际返回不复权价；
                      # 与契约 ADJ_POLICY=qfq 不一致，主流程须经 assert_adj_policy 显式放行

    def __init__(self, token: Optional[str] = None, cache_dir: str = ".cache/tushare",
                 universe: str = "L", index_code: str = "000300.SH",
                 calls_per_min: int = 50, retry: int = 3,
                 history_start: Optional[str] = None):
        """history_start：分析窗口起点（如 '2020-01-01'），构建内存缓存时丢弃更早数据，
        显著降低内存与计算量；None=全历史。仅影响取数窗口，不影响 parquet 磁盘缓存完整性。"""
        self._token = token or os.getenv("TUSHARE_TOKEN")
        if not self._token:
            raise RuntimeError(
                "TushareProvider 需要 TUSHARE_TOKEN（环境变量或参数）。"
                "请按 docs/SOP_TUSHARE_TOKEN.md 申请并配置 token。"
            )
        import tushare as ts  # 懒导入：无依赖环境不报错
        ts.set_token(self._token)
        self._ts = ts          # pro_bar 是模块级函数，非 pro_api 客户端方法
        self._pro = ts.pro_api()
        self._cache = Path(cache_dir)
        self._cache.mkdir(parents=True, exist_ok=True)
        self._universe_mode = universe
        self._index_code = index_code
        self._index_code_for_universe = _INDEX_MAP.get(universe)  # 指数子集代码；非指数为 None
        self._calls_per_min = calls_per_min
        self._retry = retry
        self._last_call = 0.0
        self._history_start = pd.Timestamp(history_start) if history_start else None
        # daily_basic 熔断闩：免费 token 限频 1次/分钟，首次超限后整轮跳过（避免逐股重试白等）
        self._daily_basic_broken = False
        # 全历史面板内存缓存：validator/engine 按日期反复调 get_panel，
        # 若每次重读 parquet（300 文件/次 × 数千日期）会卡死；首次构建后切片复用。
        self._panel_cache: Optional[pd.DataFrame] = None

    # ---- 限流 / 重试 ----
    def _throttle(self):
        gap = 60.0 / max(1, self._calls_per_min)
        now = time.time()
        wait = gap - (now - self._last_call)
        if wait > 0:
            time.sleep(wait)
        self._last_call = time.time()

    def _call(self, fn, **kwargs):
        last_err = None
        for i in range(self._retry):
            try:
                self._throttle()
                return fn(**kwargs)
            except Exception as e:  # 限流 / 积分不足 / 网络抖动
                last_err = e
                msg = str(e)
                # pro_bar 把底层限频消息吞成 OSError('ERROR.')，这里连 ERROR 一起兜住
                if any(k in msg for k in ("每分钟", "频率", "权限", "积分", "超时", "timeout", "ERROR")):
                    time.sleep(2 ** i * 5)
                    continue
                raise
        raise RuntimeError(f"Tushare 调用重试 {self._retry} 次仍失败: {last_err}")

    # ---- 股票池 ----
    def _asset_list(self) -> list[str]:
        # 不同模式用各自的缓存文件名，避免全A/指数/交易所缓存互相污染
        if self._index_code_for_universe:
            key = self._cache / f"asset_list_idx_{self._universe_mode}.csv"
        else:
            key = self._cache / f"asset_list_{self._universe_mode}.csv"
        if key.exists():
            codes = pd.read_csv(key, dtype=str)["ts_code"].tolist()
            if codes:
                return codes
            # 空壳缓存（stock_basic 限频时可能写出空表）→ 视为无效重新拉取
            print(f"[warn] {key.name} 为空壳缓存，重新拉取股票池", flush=True)
        if self._index_code_for_universe:
            codes = self._asset_list_index(self._index_code_for_universe)
        elif self._universe_mode in _EXCHANGE_SET:
            df = self._call(self._pro.stock_basic, exchange=self._universe_mode,
                            list_status="L", fields="ts_code,symbol,name,list_date")
            codes = df["ts_code"].tolist()
        else:
            # 默认按 list_status（L/D/P）；非法值回退到 L
            ls = self._universe_mode if self._universe_mode in _LIST_STATUS_SET else "L"
            df = self._call(self._pro.stock_basic, exchange="", list_status=ls,
                            fields="ts_code,symbol,name,list_date")
            codes = df["ts_code"].tolist()
        if not codes:
            raise RuntimeError(
                f"股票池为空 (universe={self._universe_mode})：token 积分/接口权限不足。"
                "可用 AkShare 生成股票池 CSV 落缓存（scripts/make_universe.py），或升级 Tushare 积分。"
            )
        pd.DataFrame({"ts_code": codes}).to_csv(key, index=False)
        return codes

    def _asset_list_index(self, index_code: str) -> list[str]:
        """取指数最新快照的成分股（con_code 列表）。走 index_weight 接口。"""
        df = self._call(self._pro.index_weight, ts_code=index_code,
                        start_date="20000101", end_date="20991231",
                        fields="trade_date,con_code,weight")
        if df is None or df.empty:
            return []
        df["trade_date"] = pd.to_datetime(df["trade_date"])
        latest = df["trade_date"].max()
        recent = df[df["trade_date"] == latest]
        return recent["con_code"].astype(str).tolist()

    # ---- 单只历史拉取并缓存 ----
    def _fetch_one(self, code: str) -> Optional[pd.DataFrame]:
        # 拉全历史范围并缓存，get_panel 再按 start/end 切片（保证缓存一致：
        # 引擎每次传不同 start/end，若不拉全量则缓存数据不全或重复拉取）
        start_s, end_s = "20000101", "20991231"
        # 免费 token 的 adj_factor 限频 1次/小时，pro_bar(adj=qfq) 无法全市场拉取；
        # 故此处用不复权价（adj 缺省），复权口径见类注释 ADJ_POLICY；升级积分后可改回 qfq。
        bar = self._call(self._ts.pro_bar, ts_code=code, start_date=start_s,
                         end_date=end_s, asset="E", freq="D")
        if bar is None or bar.empty:
            return None
        bar["trade_date"] = pd.to_datetime(bar["trade_date"])
        bar = bar.rename(columns={"vol": "volume_raw", "ts_code": "asset"})
        # daily_basic 免费 token 限频 1次/分钟：首次超限即熔断（turnover/market_cap 留 NaN，
        # 符合契约"缺失用 NaN"）；积分升级后可恢复全字段。
        if not self._daily_basic_broken:
            try:
                basic = self._call(self._pro.daily_basic, ts_code=code, start_date=start_s,
                                   end_date=end_s, fields="trade_date,turnover,total_mv")
                if basic is not None and not basic.empty:
                    basic["trade_date"] = pd.to_datetime(basic["trade_date"])
                    df = bar.merge(basic, on="trade_date", how="left")
                else:
                    df = bar.copy()
            except RuntimeError as e:
                if "频率" in str(e) or "频次" in str(e):
                    self._daily_basic_broken = True
                    print(f"[warn] daily_basic 限频熔断（整轮跳过，turnover/market_cap=NaN）: {e}", flush=True)
                else:
                    print(f"[warn] {code} daily_basic 获取失败（降级）: {e}", flush=True)
                df = bar.copy()
        else:
            df = bar.copy()
        # 降级路径补列：daily_basic 缺失时 turnover/total_mv 为 NaN（契约：缺失用 NaN，非 0）
        for col in ("turnover", "total_mv"):
            if col not in df.columns:
                df[col] = np.nan
        # 单位统一（重要：避免 v61b 式单位坑）
        df["volume"] = df["volume_raw"].astype(float) * 100.0      # tushare vol 单位=手 -> 股
        df["amount"] = df["amount"].astype(float) * 1000.0         # tushare amount 单位=千元 -> 元
        df["turnover"] = df["turnover"].astype(float)              # 百分比，原样（缺失=NaN）
        df["market_cap"] = df["total_mv"].astype(float) * 1e4      # total_mv 万元 -> 元（缺失=NaN）
        cols = ["trade_date", "asset", "open", "high", "low", "close",
                "volume", "amount", "turnover", "market_cap"]
        df = df[[c for c in cols if c in df.columns]]
        df = df.rename(columns={"trade_date": "date"})  # 契约：索引层0 名为 date
        return df.set_index(["date", "asset"])

    # ---- DataProvider 接口 ----
    def _load_full_panel(self) -> pd.DataFrame:
        """构建/复用全历史面板内存缓存（首次拉全量落 parquet，之后切片复用）。"""
        if self._panel_cache is not None:
            return self._panel_cache
        assets = self._asset_list()
        parts = []
        for code in assets:
            cache = self._cache / f"{code}.parquet"
            if cache.exists():
                df = pd.read_parquet(cache)
            else:
                df = self._fetch_one(code)
                if df is not None:
                    df.to_parquet(cache)
            if df is not None:
                parts.append(df)
        if not parts:
            panel = pd.DataFrame(columns=["date", "asset"] + _FIELDS).set_index(["date", "asset"])
        else:
            panel = pd.concat(parts).sort_index()
        if self._history_start is not None:
            panel = panel[panel.index.get_level_values("date") >= self._history_start]
        self._panel_cache = panel
        return panel

    def get_panel(self, fields: list[str], start, end) -> pd.DataFrame:
        panel = self._load_full_panel()
        dlevel = panel.index.get_level_values("date")
        lo = pd.Timestamp(start) if start is not None else dlevel.min()
        hi = pd.Timestamp(end) if end is not None else dlevel.max()
        sub = panel.loc[(dlevel >= lo) & (dlevel <= hi)]
        sub = sub[[c for c in fields if c in sub.columns]]
        sub = canonicalize_panel(sub)          # 契约：统一索引名/代码后缀
        validate_panel(sub, "Tushare", fields)  # 契约：单位/格式校验，违反即抛错
        return sub

    def get_index_returns(self, index_code: Optional[str] = None,
                          start=None, end=None) -> pd.Series:
        """指数日收益率序列（pct_chg/100），作为市场收益基准。"""
        code = index_code or self._index_code
        key = self._cache / f"idx_{code}.parquet"
        if key.exists():
            df = pd.read_parquet(key)
        else:
            df = self._call(self._pro.index_daily, ts_code=code,
                            start_date="20000101", end_date="20991231")
            if df is None or df.empty:
                return pd.Series(dtype=float)
            df["trade_date"] = pd.to_datetime(df["trade_date"])
            df = df[["trade_date", "pct_chg"]].set_index("trade_date")
            df.to_parquet(key)
        lo = pd.Timestamp(start) if start else df.index.min()
        hi = pd.Timestamp(end) if end else df.index.max()
        s = df.loc[(df.index >= lo) & (df.index <= hi), "pct_chg"] / 100.0
        s = s.astype(float)
        validate_returns(s, "Tushare")
        return s

    def get_pit_financials(self, fields: list[str], as_of_date) -> pd.DataFrame:
        # TODO Phase 4：按公告日 <= as_of_date 过滤；当前返回空（Phase 2/3 因子暂未用财报）
        return pd.DataFrame(columns=["date", "asset"] + list(fields)).set_index(["date", "asset"])

    def list_universe(self, date: str) -> list[str]:
        # 近似非 PIT：返回当前上市列表（含轻微幸存者偏差，见类注释）
        d = pd.Timestamp(date)
        try:
            return self._asset_list()
        except Exception:
            return []

    def get_adv(self, date: str, window: int = 20) -> pd.Series:
        # 真实 ADV 由二次冲击成本在回测时基于面板 volume 计算；此处返回空 Series 占位。
        # TODO Phase 4：从缓存面板拼截至 date 的 window 日均值。
        return pd.Series(dtype=float)


class AkShareProvider:
    """fallback 数据源适配器（已实现）。需 `pip install akshare`。

    设计：懒导入 akshare；单位统一（ak 的 volume 单位=股、amount 单位=元，与内部 schema 一致）。
    未做缓存（akshare 多为公开接口、限流宽松）；如接入高频场景建议补缓存。
    """

    adj_policy = "qfq"  # adjust="qfq"（东财/新浪源均前复权），符合契约 ADJ_POLICY

    def __init__(self, cache_dir: str = ".cache/akshare"):
        import akshare as ak  # 懒导入：无依赖环境不报错
        self._ak = ak
        self._cache = Path(cache_dir)
        self._cache.mkdir(parents=True, exist_ok=True)
        self._index_code = "000300"  # akshare 指数代码不带后缀
        self._panel_cache = None  # 全历史内存缓存（validator 反复 get_panel 时避免重复网络拉取）

    def _asset_list(self) -> list[str]:
        # akshare 股票列表（含退市，list_status 可选 L/D）
        df = self._ak.stock_info_a_code_name()  # 返回 code/name
        return [normalize_code(c) for c in df["code"]]  # 契约：代码补交易所后缀

    def _market_cap_map(self) -> dict:
        """总市值（元）快照：akshare 的 stock_zh_a_spot_em 返回实时总市值，缓存放共享 _SHARED_MARKET_CAP_CACHE。

        注：为点估值近似（取快照日市值）；东财 spot 端点不可达时降级返回 {}（market_cap=NaN，
        契约允许缺失用 NaN）。契约要求缺失用 NaN 而非 0。与 BaoStockProvider._share_map 共用同一文件，
        避免同一份市值快照写两份、口径漂移。
        """
        key = _SHARED_MARKET_CAP_CACHE
        key.parent.mkdir(parents=True, exist_ok=True)
        if key.exists():
            df = pd.read_csv(key, dtype={"code": str})
            if len(df):
                return dict(zip(df["code"], df["mcap"]))
        try:
            spot = self._ak.stock_zh_a_spot_em()
            spot = spot.rename(columns={"代码": "code", "总市值": "mcap"})
            spot["code"] = spot["code"].map(normalize_code)
            spot[["code", "mcap"]].to_csv(key, index=False)
            return dict(zip(spot["code"], spot["mcap"]))
        except Exception as e:
            print(f"[warn] 总市值快照获取失败（market_cap=NaN 降级）: {e}", flush=True)
            return {}

    def _hist_df(self, code: str, start_s: str, end_s: str):
        """拉单票日线，返回 (df, volume_is_lots)。

        主源 stock_zh_a_hist（东财）：volume=手、amount=元、含换手率；
        东财端点在某些网络被断连时降级 stock_zh_a_daily（新浪）：volume=**股**、amount=元、无换手率。
        返回 volume_is_lots 由调用方决定是否 ×100（契约：最终一律为股）。
        """
        num = code.split(".")[0]
        try:
            df = self._ak.stock_zh_a_hist(symbol=num, period="daily",
                                          start_date=start_s, end_date=end_s, adjust="qfq")
            df = df.rename(columns={"日期": "trade_date", "开盘": "open", "最高": "high",
                                    "最低": "low", "收盘": "close", "成交量": "volume",
                                    "成交额": "amount", "换手率": "turnover"})
            return df, True
        except Exception:
            # 新浪源：symbol 带交易所前缀小写（sz000001），volume 单位=股，无换手率
            prefix = {"SH": "sh", "SZ": "sz", "BJ": "bj"}[code.split(".")[1]]
            df = self._ak.stock_zh_a_daily(symbol=f"{prefix}{num}",
                                           start_date=start_s, end_date=end_s, adjust="qfq")
            df = df.rename(columns={"date": "trade_date", "open": "open", "high": "high",
                                    "low": "low", "close": "close", "volume": "volume",
                                    "amount": "amount"})
            df["turnover"] = np.nan
            return df, False

    def get_panel(self, fields: list[str], start, end) -> pd.DataFrame:
        if self._panel_cache is None:
            assets = self._asset_list()
            start_s = pd.Timestamp(start).strftime("%Y%m%d")
            end_s = pd.Timestamp(end).strftime("%Y%m%d")
            parts = []
            for code in assets:
                try:
                    df, volume_is_lots = self._hist_df(code, start_s, end_s)
                except Exception:
                    continue
                if df is None or df.empty:
                    continue
                df["trade_date"] = pd.to_datetime(df["trade_date"])
                df["asset"] = normalize_code(code)          # 契约：代码补交易所后缀
                # 东财源成交量=手，契约为股 -> *100；新浪源已是股（不乘）
                if volume_is_lots:
                    df["volume"] = df["volume"].astype(float) * 100.0
                # 总市值取 spot 快照（元）；无匹配留 NaN（缺失须 NaN，非 0）
                df["market_cap"] = df["asset"].map(self._market_cap_map())
                df = df[[c for c in ["trade_date", "asset", "open", "high", "low", "close",
                                     "volume", "amount", "turnover", "market_cap"] if c in df.columns]]
                parts.append(df.rename(columns={"trade_date": "date"}).set_index(["date", "asset"]))
            if not parts:
                self._panel_cache = pd.DataFrame(columns=["date", "asset"] + _FIELDS).set_index(["date", "asset"])
            else:
                self._panel_cache = pd.concat(parts).sort_index()
        panel = self._panel_cache
        dlevel = panel.index.get_level_values("date")
        lo, hi = pd.Timestamp(start), pd.Timestamp(end)
        sub = panel.loc[(dlevel >= lo) & (dlevel <= hi)]
        sub = sub[[c for c in fields if c in sub.columns]]
        sub = canonicalize_panel(sub)          # 契约：统一索引名/代码后缀
        validate_panel(sub, "AkShare", fields)  # 契约：单位/格式校验，违反即抛错
        return sub

    def get_index_returns(self, index_code: Optional[str] = None,
                          start=None, end=None) -> pd.Series:
        code = index_code or self._index_code
        df = self._ak.index_zh_a_hist(symbol=code, period="daily",
                                      start_date=pd.Timestamp(start).strftime("%Y%m%d") if start else "20000101",
                                      end_date=pd.Timestamp(end).strftime("%Y%m%d") if end else "20991231")
        if df is None or df.empty:
            return pd.Series(dtype=float)
        df = df.rename(columns={"日期": "trade_date", "涨跌幅": "pct_chg"})
        df["trade_date"] = pd.to_datetime(df["trade_date"])
        df = df.set_index("trade_date")
        s = (df["pct_chg"] / 100.0).astype(float)
        validate_returns(s, "AkShare")
        return s

    def get_pit_financials(self, fields: list[str], as_of_date) -> pd.DataFrame:
        return pd.DataFrame(columns=["date", "asset"] + list(fields)).set_index(["date", "asset"])

    def list_universe(self, date: str) -> list[str]:
        try:
            return self._asset_list()
        except Exception:
            return []

    def get_adv(self, date: str, window: int = 20) -> pd.Series:
        return pd.Series(dtype=float)


class BaoStockProvider:
    """baostock 免费数据源适配器（免 token / 免积分）。

    来源：取数逻辑移植自用户旧工程 a-share-quant-sim/core/providers/baostock.py
    （Apache-2.0，用户自有代码），并按 factor-factory 数据契约重写：
    - volume=**股**（baostock 原生即股，契约死线，不做手→股换算）
    - adjustflag="2" **前复权**（对齐 ADJ_POLICY=qfq；旧工程原为不复权）
    - 代码规范 `600000.SH` ↔ `sh.600000`（复用 contract.normalize_code）
    - parquet 磁盘缓存（.cache/baostock/，与 Tushare 同款 _fetch_one 全历史+切片模式）
    - market_cap = query_stock_basic 总股本（万股，当前快照）× close（点估值近似，同 AkShare 口径）
    - 独有字段 tradestatus(0停牌/1正常) / is_st(0正常/1ST) 原样透出（其他源缺省 NaN）

    已知限制（见 docs/PLAN_BAOSTOCK_PROVIDER.md）：
    - 当日数据收盘后才更新 → 适合历史回测，不适合盘中当日信号
    - 免费服务偶发不稳 → health_check + 重试 + 缓存兜底
    - Windows 进程退出偶发崩溃(0xC0000409)：不显式 logout，进程自然退出即断开
    - universe 支持指数池（hs300/csi500/zz500/sz50）、合并池 **hs800**（hs300∪zz500）、
      **hs1800**（hs800∪zz1000≈中证1800）、**zz1000**（baostock 无接口，经 AkShare 取成分股）、
      全 A（ALL + min_mcap 市值过滤）；无交易所子集接口
    """

    # 指数池代码 → baostock 原生接口
    _INDEX_METHODS = {
        "hs300": "query_hs300_stocks",
        "csi500": "query_zz500_stocks",
        "zz500": "query_zz500_stocks",
        "sz50": "query_sz50_stocks",
    }
    # 合并池：hs300 ∪ zz500 = 中证800 精确近似（实测合并去重 800 只）；
    # hs1800 = hs800 ∪ zz1000 ≈ 中证1800（覆盖大/中/小中盘，无需全 A）
    _MERGE_POOLS = {"hs800": ("hs300", "zz500"), "hs1800": ("hs800", "zz1000")}
    # 规范指数代码 → baostock 指数 K 线代码
    _INDEX_KLINE = {
        "000300.SH": "sh.000300",
        "000905.SH": "sh.000905",
        "000016.SH": "sh.000016",
        "399006.SZ": "sz.399006",
    }
    # query_history_k_data_plus 字段（与旧工程一致，含停牌/ST 标记）
    _FIELDS = "date,code,open,high,low,close,volume,amount,turn,tradestatus,pctChg,isST"

    adj_policy = "qfq"  # adjustflag="2"（前复权），符合契约 ADJ_POLICY

    def __init__(self, cache_dir: str = ".cache/baostock", universe: str = "hs300",
                 index_code: str = "000300.SH", retry: int = 3,
                 history_start: Optional[str] = None, min_mcap: float = 0.0,
                 pit_start_year: int = 2005):
        """history_start：分析窗口起点（如 '2024-01-01'），构建内存缓存时丢弃更早数据，
        显著降低内存与计算量；None=全历史。仅影响取数窗口，不影响 parquet 磁盘缓存完整性。
        min_mcap：全 A（ALL）池的市值下限（元），用 AkShare 市值快照过滤小市值/壳股；
        0=不过滤。
        pit_start_year：PIT 财报取数起始年（如 2015）。财报历史按 (年,季) 逐期拉取，
        窗口越小首跑调用越少；结果按股票落 .cache/baostock/financial/*.parquet 复用。"""
        self._cache = Path(cache_dir)
        self._cache.mkdir(parents=True, exist_ok=True)
        self._fin_cache = self._cache / "financial"   # PIT 财报披露表缓存（按股票）
        self._fin_cache.mkdir(parents=True, exist_ok=True)
        self._universe_mode = universe
        self._index_code = index_code
        self._retry = retry
        self._min_mcap = float(min_mcap)
        self._history_start = pd.Timestamp(history_start) if history_start else None
        self._pit_start_year = int(pit_start_year)
        self._connected = False
        self._bs = None
        self._panel_cache: Optional[pd.DataFrame] = None

    # ---- 工具 ----
    def _get_bs(self):
        """懒加载 baostock 模块（无依赖环境不报错）。"""
        if self._bs is None:
            import baostock as bs  # 懒导入
            self._bs = bs
        return self._bs

    def _login(self):
        if not self._connected:
            bs = self._get_bs()
            lg = bs.login()
            if lg.error_code != "0":
                raise ConnectionError(f"BaoStock login failed: {lg.error_msg}")
            self._connected = True

    def _call(self, fn, *args, **kwargs):
        last_err = None
        for i in range(self._retry):
            try:
                self._login()
                return fn(*args, **kwargs)
            except Exception as e:
                last_err = e
                time.sleep(2 ** i * 2)  # 网络抖动 / 服务不稳：退避重试
        raise RuntimeError(f"BaoStock 调用重试 {self._retry} 次仍失败: {last_err}")

    @staticmethod
    def _to_bs_code(code: str) -> str:
        """规范代码 `600000.SH` → baostock `sh.600000`（后缀优先，前缀兜底）。"""
        s = str(code).strip().upper()
        if "." in s:
            num, exch = s.split(".", 1)
            return f"{exch.lower()}.{num}"
        if s.startswith(("4", "8")):
            return f"bj.{s}"
        if s.startswith("6"):
            return f"sh.{s}"
        return f"sz.{s}"

    @staticmethod
    def _safe_float(v, default=None) -> Optional[float]:
        if v is None or v == "":
            return default
        try:
            return float(v)
        except (ValueError, TypeError):
            return default

    @staticmethod
    def _collect_rows(rs) -> list[dict]:
        """手动迭代 baostock 结果集（绕开 pandas 2.x 兼容 bug）。

        baostock 0.9.x 的 rs.get_data() 内部用 df.append（pandas>=2.0 已移除），
        多页结果必崩；改用 next()/get_row_data() 手动循环（不触发 append），
        避免全局 monkey-patch 的副作用。
        """
        if rs is None or rs.error_code != "0":
            return []
        rows = []
        while rs.next():
            row = rs.get_row_data()
            rows.append(dict(zip(rs.fields, row)))
        return rows

    # ---- 股票池 ----
    def _asset_list(self) -> list[str]:
        """当前 universe_mode 的成分股列表（csv 缓存；合成池/zz1000 走 _resolve_universe）。"""
        if self._universe_mode == "ALL" and self._min_mcap > 0:
            key = self._cache / f"asset_list_ALL_m{int(self._min_mcap / 1e8)}e8.csv"
        else:
            key = self._cache / f"asset_list_{self._universe_mode}.csv"
        if key.exists():
            codes = pd.read_csv(key, dtype=str)["code"].tolist()
            if codes:
                return codes
        codes = self._resolve_universe(self._universe_mode)
        pd.DataFrame({"code": codes}).to_csv(key, index=False)
        return codes

    def _resolve_universe(self, mode: str) -> list[str]:
        """按模式解析成分股（递归：合成池可嵌套合成池/zz1000）。

        - 指数池（hs300/zz500/sz50）：baostock 原生接口
        - 合成池（hs800=hs300∪zz500 / hs1800=hs800∪zz1000）：子池递归合并去重
        - zz1000：baostock 无此接口，经 AkShare index_stock_cons 取（见 _asset_list_zz1000）
        - ALL：全市场（市值过滤）
        """
        if mode in self._MERGE_POOLS:
            return self._asset_list_merge(mode)
        if mode in self._INDEX_METHODS:
            return self._asset_list_index(mode)
        if mode == "zz1000":
            return self._asset_list_zz1000()
        if mode == "ALL":
            return self._asset_list_all()
        raise ValueError(
            f"BaoStock universe 仅支持 "
            f"{sorted(set(list(self._INDEX_METHODS) + list(self._MERGE_POOLS) + ['zz1000', 'ALL']))}，"
            f"不支持 {mode}（baostock 无交易所子集接口；zz1000 经 AkShare 取成分股）。"
        )

    def _asset_list_merge(self, mode: str) -> list[str]:
        """合成池：子池递归合并去重（支持嵌套：hs1800 = hs800 ∪ zz1000，hs800 = hs300 ∪ zz500）。"""
        codes = []
        for sub in self._MERGE_POOLS[mode]:
            codes += self._resolve_universe(sub)
        return sorted(set(codes))

    def _asset_list_zz1000(self) -> list[str]:
        """中证1000成分股（baostock 无此接口，经 AkShare index_stock_cons 取，缓存 csv）。

        返回列：品种代码/品种名称/纳入日期（akshare 1.18）；取 '品种代码' 规范化为内部代码。
        价格数据仍由 baostock 按 code 拉取（与指数池一致）。
        """
        try:
            import akshare as ak
            rs = ak.index_stock_cons(symbol="000852")
        except Exception as e:
            print(f"[warn] zz1000 成分股获取失败（AkShare）: {e}", flush=True)
            return []
        if rs is None or rs.empty:
            return []
        col = "品种代码" if "品种代码" in rs.columns else "代码"
        # akshare 该接口偶发重复行（实测 1000 行仅 772 唯一），去重取真实成分股
        return sorted(set(normalize_code(c) for c in rs[col].tolist()))

    def _asset_list_index(self, mode: str) -> list[str]:
        method = getattr(self._get_bs(), self._INDEX_METHODS[mode])
        rs = self._call(method)
        rows = self._collect_rows(rs)
        return [normalize_code(r["code"]) for r in rows if "code" in r]

    def _asset_list_all(self) -> list[str]:
        """全市场股票列表（query_stock_basic 按 type=1 过滤指数）。

        注：不用 query_all_stock——实测其在并发/大结果集下不稳定（当日数据未更新时返回 0、
        大分页可能崩溃 0xC0000409）；query_stock_basic 实测稳定（5541 只全市场）。
        min_mcap>0 时按 AkShare 市值快照过滤小市值/壳股。
        """
        rs = self._call(self._get_bs().query_stock_basic)
        rows = self._collect_rows(rs)
        codes = [normalize_code(r["code"]) for r in rows if r.get("type") == "1"]
        if self._min_mcap > 0 and codes:
            mc = self._share_map()  # AkShare 市值快照（元）
            before = len(codes)
            codes = [c for c in codes if mc.get(c, 0) >= self._min_mcap]
            print(f"[info] ALL 池市值过滤(min={self._min_mcap / 1e8:.0f}亿): "
                  f"{before} -> {len(codes)}", flush=True)
        return codes

    def get_industries(self) -> dict:
        """asset -> 证监会行业（当前快照）。供因子行业中性化使用；空行业过滤。

        数据源：baostock query_stock_industry（全市场一次拉取，缓存 csv）。
        其他 provider 无此方法 → validator 自动降级（仅市值中性化或跳过）。
        """
        key = self._cache / "industries.csv"
        if key.exists():
            df = pd.read_csv(key, dtype={"code": str})
            if len(df):
                return dict(zip(df["code"], df["industry"]))
        rs = self._call(self._get_bs().query_stock_industry)
        rows = self._collect_rows(rs)
        if rows:
            df = pd.DataFrame(rows)
            df["code"] = df["code"].map(normalize_code)
            df = df[df["industry"].astype(str).str.len() > 0]  # 过滤空行业（退市/无分类）
            df[["code", "industry"]].to_csv(key, index=False)
            return dict(zip(df["code"], df["industry"]))
        return {}

    # ---- 市值快照（点估值近似；baostock 无股本接口，复用 AkShare spot 快照）----
    def _share_map(self) -> dict:
        """code -> 总市值（元）。

        baostock 0.9.30 实测 query_stock_basic 不返回股本字段（文档过时），
        故复用 AkShare 东财 spot 快照（共享缓存 _SHARED_MARKET_CAP_CACHE，与 AkShareProvider 同文件），
        口径与 AkShareProvider._market_cap_map 完全一致；失败降级 NaN（契约允许）。
        """
        key = _SHARED_MARKET_CAP_CACHE
        key.parent.mkdir(parents=True, exist_ok=True)
        if key.exists():
            df = pd.read_csv(key, dtype={"code": str})
            if len(df):
                return dict(zip(df["code"], df["mcap"]))
        try:
            import akshare as ak  # 可选依赖：无 akshare 时市值=NaN
            spot = ak.stock_zh_a_spot_em()
            spot = spot.rename(columns={"代码": "code", "总市值": "mcap"})
            spot["code"] = spot["code"].map(normalize_code)
            spot = spot.dropna(subset=["mcap"])
            spot[["code", "mcap"]].to_csv(key, index=False)
            return dict(zip(spot["code"], spot["mcap"]))
        except Exception as e:
            print(f"[warn] baostock 市值快照获取失败（market_cap=NaN 降级）: {e}", flush=True)
        return {}

    # ---- 单票拉取并缓存 ----
    def _fetch_one(self, code: str) -> Optional[pd.DataFrame]:
        bs_code = self._to_bs_code(code)
        rs = self._call(self._get_bs().query_history_k_data_plus,
                        bs_code, self._FIELDS, "2000-01-01", "2099-12-31",
                        frequency="d", adjustflag="2")  # 前复权
        rows = self._collect_rows(rs)
        if not rows:
            return None
        df = pd.DataFrame(rows)
        df["date"] = pd.to_datetime(df["date"])
        df["asset"] = code
        df["open"] = df["open"].map(lambda v: self._safe_float(v, np.nan))
        df["high"] = df["high"].map(lambda v: self._safe_float(v, np.nan))
        df["low"] = df["low"].map(lambda v: self._safe_float(v, np.nan))
        df["close"] = df["close"].map(lambda v: self._safe_float(v, np.nan))
        df["volume"] = df["volume"].map(lambda v: self._safe_float(v, np.nan))          # 股（契约）
        df["amount"] = df["amount"].map(lambda v: self._safe_float(v, np.nan))          # 元
        df["turnover"] = df["turn"].map(lambda v: self._safe_float(v, np.nan))     # 百分比
        df["tradestatus"] = df["tradestatus"].map(lambda v: self._safe_float(v, np.nan))
        df["is_st"] = df["isST"].map(lambda v: self._safe_float(v, np.nan))
        # 市值：AkShare spot 总市值快照（元，点估值近似；缺失 NaN）
        mcap = self._share_map()
        df["market_cap"] = df["asset"].map(mcap) if mcap else np.nan
        cols = ["date", "asset", "open", "high", "low", "close", "volume",
                "amount", "turnover", "market_cap", "tradestatus", "is_st"]
        df = df[[c for c in cols if c in df.columns]]
        return df.set_index(["date", "asset"])

    # ---- DataProvider 接口 ----
    def _load_full_panel(self) -> pd.DataFrame:
        if self._panel_cache is not None:
            return self._panel_cache
        assets = self._asset_list()
        parts = []
        missing = 0
        for code in assets:
            cache = self._cache / f"{code}.parquet"
            if cache.exists():
                df = pd.read_parquet(cache)
            else:
                df = self._fetch_one(code)
                if df is not None:
                    df.to_parquet(cache)
            if df is None:
                missing += 1
                continue
            # 内存裁剪：大池（全 A）必须先按窗口裁剪再 concat，避免全历史撑爆内存
            if self._history_start is not None:
                df = df[df.index.get_level_values("date") >= self._history_start]
            parts.append(df)
        if missing:
            print(f"[warn] {self._universe_mode} 池 {missing}/{len(assets)} 只无数据"
                  f"（断连/停牌/退市；面板不完整，请重跑缓存脚本续拉）", flush=True)
        if not parts:
            panel = pd.DataFrame(columns=["date", "asset"] + _FIELDS).set_index(["date", "asset"])
        else:
            panel = pd.concat(parts).sort_index()
        self._panel_cache = panel
        return panel

    def get_panel(self, fields: list[str], start, end) -> pd.DataFrame:
        panel = self._load_full_panel()
        dlevel = panel.index.get_level_values("date")
        lo = pd.Timestamp(start) if start is not None else dlevel.min()
        hi = pd.Timestamp(end) if end is not None else dlevel.max()
        sub = panel.loc[(dlevel >= lo) & (dlevel <= hi)]
        sub = sub[[c for c in fields if c in sub.columns]]
        sub = canonicalize_panel(sub)           # 契约：统一索引名/代码后缀
        validate_panel(sub, "BaoStock", fields)  # 契约：单位/格式校验
        return sub

    def get_index_returns(self, index_code: Optional[str] = None,
                          start=None, end=None) -> pd.Series:
        code = index_code or self._index_code
        bs_code = self._INDEX_KLINE.get(code)
        if bs_code is None:
            return pd.Series(dtype=float)
        key = self._cache / f"idx_{code}.parquet"
        if key.exists():
            df = pd.read_parquet(key)
        else:
            rs = self._call(self._get_bs().query_history_k_data_plus,
                            bs_code, "date,pctChg", "2000-01-01", "2099-12-31",
                            frequency="d", adjustflag="2")
            rows = self._collect_rows(rs)
            if not rows:
                return pd.Series(dtype=float)
            df = pd.DataFrame(rows)
            df["date"] = pd.to_datetime(df["date"])
            df["pct_chg"] = pd.to_numeric(df["pctChg"], errors="coerce")
            df = df[["date", "pct_chg"]].set_index("date")
            df.to_parquet(key)
        lo = pd.Timestamp(start) if start else df.index.min()
        hi = pd.Timestamp(end) if end else df.index.max()
        s = df.loc[(df.index >= lo) & (df.index <= hi), "pct_chg"] / 100.0  # 百分比→小数
        s = s.astype(float)
        validate_returns(s, "BaoStock")
        return s

    # ---- PIT 基本面管线（point-in-time 财报，防前视核心）----
    # 字段映射：规范名 -> baostock 原始列名。
    # 🔴 红线前提：baostock 免费接口只暴露【指标级】字段（利润表/资产负债表/现金流量表
    #    的汇总指标 + 业绩快报），**不提供完整三大表明细行项目**。经实拉验证可用：
    #      revenue(营业收入)      <- profit_data.MBRevenue        （元，实测 sh.600519 2023=1472亿 ✓）
    #      net_profit(净利润)     <- profit_data.netProfit        （元）
    #      total_assets(总资产)   <- express.performanceExpressTotalAsset   （元，仅业绩快报，实测 ✓）
    #      net_assets(净资产)     <- express.performanceExpressNetAsset     （元，仅业绩快报，实测 ✓）
    #    下列字段 baostock 免费接口【根本不返回】，一律返回 NaN，**绝不伪造**：
    #      cogs(营业成本) / inventory(存货) / accounts_receivable(应收账款)
    #    → 这意味着 f0014a(存货周转天数)/f0015a(应收账款周转天数) 无法仅靠 baostock 构建，
    #      须由 TushareProvider（income/balancesheet 全表明细，需积分）补 PIT 管线（见测试与汇报）。
    _PIT_FIELD_MAP = {
        "revenue": "MBRevenue",
        "net_profit": "netProfit",
        "total_assets": "performanceExpressTotalAsset",
        "net_assets": "performanceExpressNetAsset",
    }
    # baostock 免费接口缺失、只能返回 NaN 的字段（明确登记，防误用/防伪造）
    _PIT_FIELD_UNAVAILABLE = frozenset({"cogs", "inventory", "accounts_receivable"})

    def _fetch_financial_history(self, code: str) -> pd.DataFrame:
        """拉取单票全部财报披露历史，返回长表（已缓存 .cache/baostock/financial/{code}.parquet）。

        列：statDate(报告期) / pubDate(公告日，PIT 对齐的唯一依据) / 各可用原始字段。
        每个 (年,季) 调一次 profit_data（取 营业收入/净利润）；业绩快报一次拉全（取 总资产/净资产）。
        balance_data / cash_flow_data 仅含比率、无可用行项目，跳过以省调用。
        单票首跑约 (当前年-_pit_start_year+1)×4 + 1 次调用，落缓存后零网络。
        """
        key = self._fin_cache / f"{code}.parquet"
        if key.exists():
            return pd.read_parquet(key)
        bs_code = self._to_bs_code(code)
        bs = self._get_bs()
        this_year = pd.Timestamp.now().year
        recs = []
        # 利润表指标（营业收入/净利润），按 (年,季) 逐期
        for yr in range(self._pit_start_year, this_year + 1):
            for q in (1, 2, 3, 4):
                rs = self._call(bs.query_profit_data, bs_code, str(yr), str(q))
                for r in self._collect_rows(rs):
                    recs.append({
                        "statDate": r.get("statDate"),
                        "pubDate": r.get("pubDate"),
                        "MBRevenue": self._safe_float(r.get("MBRevenue")),
                        "netProfit": self._safe_float(r.get("netProfit")),
                        "performanceExpressTotalAsset": np.nan,
                        "performanceExpressNetAsset": np.nan,
                    })
        # 业绩快报（总资产/净资产），按日期区间一次拉全
        rs = self._call(bs.query_performance_express_report, bs_code,
                        f"{self._pit_start_year}-01-01", "2099-12-31")
        for r in self._collect_rows(rs):
            recs.append({
                "statDate": r.get("performanceExpStatDate"),
                "pubDate": r.get("performanceExpPubDate"),
                "MBRevenue": np.nan,
                "netProfit": np.nan,
                "performanceExpressTotalAsset": self._safe_float(r.get("performanceExpressTotalAsset")),
                "performanceExpressNetAsset": self._safe_float(r.get("performanceExpressNetAsset")),
            })
        if not recs:
            df = pd.DataFrame(columns=["statDate", "pubDate", "MBRevenue", "netProfit",
                                       "performanceExpressTotalAsset", "performanceExpressNetAsset"])
        else:
            df = pd.DataFrame(recs)
            df["statDate"] = pd.to_datetime(df["statDate"], errors="coerce")
            df["pubDate"] = pd.to_datetime(df["pubDate"], errors="coerce")
            # 丢弃无报告期/无公告日的脏行；同 (statDate,pubDate) 去重
            df = df.dropna(subset=["statDate", "pubDate"]).drop_duplicates(
                ["statDate", "pubDate"], keep="last").reset_index(drop=True)
        df.to_parquet(key)
        return df

    @staticmethod
    def _pit_select_snapshot(disc: pd.DataFrame, fields: list[str], as_of) -> dict:
        """PIT 核心：从披露历史中选截至 as_of 可获取的【最新已披露】各字段值。

        前视安全保证（血牢红线）：
          1. 仅保留 pubDate <= as_of 的行 → 未披露的财报一律不可见（无前视）。
          2. 重述处理：同一 (statDate, pubDate) 视为同一披露事件，去重保留末次。
          3. 🔴 字段独立取数（修复前任 total_assets=nan 的坑）：
             利润表 report（query_profit_data，pubDate 较晚）与业绩快报 express
             （query_performance_express_report，pubDate 较早）是【两条独立披露流】，
             各自只携带部分字段——report 有 revenue/net_profit 但资产为 nan，
             express 有 total_assets/net_assets 但收入利润为 nan。
             二者通常共享同一 statDate（如 2023-12-31），若按"整行取最新披露"
             会把 report 年报（nan 资产）覆盖 express（有值资产）→ total_assets=nan。
             → 故对【每个字段】独立取其在 pubDate<=as_of 内最新披露（pubDate 最大）
               且非缺失的值；这样 revenue 取 report、assets 取 express，互不干扰。
             这也是更纯粹的 PIT：截至任意日期，市场已知某指标的最新披露值。
          4. statDate 仅作元数据，绝不作为时间过滤/选择依据
             （报告期结束日 ≠ 披露日，前视即失真）。
        返回 {field: value}，不可用字段 / 无数据 → NaN。
        """
        as_of = pd.Timestamp(as_of)
        out = {f: np.nan for f in fields}
        if disc is None or len(disc) == 0:
            return out
        d = disc.copy()
        d["pubDate"] = pd.to_datetime(d["pubDate"], errors="coerce")
        d["statDate"] = pd.to_datetime(d["statDate"], errors="coerce")
        # (1) PIT 红线：披露日 <= as_of
        d = d[d["pubDate"] <= as_of]
        if d.empty:
            return out
        # (2) 重述：同一披露事件 (statDate, pubDate) 去重，保留末次（最新同日报送）
        d = d.drop_duplicates(["statDate", "pubDate"], keep="last")
        # (3) 字段独立取最新披露值（pubDate 最大且非缺失）
        for f in fields:
            raw = BaoStockProvider._PIT_FIELD_MAP.get(f)
            if raw is None:        # 含 baostock 免费缺失字段 → NaN（绝不伪造）
                continue
            col = d.get(raw)
            if col is None:
                continue
            valid = d[col.notna()]
            if valid.empty:
                continue
            latest = valid.loc[valid["pubDate"].idxmax()]
            v = latest[raw]
            out[f] = v if (v is not None and pd.notna(v)) else np.nan
        return out

    def get_pit_financials(self, fields: list[str], as_of_date,
                           assets: Optional[list[str]] = None) -> pd.DataFrame:
        """返回截至 as_of_date 实际可获取的 PIT 财报快照，MultiIndex(date, asset)。

        每行 = 该股票截至 as_of_date 最新已披露财报的字段值（按 pubDate 对齐，无前视）。
        date 层固定为 as_of_date（截面快照视角）；如需历史披露序列请逐 as_of 调用。
        assets=None 时对配置的 universe 全量拉取（首跑按股票缓存，慢但可复用）。

        只暴露当时市场已知信息：pubDate > as_of_date 的财报（含未披露的年报/季报）绝不出现。
        """
        as_of = pd.Timestamp(as_of_date)
        assets = assets if assets is not None else self._asset_list()
        assets = [normalize_code(a) for a in assets]
        records = []
        for code in assets:
            disc = self._fetch_financial_history(code)
            snap = self._pit_select_snapshot(disc, fields, as_of)
            records.append({"date": as_of, "asset": code, **snap})
        if not records:
            df = pd.DataFrame(columns=["date", "asset"] + list(fields)).set_index(["date", "asset"])
        else:
            df = pd.DataFrame(records).set_index(["date", "asset"])
            df = df[[c for c in fields if c in df.columns]]   # 保序保留请求字段
        return df

    def list_universe(self, date: str) -> list[str]:
        # 当前快照口径（指数成分股/当日全市场），与 Tushare 近似非 PIT 一致
        try:
            return self._asset_list()
        except Exception:
            return []

    def get_adv(self, date: str, window: int = 20) -> pd.Series:
        return pd.Series(dtype=float)

    def health_check(self) -> bool:
        """探测 baostock 可用性（登录 + 单票小查询）。"""
        try:
            self._login()
            bs = self._get_bs()
            rs = bs.query_history_k_data_plus(
                "sh.600519", "date,close", "2024-01-02", "2024-01-03",
                frequency="d", adjustflag="2")
            return len(self._collect_rows(rs)) > 0
        except Exception:
            return False
