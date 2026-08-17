"""数据契约（Data Contract）—— 接口层强制的单位 / 格式规范。

为何存在（见 ADR-0001 / RESEARCH_LOG R2026-0804-05）：
可插拔 DataProvider 设计的核心风险是"切换数据源后结果悄悄变化"——根因几乎都落在
单位（手 vs 股、千元 vs 元）、格式（代码带不带后缀、索引列名）、复权口径不一致。
本模块把契约集中定义，并提供运行时校验器与规范化器，让任何新 Provider 在 get_panel
返回前必须通过校验，否则立即报错，而非污染因子结果。

契约要点（所有 Provider 必须遵守）：
1. 面板索引：MultiIndex，level0 名 `date`（datetime64[ns]，无时区），level1 名 `asset`（str，规范代码）。
2. 规范代码：6 位数字 + 交易所后缀，如 `000001.SZ` / `600000.SH` / `830000.BJ`。
3. 价格列（open/high/low/close/pre_close）：前复权(qfq)价，单位 CNY（元）。
4. volume：成交量，单位 **股(shares)**，非手(lots)。
5. amount：成交额，单位 **元(CNY)**，非千元。
6. turnover：换手率，单位 **百分比**，非小数。软区间 0–1000（单日 >100% 真实存在，勿卡 100）。
7. market_cap：总市值，单位 **元(CNY)**。
8. 收益率（get_index_returns / pct_chg）：小数（0.01 = +1.00%），非百分数。
9. 缺失值用 NaN（float）表示，禁止用 0 代表缺失，禁止静默前向填充。
10. 面板按 (date, asset) 升序排序。

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🔴 PIT 分级（2026-08-08 补，踩坑后立）：**契约保证的是单位与格式，不保证 PIT**
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- ✅ **PIT 安全**：open/high/low/close 的**收益**、volume、amount、turnover、
  tradestatus、is_st —— 均为当日实际发生量。
- ⚠️ **PIT 存疑**：价格**水平**（前复权价含未来分红送转信息，故价格"高低"不可跨期
  比较，但相邻两日的**比值/收益**是干净的）。
- ❌ **非 PIT**：`market_cap`。所有 Provider（AkShare / BaoStock）都是取**今日**总市值
  快照后 `df["asset"].map(...)` 贴到该股全部历史日期上，时序 nunique == 1。
  实测 2013 年用它分市值档，与真实 PIT 市值的分组一致率仅 **53.7%**，且"小盘组"
  实际等于"到今天仍然小的公司"= 后视选股。
  → 需要历史市值时一律用 `data.pit.pit_float_mcap()`（= amount/(turnover/100)）。
  → 现存已知依赖：`validate/validator.py::_neutralize_cross_section`（市值中性化，
     已有 caveat 注释）、`factors/zoo_basics.py::size_log_mcap`（研究中，未交付）。

⚠️ 特别注意：`assert_no_lookahead` **查不出**这类问题。它检查的是"compute 有没有切到
as_of 之后的行"，而这里是**列本身被未来信息污染**——切片再干净也没用。与 exec_lag
（回测阶段前视）并列为本项目两大"审计过 ≠ 无前视"陷阱。
"""
from __future__ import annotations

import re
from typing import Iterable, Optional

import numpy as np
import pandas as pd

