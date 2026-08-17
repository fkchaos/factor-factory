# TEST_LOG · 因子研发测试历史

> **纪律**：成功与失败都记录。失败因子进「因子墓地」，含假设 / 参数 / 失败原因 / 当时指标，防止团队在不同时间重复掉同一个坑（尤其前视 / 幸存者这类隐性陷阱）。
> 模板见 `research/templates/test_log_template.md`。

## 2026-08-04

### ✅ 通过 / 上线中
- **前视防护专项测试**（`tests/test_lookahead.py`）：4 项全过。验证框架能拦下「用全样本末日排名选股」「用全局统计量」两类前视偏差；合规因子正常通过。这是用户旧工程 v61b 头号隐患（`select_stocks` 忽略 `date` 用全样本末日排名）的系统性防护。
- **Phase 2 端到端冒烟测试**（`tests/test_pipeline.py`）：3 项全过。LocalProvider + OvernightIntradayFactor + WalkForwardEngine + Validator 端到端跑通；净值曲线非空无 NaN、因子 IC 有限、前视审计通过。全量 7 项 pytest 通过。
- **overnight_intraday 因子（首个真实因子）**：通过 `assert_no_lookahead` 审计；在合成随机数据（seed=7）上 RankIC≈-0.003（≈0，**符合随机数据预期——证明验证器没有凭空造出假显著 IC**）、回测 total_return 31.1% / Sharpe 0.67 / MaxDD -24.0%（随机噪声，非真实 alpha）。**真实数据接入后须重测确认有效性**。
- **ivol 因子（特质波动率，Phase 2 第二个因子）**：通过 `assert_no_lookahead` 审计 + 引擎冒烟（全量 9 项 pytest 通过）。合成随机数据（seed=7）上 RankIC≈0.0002 / ICIR≈0.001 / IC胜率0.488（≈0、≈50%，**随机数据预期，验证器无假显著**）；回测 total_return -19.8% / Sharpe -0.21 / MaxDD -58.7%（随机+成本，无 alpha）。**真实数据接入后须重测确认低波动溢价是否生效**。factor_plan 已预注册（`research/factor_plans/fp_ivol.md`）；overnight_intraday 的 factor_plan 亦补齐（`fp_overnight_intraday.md`）。
- **组合合成层（portfolio/combiner.py，Phase 2 收尾）**：CompositeFactor 实现 Factor 接口接入引擎；combine_factors 支持等权/ICIR 加权；simple_orthogonalize 提供去冗余。前视审计通过（全量 12 项 pytest）。合成数据(seed=7)上 ICIR 加权组合回测 total_return 38.5% / Sharpe 0.78 / MaxDD -17.3%（**随机噪声，非真实 alpha**；权重 overnight 0.936 / ivol 0.064，ICIR 加权正确反映合成数据上两因子 ICIR 差异）。**真实数据接入后须重测组合有效性**。

### 🪦 因子墓地（已淘汰 / 未通过）
- （暂无；Phase 2 为首轮真实因子，待真实数据验证后若有失败因子入此。）

- **共享选股层 + 影子账户（engine/selection.py + portfolio/shadow_account.py，Phase 3 方案 A）**：抽取 select_targets + execute_rebalance 供 WalkForwardEngine 与 ShadowAccount 共用（解耦 XDT，选股语义唯一可审计）；ShadowAccount 为纯回测影子（滚动调仓、不接券商），前视防护继承 Factor 契约 + CI 审计。重构后 WalkForwardEngine 行为不变（全量 23 项 pytest 通过，含新增 3 项 shadow 测试）。合成数据(seed=7)上影子账户：total_return -9.1% / Sharpe -0.094 / MaxDD -30.0% / 121 次调仓 / 平均单边换手 70.8%（**随机数据噪声换仓，换手率非真实参考**）；benchmark NaN（LocalProvider 无指数基准，真实数据接入后自动生效）。**真实数据接入后须重测**。
- **重构：WalkForwardEngine 改用共享选股层**（engine_impl.run）：内联选股/买卖逻辑替换为 select_targets + execute_rebalance，删除重复代码，选股语义与影子账户统一。回归测试全过，无行为变更。

