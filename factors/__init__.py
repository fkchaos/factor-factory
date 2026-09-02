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
from . import avg_turnover_120d  # noqa: F401
from . import avg_turnover_10d  # noqa: F401
from . import avg_turnover_240d  # noqa: F401
from . import amount_std_20d  # noqa: F401
from . import avg_turnover_5d  # noqa: F401
from . import ema_5d  # noqa: F401
from . import ema_10d  # noqa: F401
from . import ema_12d  # noqa: F401
from . import ema_120d  # noqa: F401
from . import ma_5d  # noqa: F401
from . import amount_ma_20d  # noqa: F401
from . import money_flow_ma_20d  # noqa: F401
from . import bollinger_upper_20d  # noqa: F401
from . import turnover_days  # noqa: F401  （f0014a 存货周转天数 / f0015a 应收账款周转天数）
from . import realized_skew_20d  # noqa: F401  （f0027a 近20日已实现偏度）
from . import lower_shadow  # noqa: F401  （f0028a 长下影线）