# ---- 规范字段表：字段 -> (dtype, 单位/语义, 软合理区间[min, max]) ----
# 软区间用于捕获明显单位错（手当股、千元当元、百分数当小数等），越界即抛错。
PANEL_FIELDS: dict[str, tuple[str, str, tuple[float, float]]] = {
    "open":       ("float64", "前复权开盘价 CNY", (0.01, 1_000_000.0)),
    "high":       ("float64", "前复权最高价 CNY", (0.01, 1_000_000.0)),
    "low":        ("float64", "前复权最低价 CNY", (0.01, 1_000_000.0)),
    "close":      ("float64", "前复权收盘价 CNY", (0.01, 1_000_000.0)),
    "pre_close":  ("float64", "前复权昨收价 CNY", (0.01, 1_000_000.0)),
    "volume":     ("float64", "成交量 股(shares)", (0.0, 1e13)),
    "amount":     ("float64", "成交额 元(CNY)", (0.0, 1e15)),
    # 换手率上限刻意放到 1000 而非 100：单日换手 >100% 是 A 股真实现象
    # （次新股 / ST 摘帽 / 小盘妖股，历史极值可达数百 %）。上限设 100 会把真数据
    # 误判成单位错并中断全池回填（2026-08-07 六池回填即因样例值 106.48 崩在 hs1800）。
    # 1000 仍能捕获"股/手混淆(100x)""小数当百分数(0.05→被当 0.05%)"这类真单位错。
    "turnover":   ("float64", "换手率 百分比(0-1000)", (0.0, 1000.0)),
    "market_cap": ("float64", "总市值 元(CNY)", (0.0, 1e16)),
    # baostock 独有标记字段（其他源缺省 NaN；0/1 整数语义，缺失须 NaN 非 0）
    "tradestatus": ("float64", "交易状态 0=停牌/1=正常", (0.0, 1.0)),
    "is_st":       ("float64", "ST标记 0=正常/1=ST", (0.0, 1.0)),
}
INDEX_NAMES: tuple[str, str] = ("date", "asset")
ADJ_POLICY = "qfq"  # 复权口径：前复权
CODE_RE = re.compile(r"^(\d{6})\.(SH|SZ|BJ)$")

# 交易所推断表：按代码前缀映射（akshare 无后缀代码用）
_EXCH_BY_PREFIX: dict[str, str] = {
    "60": "SH", "68": "SH", "5": "SH", "9": "SH",   # 沪市/科创板/沪市基金/沪市B
    "00": "SZ", "30": "SZ", "002": "SZ", "003": "SZ",  # 深市/创业板
    "8": "BJ", "4": "BJ",                             # 北交所
}


def normalize_code(code: str) -> str:
    """把任意常见写法规范为 `{6位}.{SH|SZ|BJ}`。

    支持：000001 / 000001.SZ / sz000001 / 600000.SH / sh.600000 / bj.830000 / 830000。
    无法识别时原样返回（交由校验器捕获报错）。
    """
    s = str(code).strip().upper()
    if CODE_RE.match(s):
        return s
    # 点分隔前缀：sh.600000 / sz.000001 / bj.830000（baostock 格式）
    m = re.match(r"^(SH|SZ|BJ)\.(\d{6})$", s)
    if m:
        return f"{m.group(2)}.{m.group(1)}"
    # 去 sh/sz/bj 前缀（如 sz000001 -> 000001）
    s2 = re.sub(r"^(SH|SZ|BJ)", "", s)
    if not re.fullmatch(r"\d{6}", s2):
        return str(code)  # 无法识别，原样返回
    p3, p2, p1 = s2[:3], s2[:2], s2[0]
    if p3 in _EXCH_BY_PREFIX:
        exch = _EXCH_BY_PREFIX[p3]
    elif p2 in _EXCH_BY_PREFIX:
        exch = _EXCH_BY_PREFIX[p2]
    else:
        exch = _EXCH_BY_PREFIX.get(p1, "SZ")  # 兜底深市
    return f"{s2}.{exch}"


def canonicalize_panel(panel: pd.DataFrame) -> pd.DataFrame:
    """规范化面板：索引名统一为 (date, asset)，asset 代码补交易所后缀。

    返回新 DataFrame，不改动传入对象。
    注：显式 from_arrays 重建索引，避开 MultiIndex.set_levels 在多资产时的完整性校验坑。
    """
    df = panel.copy()
    if not isinstance(df.index, pd.MultiIndex):
        return df
    l0 = df.index.get_level_values(0)
    l1 = df.index.get_level_values(1)
    d = pd.to_datetime(l0) if not str(l0.dtype).startswith("datetime64") else l0
    codes = [normalize_code(str(a)) for a in l1]
    df.index = pd.MultiIndex.from_arrays([d, codes], names=list(INDEX_NAMES))
    return df


