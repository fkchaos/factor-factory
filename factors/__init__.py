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
from . import overnight_ratio_60d  # noqa: F401  （f0044a 隔夜收益占比）
from . import overnight_intraday_decomp  # noqa: F401  （f0045a 隔夜-日内分解）
from . import idio_vol_ratio  # noqa: F401  （f0046a 特质波动率比率）
from . import return_deviation_mkt  # noqa: F401  （f0047a 相对市场收益偏离）
from . import overnight_gap_volexp_spread  # noqa: F401  （f0048a 隔夜跳空-波动扩张价差）
from . import reversal_60d  # noqa: F401  （f0049a 60日反转）
from . import asymmetric_5d_reversal  # noqa: F401  （f0050a 非对称5日反转）
from . import idio_tail_beta  # noqa: F401  （f0051a 特质收益下尾beta）
from . import dual_filter_momentum  # noqa: F401  （f0052a 双过滤动量）
from . import rejoicing_regret  # noqa: F401  （f0053a rejoicing-regret度）
from . import excess_return_ir  # noqa: F401  （f0054a 超额收益信息比率）
from . import price_volume_divergence  # noqa: F401  （f0055a 量价背离）
from . import intraday_battle_intensity  # noqa: F401  （f0056a 日内博弈激烈度）
from . import oversold_rebound_score  # noqa: F401  （f0057a 超跌反弹分）
from . import beta_qvol_interact  # noqa: F401  （f0058a beta×量波动交互）
from . import turnover_excess_group  # noqa: F401  （f0059a 组内换手异常超出幅度）
from . import fundamentals  # noqa: F401  （f0060a-f0072a 财报扩面 13 因子，Phase 0）
from . import forecast  # noqa: F401  （f0073a-f0075a 业绩预告因子，Phase 1）
from . import sue  # noqa: F401  （f0076a SUE 标准化未预期盈余，Phase 1）
from . import drif  # noqa: F401  （f0077a DRIF 收益分布形态因子）
from . import value_bm  # noqa: F401  （f0078a 价值 B/M 账面市值比）
from . import delta_roe  # noqa: F401  （f0079a ΔROE 盈利质量边际改善）
from . import amount_rank_ma_breakout  # noqa: F401  （f0080a 成交额前分位+均线突破）
from . import momentum_volume_shrink_pullback  # noqa: F401  （f0081a 动量向上+缩量回调）
from . import growth_convexity  # noqa: F401  （f0082a 双重增长凸性 营收同比×净利同比）
from . import beta_market_60d  # noqa: F401  （f0083a 市场 beta / BAB 异象）
