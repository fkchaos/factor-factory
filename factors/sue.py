"""SUE（Standardized Unexpected Earnings，标准化未预期盈余）· f0076a。

为什么做它（PEAD 正统做法，且与既有因子的关键差别）：
  - f0072a 净利同比只是**未标准化的同比增速**，高波动公司的 30% 增长和低波动公司的
    30% 增长含的信息量完全不同；SUE 除以"历史盈余惊喜的波动率"，把**惊喜程度标准化**。
  - 预期用**季节性随机游走**（Q_t 的预期 = Q_{t-4}，即去年同季），不需要卖方一致预期，
    因此**覆盖率 100%**（有财报就有值），绕开了业绩预告只有 28–36% 覆盖的约束。
  - 数据全部来自已有的 PIT 财报缓存（PARENT_NETPROFIT + 公告日），**零新增数据源成本**。

计算口径（Foster-Olsen-Shevlin 1984 / Bernard-Thomas 1989 的 A 股落地版）：
  1. 报表净利是**累计口径**（Q1 / H1 / Q1-Q3 / 全年），先拆成单季：
     Q1 = cum_Q1；Q2 = cum_H1 − cum_Q1；Q3 = cum_Q3 − cum_H1；Q4 = cum_年报 − cum_Q3
  2. 盈余惊喜 UE_t = Q_t − Q_{t−4}（同比，天然剔除季节性）
  3. 标准化 SUE_t = UE_t / std(UE_{t−1} … UE_{t−8})（过去 8 个季度的惊喜波动）
     —— 分母要求至少 min_hist(4) 个有效历史惊喜，否则该期无值（避免小样本噪声）

🔴 PIT 安全（与 fundamentals.py 同纪律）：
  - 只消费 pubDate <= as_of 的披露事件；同一报告期的更正/重述按 pubDate 升序后者覆盖
    前者 → 得到"当时可见的版本"，绝不用最终重述版回算历史。
  - 因子值在公告日跳变、之后阶梯保持（财报特性，非前视）。

⚠️ 如实标注的口径限制：
  - warm-up：需要 4 个历史同季，故每票上市/有数据后约 2 年才有 SUE（窗口 2020 起，
    PIT 缓存通常回溯到 2007，故 2020 年时点 warm-up 已满足）。
  - 单季拆分依赖前一季度累计值存在；缺失（如只披露年报的公司）则该期跳过。
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from factors.interface import register_factor, slice_panel_to_date
from data.pit_fundamentals import default_store

FIELD = "net_profit_parent"


# ---------------- 纯函数（便于单测，无 IO）----------------
def to_quarterly(cum: pd.Series) -> pd.Series:
    """累计口径 → 单季口径。

    Args:
        cum: index=statDate（报告期末），value=年初至今累计值。
    Returns:
        Series，index=MultiIndex(y, q)，按时间升序；无法拆分的期（缺前一季）被跳过。
    """
    if cum is None or len(cum) == 0:
        return pd.Series(dtype=float)
    idx = pd.to_datetime(pd.Index(cum.index))
    y = np.asarray(idx.year)
    q = np.asarray((idx.month - 1) // 3 + 1)
    # 🔴 必须传裸数组：若传带 RangeIndex 的 Series 并同时给 index=MultiIndex，
    # pandas 会按索引对齐 → 全部变 NaN 且不报错（静默失真）。
    df = pd.DataFrame(
        {"v": np.asarray(cum.values, dtype=float)},
        index=pd.MultiIndex.from_arrays([y, q], names=["y", "q"]),
    )
    # 同一 (y,q) 多条（理论上已按 pubDate 覆盖过，兜底取最后一条）
    df = df[~df.index.duplicated(keep="last")].sort_index()
    out: dict[tuple[int, int], float] = {}
    for (yy, qq), row in df.iterrows():
        v = row["v"]
        if pd.isna(v):
            continue
        if qq == 1:
            prev = 0.0
        else:
            if (yy, qq - 1) not in df.index:
                continue  # 缺前一季度累计 → 无法拆单季
            prev = df.loc[(yy, qq - 1), "v"]
            if pd.isna(prev):
                continue
        out[(int(yy), int(qq))] = float(v) - float(prev)
    if not out:
        return pd.Series(dtype=float)
    s = pd.Series(out)
    s.index = pd.MultiIndex.from_tuples(list(out.keys()), names=["y", "q"])
    return s.sort_index()


def sue_map(cum: pd.Series, min_hist: int = 4, lookback: int = 8) -> dict[tuple[int, int], float]:
    """累计序列 → {(年, 季): SUE}。只返回**有足够历史**且波动非零的期。"""
    q = to_quarterly(cum)
    if len(q) < 5:  # 至少 5 季才能有 1 个同比对
        return {}
    keys = list(q.index)
    vals = [float(v) for v in q.to_numpy()]
    out: dict[tuple[int, int], float] = {}
    for i in range(4, len(vals)):
        ue = vals[i] - vals[i - 4]
        if not np.isfinite(ue):
            continue
        lo = max(4, i - lookback)
        hist = [vals[j] - vals[j - 4] for j in range(lo, i)]
        hist = [h for h in hist if np.isfinite(h)]
        if len(hist) < min_hist:
            continue
        sd = float(np.std(hist, ddof=1))
        if not np.isfinite(sd) or sd <= 0:
            continue
        out[(int(keys[i][0]), int(keys[i][1]))] = ue / sd
    return out


def _cum_asof(events: pd.DataFrame, as_of) -> pd.Series:
    """截至 as_of 可见的累计序列（同一报告期取当时最新披露版本）。"""
    as_of = pd.Timestamp(as_of)
    if events is None or len(events) == 0:
        return pd.Series(dtype=float)
    ev = events[events["pubDate"] <= as_of]
    if len(ev) == 0:
        return pd.Series(dtype=float)
    cum = {}
    for _, r in ev.iterrows():
        cum[pd.Timestamp(r["statDate"])] = float(r["value"])
    return pd.Series(cum).sort_index()


def _sue_asof(events: pd.DataFrame, as_of):
    """截至 as_of 的最新一期 SUE（慢路径用）。"""
    m = sue_map(_cum_asof(events, as_of))
    if not m:
        return np.nan
    return m[max(m.keys())]


# ---------------- 因子 ----------------
class SUEFactor:
    """SUE = (当季净利 − 去年同季净利) / 过去 8 季该惊喜的标准差。"""

    name = "sue"
    fcode = "f0076a"
    universe_hint = "hs300"
    pit_fields = [FIELD]

    # ---- 慢路径：逐日逐票（测试基准；生产走 compute_panel 快路径）----
    def compute(self, panel: pd.DataFrame, as_of_date, ctx=None) -> pd.Series:
        t = pd.Timestamp(as_of_date)
        sub = slice_panel_to_date(panel, t)
        assets = sub.index.get_level_values("asset").unique().tolist()
        svc = (ctx or {}).get("pit_service")
        if svc is None:
            svc = default_store(assets, self.pit_fields)
        out = {}
        for a in assets:
            ev = svc.disclosure_events(a, FIELD)
            if len(ev) == 0:
                continue
            v = _sue_asof(ev, t)
            if pd.notna(v):
                out[a] = float(v)
        return pd.Series(out, dtype=float)

    # ---- 快路径：事件驱动（只在公告日算一次，再阶梯 ffill）----
    def compute_panel(self, panel: pd.DataFrame, ctx=None) -> pd.DataFrame:
        dates = pd.DatetimeIndex(sorted(panel.index.get_level_values("date").unique()))
        assets = list(dict.fromkeys(panel.index.get_level_values("asset")))
        svc = (ctx or {}).get("pit_service")
        if svc is None:
            svc = default_store(assets, self.pit_fields)
        cols = {}
        for a in assets:
            ev = svc.disclosure_events(a, FIELD)
            if len(ev) == 0:
                continue
            # 窗口前的披露也要纳入（warm-up 历史），但只在窗口内输出值
            steps: dict[pd.Timestamp, float] = {}
            cum: dict[pd.Timestamp, float] = {}
            for pub, grp in ev.groupby("pubDate", sort=True):
                for _, r in grp.iterrows():
                    cum[pd.Timestamp(r["statDate"])] = float(r["value"])
                m = sue_map(pd.Series(cum).sort_index())
                if not m:
                    continue
                v = m[max(m.keys())]
                if np.isfinite(v):
                    steps[pd.Timestamp(pub)] = float(v)
            if not steps:
                continue
            ser = pd.Series(steps).sort_index()
            # 公告当日即生效（PIT 口径 pubDate <= as_of），之后 ffill 到每个交易日
            cols[a] = ser.reindex(dates.union(ser.index)).ffill().reindex(dates)
        return pd.DataFrame(cols, index=dates) if cols else pd.DataFrame(index=dates)


register_factor(SUEFactor())