### 🪦 因子墓地（已淘汰 / 未通过）
- （暂无；Phase 2 为首轮真实因子，待真实数据验证后若有失败因子入此。）

### 📌 观察 / 待办
- 真实数据源（Tushare / AkShare）尚未接入，当前验证基于 LocalProvider 合成数据，IC / 收益**不可作真实结论**。
- DSR / PBO 过拟合审计接口已预留，未实现（计划 P1）。
- 行业 / 市值中性化在 Validator 中接口预留，未启用（需真实行业 / 市值数据）。
- 涨跌停封板为近似处理（t+1 开盘相对 t 收盘 ±9.5%），真实源接入后应改用交易所涨跌停价字段。
- **方案 A（纯回测影子）已完成**；方案 B（接 QMT / PTrade 模拟盘）待外部券商环境就绪后再扩展，HANDOFF 已标注待决策。

## 🔬 真实数据重测 2026-08-04 (universe=SZ)

**真实数据重测（Tushare，运行日 2026-08-04，universe=SZ）**

- overnight_intraday: RankIC=nan, ICIR=nan, IC胜率=nan, n=0, 衰减(1/5/10/20d)={'ic_5d': nan, 'ic_10d': nan, 'ic_20d': nan}
- ivol: RankIC=nan, ICIR=nan, IC胜率=nan, n=0, 衰减(1/5/10/20d)={'ic_5d': nan, 'ic_10d': nan, 'ic_20d': nan}
- 组合(combine='icir'): {'error': 'insufficient data'}

> ⚠️ 真实 alpha 须再经 DSR/PBO 过拟合审计（Phase 3）方可纳入生产组合。


## 🧱 数据契约层 2026-08-04（Provider 可插拔 + 单位/格式防火墙）

**背景**：用户要求接口-Provider 可插拔架构，且单位/格式必须在接口层明确规定，避免切源结果漂移。

**新增**：
- `data/contract.py`：PANEL_FIELDS 单位表 + normalize_code + canonicalize_panel + validate_panel + validate_returns（契约见 docs/DATA_CONTRACT.md）
- `data/interface.py`：Protocol 补 get_index_returns + 契约 docstring
- `tests/test_provider_contract.py`：19 项契约测试（无网络依赖）
- `docs/DATA_CONTRACT.md` + ARCHITECTURE.md §3.1

**修复（探针抓到的真 bug）**：
1. `self._pro.pro_bar` 不存在（pro_bar 是模块级函数）→ 改为 `self._ts.pro_bar`——这是 SZ 后台任务两次"静默死亡"的真正根因
2. `daily_basic` 免费 token 限频 1次/分钟 → 加熔断闩（首次超限整轮跳过，turnover/market_cap=NaN，符合契约"缺失用 NaN"）
3. `adj_factor` 免费 token 限频 **1次/小时** → pro_bar 去掉 adj 参数，Tushare 免费档降级为**不复权(raw)** 价格（升级积分后可切 qfq）
4. 旧实现 `df["turnover"].fillna(0.0)` 违反契约 0 占位禁令 → 改 NaN
5. AkShare 旧实现：代码无后缀、market_cap 用 0 占位、volume 手当股 → 全部修正

**结果**：全量 46 项 pytest 通过（27 旧 + 19 新）。

**进行中**：SZ 真实重测后台运行（task Ro67UG，日志 .cache/real_research.log）——此前三次 n=0 均因上述 bug 中断；本次修复后预期产出真实 RankIC。

### ✅ 跨源一致性核对（2026-08-04，契约实证）
Tushare(raw) vs AkShare 新浪源(raw)，2024-01-02~06-28：
- 000001.SZ / 000002.SZ 各 **117 个共同交易日**
- close / volume / amount **最大相对差全部 0.0000%**（单位换算手→股×100、千元→元×1000 后完全一致）
- 结论：**数据契约（单位/格式接口层强制）在真实数据源间生效，切源不产生结果偏差**


