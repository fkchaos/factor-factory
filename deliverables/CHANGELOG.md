# Changelog · 交付物发布说明

> 本文件记录 factor-factory 的**交付物**变更（因子 f-code / 信号 s-code 出包）。
> 格式参考 [Keep a Changelog](https://keepachangelog.com/)。`[Unreleased]` 段由每日推进器
> 在新交付时自动追加；主理人在交互会话整理发布时把 `[Unreleased]` 内容归档为带版本号的段落。
>
> 注：本厂**不设质量门槛**——出包只保证真实性与 PIT 合规（DSR/PBO 审计 + 前视防护 CI），
> 因子强弱由下游策略组在 JSON 层筛选决定，故本文件不评价 IC 好坏，只记录"交付了什么"。

## [Unreleased]

### 因子（f0076a · Phase 1 第二小批 · 盈余惊喜）
- `2026-09-09 | factor | f0076a | SUE标准化未预期盈余（sue） | deliverables/factors/f0076a/`（hs300 RankIC +0.0055 / hs800 **+0.0082** ICIR 0.11 胜率 56.0%；财报线迄今**强度第二 + 独立性最好**的因子。季节性随机游走预期（Q_t 预期=Q_{t−4}），无需卖方一致预期 → 覆盖率 98%，绕开业绩预告仅 28–36% 的死穴。与 f0072a 净利同比 ρ=**0.50** <0.7 冗余门槛 → 标准化确带来增量，非重复品；全局矩阵中未出现在任何 |ρ|≥0.7 配对，通过冗余前置闸门）

### 因子（f0060a–f0075a 批量交付 · Phase 0 财报扩面 + Phase 1 第一小批 · 双池 hs300/hs800）
> 本批全部为**非 OHLCV 新数据源**（PIT 财报 + 东财业绩预告），用于破解外部审核"全 OHLCV 同质"批评。
> 强度如实偏弱（IC 中位 ~0.0035），**价值在正交性**（财报 vs 价量中位 |ρ|=0.016，价量内部基线 0.053），勿当高 alpha 用。
- `2026-09-09 | factor | f0060a | ROE净资产收益率（roe） | deliverables/factors/f0060a/`（hs300 +0.0039 / hs800 +0.0044）
- `2026-09-09 | factor | f0061a | ROA总资产收益率（roa） | deliverables/factors/f0061a/`（hs300 +0.0050 / hs800 +0.0054；与 f0060a ρ=0.86 高冗余）
- `2026-09-09 | factor | f0062a | 毛利率（gross_margin） | deliverables/factors/f0062a/`（hs300 +0.0035 / hs800 **−0.0013**，双池符号翻转但幅度均 <0.005 属噪声，不构成方向性结论）
- `2026-09-09 | factor | f0063a | 净利率（net_margin） | deliverables/factors/f0063a/`（hs300 +0.0043 / hs800 +0.0036；与 f0065a ρ=0.98 近重复）
- `2026-09-09 | factor | f0064a | 资产周转率（asset_turnover） | deliverables/factors/f0064a/`（hs300 +0.0043 / hs800 +0.0052）
- `2026-09-09 | factor | f0065a | 营业利润率（operate_profit_margin） | deliverables/factors/f0065a/`（hs300 +0.0036 / hs800 +0.0031）
- `2026-09-09 | factor | f0066a | 财务杠杆（financial_leverage） | deliverables/factors/f0066a/`（hs300 −0.0029 / hs800 −0.0013）
- `2026-09-09 | factor | f0067a | 盈利现金保障（cash_coverage） | deliverables/factors/f0067a/`（hs300 +0.0049 / hs800 +0.0018；全局最独立因子之一 mean|ρ|=0.042）
- `2026-09-09 | factor | f0068a | 应计（accrual） | deliverables/factors/f0068a/`（hs300 −0.0062 / hs800 −0.0026；方向与"高应计→低收益"经典事实一致）
- `2026-09-09 | factor | f0069a | 扣非净利占比（deduct_ratio） | deliverables/factors/f0069a/`（hs300 −0.0009 / hs800 −0.0029；全局最独立因子之一 mean|ρ|=0.037）
- `2026-09-09 | factor | f0070a | EP盈利收益率（ep） | deliverables/factors/f0070a/`（hs300 +0.0083 / hs800 **+0.0139** ICIR 0.12；本批最强，大池优于小池）
- `2026-09-09 | factor | f0071a | 营收同比（revenue_yoy） | deliverables/factors/f0071a/`（hs300 −0.0010 / hs800 +0.0029，双池符号翻转、幅度均噪声级）
- `2026-09-09 | factor | f0072a | 净利同比（netprofit_yoy） | deliverables/factors/f0072a/`（hs300 +0.0049 / hs800 +0.0066；未标准化版本，f0076a 为其标准化升级）
- `2026-09-09 | factor | f0073a | 预告净利同比（forecast_yoy） | deliverables/factors/f0073a/`（hs300 +0.0004 / hs800 +0.0028；覆盖率 28–36% 约束；与 f0074a ρ=0.75 冗余）
- `2026-09-09 | factor | f0074a | 预告类型分档（forecast_kind） | deliverables/factors/f0074a/`（hs300 +0.0027 / hs800 +0.0028；预增+3…预减−3 手工分档，无统计依据）
- `2026-09-09 | factor | f0075a | 前瞻EP（forecast_ep） | deliverables/factors/f0075a/`（hs300 +0.0039 / hs800 +0.0070；⚠️ 与 f0070a 历史EP ρ=**0.81** 高冗余，增量有限）

### 信号（s0004x · 信号线自 08-12 后首个新包，第四个正交视角）
- `2026-09-08 | signal | s0004x | 难做指数Regime（difficulty_regime） | deliverables/signals/s0004x/`
  （hs800 / 2020 起 1597 日；exec_lag=1 钢印；叠加 Sharpe 0.77→0.05 **改善 −0.721**、最大回撤 −27.09%→−35.36% **恶化 8.27pct**、命中率价差 −3.7% → 按策略组 §7.2 判 **refuted**，且是四信号中唯一"收益与回撤两项都变差"的；与 s0001x/s0002x/s0003x 状态一致率 43.5% / 48.9% / 60.8% 均 <85%，视角独立）
  ⚠️ 消费提示：本信号量的是**因子可提取性**（该不该放开因子暴露），不是市场涨跌；实测结果恰好证明把它当择时器用会亏——这正是卡片 caveat ③ 事前预警的误用方式。

### 因子（f0056a–f0059a 批量交付 · 纯价量 drain 第二批）
- `2026-09-08 | factor | f0056a | 日内博弈激烈度（intraday_battle_intensity） | deliverables/factors/f0056a/`（hs300 RankIC −0.0004 / hs800 −0.0023；方向与假设"负相关"一致但近乎无效）
- `2026-09-08 | factor | f0057a | 超跌反弹分（oversold_rebound_score） | deliverables/factors/f0057a/`（hs300 −0.0006 / hs800 +0.0021；z×z 双负象限混合为构造固有缺陷，如实保留未私改）
- `2026-09-08 | factor | f0058a | beta量波动交互（beta_qvol_interact） | deliverables/factors/f0058a/`（hs300 −0.0093 / hs800 −0.0115；与假设方向**相反**，该 arXiv 模型在 A 股日频口径下被证伪，刻意不反转符号）
- `2026-09-08 | factor | f0059a | 组内换手异常超出幅度（turnover_excess_group） | deliverables/factors/f0059a/`（hs300 −0.0103 / hs800 −0.0154；与假设方向**相反**，反支持 A 股"高换手→低收益"经典事实。⚠️ 行业维度降级：面板无行业列，仅按 PIT 流通市值三分组，补行业列后应作 f0059b 重出而非原地改口径）

### 因子（f0050a–f0055a 批量交付 · 纯价量 drain）
- `2026-09-07 | factor | f0050a | 非对称5日反转（asymmetric_5d_reversal） | deliverables/factors/f0050a/`（hs300 RankIC +0.0170 / hs800 +0.0193）
- `2026-09-07 | factor | f0051a | 特质收益下尾beta（idio_tail_beta） | deliverables/factors/f0051a/`（hs300 +0.0020 / hs800 -0.0005）
- `2026-09-07 | factor | f0052a | 双过滤动量（dual_filter_momentum） | deliverables/factors/f0052a/`（hs300 -0.0057 / hs800 -0.0094）
- `2026-09-07 | factor | f0053a | rejoicing-regret度（rejoicing_regret） | deliverables/factors/f0053a/`（hs300 +0.0115 / hs800 +0.0172）
- `2026-09-07 | factor | f0054a | 超额收益信息比率（excess_return_ir） | deliverables/factors/f0054a/`（hs300 -0.0083 / hs800 -0.0135）
- `2026-09-07 | factor | f0055a | 量价背离（price_volume_divergence） | deliverables/factors/f0055a/`（hs300 +0.0019 / hs800 +0.0003）

### 文档（开源就绪）
- 新增 `docs/DELIVERABLES.md`：**交付物查阅地图**——面向外部用户/下游策略组，逐一给出因子/信号/矩阵/导出 JSON/CHANGELOG 的精确路径、内容、消费方式，弥补 README/ARCHITECTURE 仅类别级说明的空白
- README 文档导航新增 `DELIVERABLES` 行；`生产线 vs 交付物` 注释与 USER_GUIDE §4 交叉引用该地图

### 仓库（开源发布）
- 首次推送到公开仓 `github.com/fkchaos/factor-factory`：MIT 许可、六层解耦架构、双线（因子 f-code / 信号 s-code）、PIT 合规、DSR/PBO 过拟合审计、CHANGELOG 发布、单文件美观看板

### 因子（f0006a–f0010a 批量交付）
- `2026-08-17 | factor | f0006a | 动量20日（momentum_20） | deliverables/factors/f0006a/`（反向：动量赢家未来偏弱；RankIC -0.0077，审计通过即出包）
- `2026-08-17 | factor | f0007a | 反转5日（reversal_5） | deliverables/factors/f0007a/`
- `2026-08-17 | factor | f0008a | 隔夜跳空缺口（overnight_gap） | deliverables/factors/f0008a/`
- `2026-08-17 | factor | f0009a | 涨停封板强度（limit_up_seal） | deliverables/factors/f0009a/`
- `2026-08-17 | factor | f0010a | 市值对数（size_log_mcap） | deliverables/factors/f0010a/`

### 因子（f0011a–f0026a 补录 · 批量价量 + 财报类 + 研究中因子）
- `2026-08-20 | factor | f0011a | 120日平均换手率（avg_turnover_120d） | deliverables/factors/f0011a/`
- `2026-08-20 | factor | f0012a | 10日平均换手率（avg_turnover_10d） | deliverables/factors/f0012a/`
- `2026-08-20 | factor | f0013a | 240日平均换手率（avg_turnover_240d） | deliverables/factors/f0013a/`
- `2026-08-20 | factor | f0016a | 20日成交金额标准差（amount_std_20d） | deliverables/factors/f0016a/`
- `2026-08-20 | factor | f0017a | 5日平均换手率（avg_turnover_5d） | deliverables/factors/f0017a/`
- `2026-08-20 | factor | f0018a | 5日EMA（ema_5d） | deliverables/factors/f0018a/`
- `2026-08-20 | factor | f0019a | 10日EMA（ema_12d） | deliverables/factors/f0019a/`
- `2026-08-20 | factor | f0020a | 12日EMA（ema_12d） | deliverables/factors/f0020a/`
- `2026-08-20 | factor | f0021a | 120日EMA（ema_120d） | deliverables/factors/f0021a/`
- `2026-08-20 | factor | f0022a | 5日MA（ma_5d） | deliverables/factors/f0022a/`
- `2026-08-20 | factor | f0023a | 20日成交金额MA（amount_ma_20d） | deliverables/factors/f0023a/`
- `2026-08-20 | factor | f0024a | 20日资金流量（money_flow_ma_20d） | deliverables/factors/f0024a/`
- `2026-08-20 | factor | f0025a | 布林上轨20日（bollinger_upper_20d） | deliverables/factors/f0025a/`
- `2026-08-24 | factor | f0014a | 存货周转天数（inventory_turnover_days） | deliverables/factors/f0014a/`（财报类·日频RankIC≈0(-0.0008)；迅投看板IC=0.83为同期相关口径非RankIC，不可比·高IC低超额陷阱实锤）
- `2026-08-24 | factor | f0015a | 应收账款周转天数（ar_turnover_days） | deliverables/factors/f0015a/`（财报类·日频RankIC≈0(+0.0000)；同口径提示）
- `2026-09-01 | factor | f0026a | 量能扩张速度（volume_expansion_speed） | deliverables/factors/f0026a/`（原研究中因子·离线cache hit出包验证·RankIC -0.0057）
- `2026-09-01 | factor | f0027a | 近20日已实现偏度（realized_skew_20d） | deliverables/factors/f0027a/`（✅本轮(09-02)确认出包完成·i20260827-001 翻 validated·博彩偏好异象）

### 因子（f0028a · 2026-09-02 drain 完成）
- `2026-09-02 | factor | f0028a | 长下影线（lower_shadow） | deliverables/factors/f0028a/`（已确认出包成功·灵感 i20260806-010→validated·纯OHLC·RankIC=-0.0141 弱因子照常交付）

### 仓库（口径修复 · 2026-09-02）
- 回填 15 个已交付因子模块的 `fcode` 类属性（此前漏写，导致看板长期误计"研究中=17"）：amount_std_20d→f0016a、avg_turnover_10/120/240/5d→f0012/11/13/17a、ema_5/10/12/120d→f0018/19/20/21a、ma_5d→f0022a、amount_ma_20d→f0023a、money_flow_ma_20d→f0024a、bollinger_upper_20d→f0025a、chip_cost_distance→f0004a、turnover_days（Inventory/AR 两类）→f0014a/f0015a。看板"研究中"由 17 降至 1（剩 1 = ML 特征占位 `feature_factory.log_mktcap`，故意不出包、pending_handoff 已登记）。

### 因子（f0029a–f0037a 批量 drain · 2026-09-03 ~ 2026-09-04）
- `2026-09-03 | factor | f0029a | 连涨占比短期反转（up_run_reversal） | deliverables/factors/f0029a/`（RankIC +0.0146；n=753）
- `2026-09-03 | factor | f0030a | 20日成交量变异系数（volume_cv_20d） | deliverables/factors/f0030a/`（RankIC -0.0073；ICIR -0.104）
- `2026-09-03 | factor | f0031a | 20日Amihud非流动性（amihud_illiquidity_20d） | deliverables/factors/f0031a/`（RankIC +0.0097；ICIR +0.128）
- `2026-09-04 | factor | f0032a | 波动率扩张速度（vol_expansion_speed） | deliverables/factors/f0032a/`（RankIC +0.0004；近 0）
- `2026-09-04 | factor | f0033a | 流动性改善度（liquidity_improvement） | deliverables/factors/f0033a/`（RankIC +0.0060；ICIR +0.080）
- `2026-09-04 | factor | f0034a | 触底反弹信号（bottom_rebound） | deliverables/factors/f0034a/`（RankIC -0.0333；ICIR -0.110）
- `2026-09-04 | factor | f0035a | 12-1动量（momentum_12_1） | deliverables/factors/f0035a/`（RankIC +0.0070；ICIR +0.05；灵感 i20260820-039→validated）
- `2026-09-04 | factor | f0036a | 长上影线（upper_shadow） | deliverables/factors/f0036a/`（RankIC +0.0063；ICIR +0.08；灵感 i20260820-042→validated）
- `2026-09-04 | factor | f0037a | 收益反向交叉次数（reverse_cross_60） | deliverables/factors/f0037a/`（RankIC -0.0028；ICIR -0.03；灵感 i20260903-004→validated）

> 注：f0029a–f0034a 为 09-03/09-04 早前推进器出包，本轮（09-04 晚）补录 CHANGELOG 以保证权威；f0035a–f0037a 为本轮 drain。全部因子均经 DSR/PBO 审计 + 前视防护，不设质量门槛，强弱交策略组筛选。

### 因子（f0038a–f0043a 批量 drain · 2026-09-05）
- `2026-09-05 | factor | f0038a | 趋势平滑度R²（trend_smoothness_r2） | deliverables/factors/f0038a/`（RankIC +0.0026；ICIR +0.032；灵感 i20260805-008→validated）
- `2026-09-05 | factor | f0039a | 最大5日涨幅（max5_return） | deliverables/factors/f0039a/`（RankIC -0.0023；ICIR -0.034；灵感 i20260805-009→validated）
- `2026-09-05 | factor | f0040a | 最低3日收益（min3_return） | deliverables/factors/f0040a/`（RankIC -0.0020；ICIR -0.031；灵感 i20260806-001→validated）
- `2026-09-05 | factor | f0041a | 低位放量事件（lowprice_volume_spike） | deliverables/factors/f0041a/`（RankIC -0.0131；ICIR -0.085；灵感 i20260820-036→validated）
- `2026-09-05 | factor | f0042a | 分歧度代理（dispersion_agent） | deliverables/factors/f0042a/`（RankIC -0.0003；ICIR -0.005；灵感 i20260805-006→validated）
- `2026-09-05 | factor | f0043a | 特异度占比（idiosyncratic_share） | deliverables/factors/f0043a/`（RankIC +0.0004；ICIR +0.007；灵感 i20260820-037→validated）

> 注：本批 6 个纯价量因子经 pkl 缓存预填加速出包（绕过原 O(T²) harness 瓶颈）；全部 DSR/PBO 审计 + 前视防护通过，IC 普遍偏弱但真实，强弱交策略组筛选。灵感池 27→21。

### 因子（f0044a–f0049a 批量 drain · 2026-09-06）
- `2026-09-06 | factor | f0044a | 隔夜收益占比（overnight_ratio_60d） | deliverables/factors/f0044a/`（RankIC +0.0032 / +0.0035；60日隔夜累计/总累计；灵感 i20260805-004→validated）
- `2026-09-06 | factor | f0045a | 隔夜-日内分解（overnight_intraday_decomp） | deliverables/factors/f0045a/`（RankIC +0.0134 / +0.0193；20日隔夜累计−日内累计；灵感 i20260805-003→validated）
- `2026-09-06 | factor | f0046a | 特质波动率比率（idio_vol_ratio） | deliverables/factors/f0046a/`（RankIC -0.0053 / -0.0097；20日特质波动/120日特质波动；灵感 i20260820-038→validated）
- `2026-09-06 | factor | f0047a | 相对市场收益偏离（return_deviation_mkt） | deliverables/factors/f0047a/`（RankIC -0.0172 / -0.0196；5日累计(r_i−r_mkt)；灵感 i20260824-002→validated）
- `2026-09-06 | factor | f0048a | 隔夜跳空-波动扩张价差（overnight_gap_volexp_spread） | deliverables/factors/f0048a/`（RankIC +0.0068 / +0.0097；跳空z−振幅扩张z；灵感 i20260820-035→validated）
- `2026-09-06 | factor | f0049a | 60日反转（reversal_60d） | deliverables/factors/f0049a/`（RankIC +0.0055 / +0.0099；−(close[t]/close[t-60]−1)；灵感 i20260806-008→validated）

> 注：本批 6 个纯价量因子经 panel 磁盘缓存 + `compute_panel` 快路径（O(N) 向量化，单包 ~4min，原逐日 O(T²) 瓶颈已根治）出包；全部 DSR/PBO 审计 + 前视防护通过，IC 普遍偏弱但真实，强弱交策略组筛选。灵感池 21→15。

## [0.1.0] - 2026-08-17

初始交付批次（研究/模拟盘，非实盘）。

### 因子线（横截面 f-code，选股打分）
- `f0001a` 隔夜-日内反转（`overnight_intraday`）— 隔夜收益 vs 日内收益反转结构
- `f0002a` 特质波动率 / 低波溢价（`ivol`）— 特质波动率越低越好
- `f0003a` 等权组合（隔夜反转 + 低波）（`combo`）— 两因子等权合成
- `f0004a` 筹码成本偏离（`chip_cost_distance`）— 锚定 VWAP 持仓成本偏离
- `f0005a` 量能扩张速度（`volume_expansion_speed`）— 近20日均量 / 近120日均量

### 信号线（时序 s-code，市场状态 overlay）
- `s0001x` 广度 Regime（`breadth_regime`）— 上涨/下跌家数结构
- `s0002x` 风险偏好 Regime（`risk_appetite_regime`）— 大小盘资金流向
- `s0003x` 波动率 Regime（`volatility_regime`）— 波动收缩/扩张（对数比值，阈值免拟合）

### 交付物形态
- `deliverables/factors/<fcode>/` 含 `card.md`（说明 + 相关性 + 回测）、`manifest.yaml`
- `deliverables/signals/<scode>/` 含 `card.md`（状态定义 + 叠加改善）、`manifest.yaml`，标注 `exec_lag=1`
- `deliverables/universe_matrix/` 六池 RankIC/ICIR/DSR 矩阵
- `deliverables/strategy_export/` 聚合 JSON（stock_factors / timing_signals / risk_params 占位）
