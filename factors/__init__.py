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
from . import up_run_reversal  # noqa: F401  （f0029a 连涨占比短期反转）
from . import volume_cv_20d  # noqa: F401  （f0030a 20日成交量变异系数）
from . import amihud_illiquidity_20d  # noqa: F401  （f0031a 20日Amihud非流动性）
from . import vol_expansion_speed  # noqa: F401  （f0032a 波动率扩张速度）
from . import liquidity_improvement  # noqa: F401  （f0033a 流动性改善度）
from . import bottom_rebound  # noqa: F401  （f0034a 触底反弹信号）
from . import momentum_12_1  # noqa: F401  （f0035a 12-1 动量）
from . import upper_shadow  # noqa: F401  （f0036a 长上影线）
from . import reverse_cross_60  # noqa: F401  （f0037a 收益反向交叉次数）
from . import trend_smoothness_r2  # noqa: F401  （f0038a 趋势平滑度R²）
from . import max5_return  # noqa: F401  （f0039a 最大5日涨幅）
from . import min3_return  # noqa: F401  （f0040a 最低3日收益）
from . import lowprice_volume_spike  # noqa: F401  （f0041a 低位放量事件）
from . import dispersion_agent  # noqa: F401  （f0042a 分歧度代理）
from . import idiosyncratic_share  # noqa: F401  （f0043a 特异度占比）