## 🔬 真实数据重测 · 首轮有效结果 2026-08-04 (universe=SZ, 300只)

**单因子（2020-01-01 起，约 1600 交易日，SZ 300 只，raw 价格，turnover/market_cap=NaN）**：
- overnight_intraday: **RankIC=-0.0374, ICIR=-0.2717, IC胜率=0.37**, 衰减20d=-0.030
  → 方向为负；因子卡定义的做多方向若为"隔夜-日内"，则符号约定需复核（真实数据为负信号）
- ivol: **RankIC=+0.0537, ICIR=+0.3818, IC胜率=0.67**, 衰减20d=+0.109
  → **低波动异象在真实数据上站住**：ICIR 0.38、胜率 67%、20 日衰减仍为正（信号有持续性）

**组合回测（2023-01-01 起 616 交易日，top_n=10，ICIR 加权，二次冲击成本+T+1）**：
- **total_return=+24.2%, Sharpe=0.425, MaxDD=-22.2%**

> ⚠️ 前提与局限（务必阅读）：
> 1. Tushare 免费档价格为**不复权(raw)**，除权除息日有毛刺（预处理 MAD 剪枝缓解）；
> 2. turnover/market_cap 因 daily_basic 免费限频为 **NaN**（未做行业/市值中性化）；
> 3. 股票池为**当前** SZ 列表（非严格 PIT，有幸存者偏差）；
> 4. 组合回测窗口 2023 起、top_n=10（集中度高）；沙箱内存限制下无法跑全历史全池。
> 5. **真实 alpha 仍须过 DSR/PBO 过拟合审计（Phase 3）方可纳入生产组合。**


## 🔬 真实数据重测 2026-08-05 (universe=SZ)

**真实数据重测（Tushare，运行日 2026-08-05，universe=SZ）**

- overnight_intraday: RankIC=nan, ICIR=nan, IC胜率=nan, n=0, 衰减(1/5/10/20d)={'ic_5d': nan, 'ic_10d': nan, 'ic_20d': nan}
- ivol: RankIC=nan, ICIR=nan, IC胜率=nan, n=0, 衰减(1/5/10/20d)={'ic_5d': nan, 'ic_10d': nan, 'ic_20d': nan}
- 组合(combine='icir'): {'error': 'insufficient data'}

> ⚠️ 真实 alpha 须再经 DSR/PBO 过拟合审计（Phase 3）方可纳入生产组合。


## 🔬 真实数据重测 2026-08-05 (universe=SZ)

**真实数据重测（Tushare，运行日 2026-08-05，universe=SZ）**

- overnight_intraday: RankIC=-0.0425, ICIR=-0.3239, IC胜率=0.36, n=2786, 衰减(1/5/10/20d)={'ic_5d': -0.027745004932929727, 'ic_10d': -0.025623033672055727, 'ic_20d': -0.026281158628218712}
- ivol: RankIC=0.0539, ICIR=0.3932, IC胜率=0.67, n=1078, 衰减(1/5/10/20d)={'ic_5d': 0.07507874515660763, 'ic_10d': 0.07841753032608917, 'ic_20d': 0.10087367671391798}
- 组合(combine='icir'): {'total_return': -1.0008785289933277, 'sharpe': -0.05563525243643722, 'max_drawdown': -1.0428093057853067, 'n_days': 6190}

> ⚠️ 真实 alpha 须再经 DSR/PBO 过拟合审计（Phase 3）方可纳入生产组合。


## 🔬 真实数据重测 2026-08-05 (universe=sz50)

**真实数据重测（baostock，运行日 2026-08-05，universe=sz50）**

