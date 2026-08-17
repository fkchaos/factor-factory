"""因子包。

**导入即注册**：`get_factor(name)` 依赖因子模块被 import 过（模块底部调用
register_factor 注册实例）。历史上 scripts/build_deliverable.py 只 import 了
factors.interface，导致 get_factor("ivol") 抛 KeyError、交付包始终生不出来。
在包 __init__ 里统一 import 全部因子模块，从根上消除这类"忘记 import"的坑。

新增因子模块后，请在下面的 import 列表里补一行。
"""
from . import interface  # noqa: F401  （必须最先，其余模块依赖它）
from . import zoo_basics  # noqa: F401
from . import ivol  # noqa: F401
from . import overnight_intraday  # noqa: F401
from . import microstructure  # noqa: F401
from . import combo  # noqa: F401
from . import chip_cost_distance  # noqa: F401
from . import volume_expansion_speed  # noqa: F401