def validate_panel(panel: pd.DataFrame, provider: str,
                   fields: Optional[Iterable[str]] = None) -> None:
    """运行时校验面板是否符合契约，违反抛 ValueError（带 provider 名便于定位）。

    这是"切换数据源结果不一致"的防火墙：单位/格式错在返回前炸出来，而非污染因子。
    """
    if not isinstance(panel.index, pd.MultiIndex):
        raise ValueError(f"[{provider}] 面板索引必须是 MultiIndex(date, asset)，实际 {type(panel.index)}")
    if list(panel.index.names) != list(INDEX_NAMES):
        raise ValueError(f"[{provider}] 面板索引名必须为 {INDEX_NAMES}，实际 {list(panel.index.names)}")
    dlevel = panel.index.get_level_values("date")
    if not (str(dlevel.dtype).startswith("datetime64") and getattr(dlevel, "tz", None) is None):
        raise ValueError(f"[{provider}] date 层须为 datetime64[ns] 无时区，实际 {dlevel.dtype}")
    alevel = panel.index.get_level_values("asset")
    if alevel.dtype.kind not in ("O", "U", "S"):
        raise ValueError(f"[{provider}] asset 层须为字符串，实际 dtype {alevel.dtype}")
    bad = [a for a in alevel.unique() if not CODE_RE.match(str(a))]
    if bad:
        raise ValueError(f"[{provider}] 存在非规范股票代码（需 6位.交易所后缀，如 000001.SZ）: {bad[:5]}")
    # 字段单位软校验
    check = list(fields) if fields else list(panel.columns)
    for f in check:
        if f not in PANEL_FIELDS:
            continue
        lo, hi = PANEL_FIELDS[f][2]
        col = panel[f].dropna()
        if len(col) == 0:
            continue
        if (col < lo).any() or (col > hi).any():
            sample = col[(col < lo) | (col > hi)].iloc[0]
            raise ValueError(
                f"[{provider}] 字段 `{f}` 超出合理区间 [{lo}, {hi}]，疑似单位错误；样例值={sample}。"
                f"请检查该源单位换算（股/手、元/千元、百分比/小数）。"
            )
    # 缺失须用 NaN：volume/amount/market_cap 不应出现全 <=0 的活跃日（0 占位=错误）
    for f in ("volume", "amount", "market_cap"):
        if f in panel.columns:
            col = panel[f].dropna()
            if len(col) and bool((col <= 0).all()):
                raise ValueError(
                    f"[{provider}] 字段 `{f}` 全部 <=0，疑似用 0 占位缺失或单位错误（应为正数）。"
                )


def validate_returns(s: pd.Series, provider: str) -> None:
    """校验收益率序列：datetime 索引 + 值为小数。

    阈值说明：A股单日涨跌停上限 10%/20%/30%（主板/创业科创/北交），日收益率绝对值
    超过 50% 必为百分数误传（0.01=+1% 的小数契约）。注意：0.02 vs 2% 这类细微单位错
    校验器无法区分，须由 Provider 层保证换算正确。
    """
    if not isinstance(s.index, pd.DatetimeIndex):
        raise ValueError(f"[{provider}] 收益率索引须为 DatetimeIndex，实际 {type(s.index)}")
    v = s.dropna()
    if len(v) == 0:
        return
    if (v.abs() > 0.5).any():
        raise ValueError(
            f"[{provider}] 收益率疑似为百分数而非小数（样例 {v[v.abs() > 0.5].iloc[0]}）；"
            "契约要求 0.01=+1% 的小数表示。"
        )


def assert_adj_policy(provider_adj: str, allow_mismatch: bool = False) -> None:
    """复权口径防火墙：所选数据源的复权口径必须与契约 ADJ_POLICY 一致，否则 fail-loud。

    这是"切换数据源结果悄悄变化"的最后一道防火墙——契约声明 ADJ_POLICY=\"qfq\"，
    若某 Provider（如 Tushare 免费档）只能返回不复权(raw)价，静默混入主流程会让因子结果
    在除权除息日出现伪信号。故：不一致时默认直接抛错；仅在诊断场景（如 cross_source_check
    的方向性核对）显式 allow_mismatch=True 放行，并要求调用方在产物上标注口径差异。
    """
    if provider_adj == ADJ_POLICY:
        return
    msg = (
        f"复权口径不一致：Provider 声明 adj_policy='{provider_adj}'，"
        f"但契约 ADJ_POLICY='{ADJ_POLICY}'。"
        f"静默用不一致复权口径跑主流程会污染因子结果（除权除息日伪信号）。"
    )
    if allow_mismatch:
        import warnings
        warnings.warn(msg + "（已显式放行：仅允许于方向性诊断，主流程禁止。）")
        return
    raise RuntimeError(msg + "若确须使用，请显式设 FF_ALLOW_ADJ_MISMATCH=1 并在产物标注口径。")
