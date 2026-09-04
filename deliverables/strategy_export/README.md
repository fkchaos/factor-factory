# 策略组阶段 0 输入包（factor-factory → a-share-quant-sim）

> 生成时间：2026-09-04 21:58｜生成脚本：`scripts/export_to_strategy_json.py`（幂等，可反复重跑）
> 对齐依据：`docs/REQUIREMENTS_ALIGNMENT-2026-08-07.md` v2 §3 / §5.1 / §5.2 / §6

## 文件

| 文件 | 内容 | 条目数 |
|---|---|---|
| `stock_factors.json` | 横截面选股因子（f-code） | 37 |
| `timing_signals.json` | 市场级择时信号（s-code） | 3 |
| `risk_params.json` | **占位**：风控参数不在我们交付范围 | 0 |

直接放到你们 `alpha-research/inputs/` 下即可被阶段 0 消费，`source` 均已标 `external`。

## 🔴 择时信号必读：exec_lag 钢印

exec_lag=1（T 日收盘后才算得出 T 日状态，最早 T+1 建仓）。⚠️ 禁止用同期收益 ret[T] 评估本信号，必须 state.shift(1)；同期口径对广度类信号近似同义反复，实测可把 Sharpe 从真值撑高一大截。

每条 timing 记录顶层都带 `exec_lag` 与 `exec_lag_warning` 两个字段。
`backtest_sharpe` 取的是 **已 shift(1) 的 overlay Sharpe**，不是同期口径。
包内 `card.md` 的 `*_contemp` 列仅供诊断（判断信号对当日信息的依赖度），**不可用于评估**。

## 字段说明

- 对方 schema 字段一律放**顶层**，可直接解析。
- 我方增量统一收在 `_factory_extra` 下（多池 IC 表、§7.2 判决徽章、DSR/PBO、
  中性化/PIT 状态、复现命令、TODO 清单），忽略它不影响你们的解析。
- `regime_dependency` / `decay_status` 目前一律 `"unknown"`——不是遗漏，是我们
  拒绝在没算出来之前填数字，对应补丁见各条目 `_factory_extra.todo`。

## 判决随池翻转（重要）

选股因子的 §7.2 判决**是池子的函数**：同一因子在 sz50 可能"证伪"、在 zz1000 却"有效"。
我们不做内部门槛筛选，把**多池原始 IC 表全给**（`_factory_extra.metrics_by_pool`，
每池附 `gate_7_2_verdict`），主场池选择权交给你们的域判断。
顶层 `ic_mean` / `ir` 取的是 `_factory_extra.home_pool`（|ICIR| 最大池）的值。

## 我们不交付什么

止损 / 止盈 / 持仓天数上限 / 最大仓位 / 最大持仓数 —— 属策略层集成，不在因子/信号工厂范围。
我们仅提供**因子层面风险属性**（最大回撤、成本敏感性、中性化状态），见 `_factory_extra`。
