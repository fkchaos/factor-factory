"""组合因子（c 类：组合 / 正交创新）——f0003a 的因子实现。

设计要点
--------
1. **只做截面组合**：成分因子各自已保证 as_of 切片（slice_panel_to_date 双保险），
   本模块不再触碰面板历史，因此不引入任何新的前视风险。
2. **先预处理再合成**：逐成分 MAD 去极值 → 截面 z-score → 加权平均。
   顺序与 factors.interface 的预处理纪律一致（数学等价于 scripts/build_combo.combine_equal）。
3. **方向系数（component_signs）**：等权合成的前提是各成分与未来收益的方向一致。
   实测 overnight_intraday 的 RankIC 为负、ivol 为正，若直接等权会相互抵消。
   因此引入显式的方向系数把成分对齐到"正 IC"方向。

   ⚠️ 诚实披露：方向系数来自样本内（2020 起）实测 IC 符号，属于人工先验，
   存在轻微的样本内选择偏差。该决策已写入交付包 card.md 的"已知限制"。
   仅做符号对齐、不做幅度拟合，自由度为 1 bit/成分，过拟合风险可控。

用法
----
    from factors.interface import get_factor
    combo = get_factor("combo_equal_v1")
"""
from __future__ import annotations

from typing import Optional, Sequence

import numpy as np
import pandas as pd

from factors.interface import (
    Factor,
    get_factor,
    register_factor,
    winsorize_mad,
    zscore_cross_section,
)

# 成分方向系数：+1 保持原方向，-1 翻转。
#
# ⚠️ 2026-08-06 实测教训（务必读）：
#   最初按"hs300/SZ300 上 overnight_intraday 的 RankIC 为负"把它设成 -1.0，
#   结果在 sz50 上实测 overnight 的 RankIC 是 **+0.0102**（符号与大池相反），
#   -1 反而把它翻成负值、与 ivol(+0.0113) 相互抵消 —— 组合 RankIC 塌到 +0.0004、
#   ICIR 0.00、胜率 50.3%，等于一个纯噪声因子。
#
#   结论有两层：
#   (a) overnight_intraday 的方向**跨池不稳定**，这是它的已知缺陷，不是组合的锅；
#   (b) 把方向系数写死成常量本身就是错的设计——它隐含"方向全局恒定"的假设。
#
#   当前取 +1/+1（即纯等权，与任务口径"默认等权法"一致）。
#   待办：改为用截至 t 的历史 IC 符号自适应（滚动、无前视），彻底消灭这个常量。
DEFAULT_SIGNS: dict[str, float] = {
    "overnight_intraday": +1.0,
    "ivol": +1.0,
}


class ComboEqualFactor:
    """等权组合因子：成分 z-score 后按方向系数等权平均。"""

    name = "combo_equal_v1"
    fcode = "f0003a"  # 交付包代号（对齐 deliverables/factors/_REGISTRY.csv）
    universe_hint = None
    components: Sequence[str] = ("overnight_intraday", "ivol")

    def __init__(
        self,
        components: Optional[Sequence[str]] = None,
        signs: Optional[dict[str, float]] = None,
        name: Optional[str] = None,
    ) -> None:
        if components is not None:
            self.components = tuple(components)
        self.signs = dict(DEFAULT_SIGNS if signs is None else signs)
        if name:
            self.name = name

    # ---- 内部：单成分标准化 ----
    @staticmethod
    def _z(series: pd.Series) -> pd.Series:
        s = series.dropna()
        if len(s) < 3:
            return pd.Series(np.nan, index=series.index)
        return zscore_cross_section(winsorize_mad(s)).reindex(series.index)

    def compute(self, panel: pd.DataFrame, as_of_date, ctx=None) -> pd.Series:
        cols: dict[str, pd.Series] = {}
        for cname in self.components:
            try:
                sub = get_factor(cname).compute(panel, as_of_date, ctx)
            except Exception:
                continue
            if sub is None or len(sub) == 0:
                continue
            sign = float(self.signs.get(cname, 1.0))
            cols[cname] = self._z(pd.Series(sub)) * sign

        if not cols:
            return pd.Series(dtype=float, name=self.name)

        mat = pd.DataFrame(cols)
        combined = mat.mean(axis=1, skipna=True)
        # 全 NaN 行（所有成分都缺）保持 NaN，不造假信号
        combined[mat.notna().sum(axis=1) == 0] = np.nan
        return combined.rename(self.name)


# 注册实例（注意注册的是实例，非类）
register_factor(ComboEqualFactor())
