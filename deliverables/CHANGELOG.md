# Changelog · 交付物发布说明

> 本文件记录 factor-factory 的**交付物**变更（因子 f-code / 信号 s-code 出包）。
> 格式参考 [Keep a Changelog](https://keepachangelog.com/)。`[Unreleased]` 段由每日推进器
> 在新交付时自动追加；主理人在交互会话整理发布时把 `[Unreleased]` 内容归档为带版本号的段落。
>
> 注：本厂**不设质量门槛**——出包只保证真实性与 PIT 合规（DSR/PBO 审计 + 前视防护 CI），
> 因子强弱由下游策略组在 JSON 层筛选决定，故本文件不评价 IC 好坏，只记录"交付了什么"。

## [Unreleased]

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
