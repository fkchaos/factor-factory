# Changelog · 交付物发布说明

> 本文件记录 factor-factory 的**交付物**变更（因子 f-code / 信号 s-code 出包）。
> 格式参考 [Keep a Changelog](https://keepachangelog.com/)。`[Unreleased]` 段由每日推进器
> 在新交付时自动追加；主理人在交互会话整理发布时把 `[Unreleased]` 内容归档为带版本号的段落。
>
> 注：本厂**不设质量门槛**——出包只保证真实性与 PIT 合规（DSR/PBO 审计 + 前视防护 CI），
> 因子强弱由下游策略组在 JSON 层筛选决定，故本文件不评价 IC 好坏，只记录"交付了什么"。

## [Unreleased]

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
