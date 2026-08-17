"""时序信号线（Signal Division）包初始化。

与 factors 平行：factors 给"每只股票"打分（选股），signals 给"整个市场"判状态（仓位 overlay）。
详见 docs/PLAN_SIGNAL_LINE.md。

**导入即注册**（与 factors/__init__.py 同一纪律，2026-08-07 踩坑后补齐）：
`get_signal(name)` 依赖信号模块被 import 过（模块底部调用 register_signal 注册实例）。
scripts/build_signal_deliverable.py 只 import 了 signals.interface，导致
`get_signal("breadth_regime")` 抛 KeyError、s-code 交付包始终生不出来——与因子线
当年完全相同的坑。在包 __init__ 里统一 import 全部信号模块，从根上消除。

新增信号模块后，请在下面的 import 列表里补一行。
"""
from . import interface  # noqa: F401  （必须最先，其余模块依赖它）
from . import breadth_regime  # noqa: F401
from . import risk_appetite  # noqa: F401
from . import volatility_regime  # noqa: F401