- overnight_intraday: RankIC=-0.0186, ICIR=-0.0697, IC胜率=0.47, n=6440, 衰减(1/5/10/20d)={'ic_5d': -0.020543421994454542, 'ic_10d': -0.011321706212079743, 'ic_20d': -0.00479299937066809}
- ivol: RankIC=0.0161, ICIR=0.0554, IC胜率=0.52, n=6215, 衰减(1/5/10/20d)={'ic_5d': 0.014889176261826734, 'ic_10d': 0.011094985204971921, 'ic_20d': 0.015028108031268967}
- 组合(combine='icir'): {'total_return': 11.148996414107755, 'sharpe': 0.6925517448493617, 'max_drawdown': -0.48195766609872315, 'n_days': 6190}

> ⚠️ 真实 alpha 须再经 DSR/PBO 过拟合审计（Phase 3）方可纳入生产组合。


## 🔬 真实数据重测 2026-08-05 (universe=sz50)

**真实数据重测（baostock，运行日 2026-08-05，universe=sz50）**

- overnight_intraday: RankIC=-0.0331, ICIR=-0.1285, IC胜率=0.46, n=624, 衰减(1/5/10/20d)={'ic_5d': -0.0036844816432517625, 'ic_10d': -0.003184672297156997, 'ic_20d': -0.0026675177698011485}
- ivol: RankIC=0.0297, ICIR=0.0957, IC胜率=0.55, n=601, 衰减(1/5/10/20d)={'ic_5d': 0.023688590493065455, 'ic_10d': 0.02315419126402336, 'ic_20d': 0.029306251845205907}
- 组合(combine='icir'): {'total_return': 0.2130278800124863, 'sharpe': 0.7024278186660241, 'max_drawdown': -0.2003689196845343, 'n_days': 374}

> ⚠️ 真实 alpha 须再经 DSR/PBO 过拟合审计（Phase 3）方可纳入生产组合。


## 🔬 真实数据重测 2026-08-05 (universe=sz50)

**真实数据重测（baostock，运行日 2026-08-05，universe=sz50）**

- overnight_intraday: RankIC=0.0331, ICIR=0.1285, IC胜率=0.54, n=624, 衰减(1/5/10/20d)={'ic_5d': 0.0036844816432517625, 'ic_10d': 0.003184672297156997, 'ic_20d': 0.0026675177698011485}, DSR=1.0, PBO=0.0
- ivol: RankIC=0.0297, ICIR=0.0957, IC胜率=0.55, n=601, 衰减(1/5/10/20d)={'ic_5d': 0.023688590493065455, 'ic_10d': 0.02315419126402336, 'ic_20d': 0.029306251845205907}, DSR=1.0, PBO=0.0
- 组合(combine='icir'): {'total_return': 0.2757337813180101, 'sharpe': 1.0231535677061978, 'max_drawdown': -0.15097904362531517, 'n_days': 374}

> ⚠️ DSR/PBO 门禁：DSR≥0.95 且 PBO≤0.30 方可通过（见 validate/overfit_audit.py）。


## 🔬 真实数据重测 2026-08-05 (universe=sz50)

**真实数据重测（baostock，运行日 2026-08-05，universe=sz50）**

- overnight_intraday: RankIC=0.0167, ICIR=0.1227, IC胜率=0.54, n=624, 衰减(1/5/10/20d)={'ic_5d': 0.011090222484477769, 'ic_10d': 0.0021702942480604503, 'ic_20d': 0.006995251261256388}, DSR=1.0, PBO=0.0
- ivol: RankIC=0.0184, ICIR=0.1260, IC胜率=0.55, n=601, 衰减(1/5/10/20d)={'ic_5d': 0.018980200199468066, 'ic_10d': 0.01470442104211835, 'ic_20d': 0.008442233843713037}, DSR=1.0, PBO=0.0
- 组合(combine='icir'): {'total_return': 0.2558451519941045, 'sharpe': 1.0068247618556176, 'max_drawdown': -0.15055410549406834, 'n_days': 374}

> ⚠️ DSR/PBO 门禁：DSR≥0.95 且 PBO≤0.30 方可通过（见 validate/overfit_audit.py）。

