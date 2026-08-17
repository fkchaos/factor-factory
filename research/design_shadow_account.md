# 设计文档：影子账户（ShadowAccount，方案 A）

> Plan-First 预注册。本文件在编码前明确设计，供评审与后续 session 对齐。

## 1. 背景与目标
- 因子研发到"可生产"前，需一段**小资金 / 模拟持仓跟踪（1-3 月）**，观察因子在"滚动实盘"下的净值、换手、回撤、相对基准表现。
- 用户决策：先做**方案 A（纯回测影子，不接券商）**；方案 B（接 QMT/PTrade 模拟盘）待外部券商环境就绪后再说（见 HANDOFF 待决策清单）。

## 2. 与 WalkForwardEngine 的区别（关键）
| 维度 | WalkForwardEngine | ShadowAccount（方案 A） |
|---|---|---|
| 训练结构 | train/test 切片、重新训练 | 固定参数、滚动持有（不重新训练） |
| 调仓 | 每 step_days | 每 rebal_days（默认 5，周频） |
| 语义 | 样本外验证（过拟合审计用） | 模拟实盘持仓跟踪（更接近真实观察） |
| 选股/成交 | select_targets + execute_rebalance | **复用同一套**（共享 engine.selection） |

> 共享选股层是解耦（XDT）与本 proj 防"隐式约定漂移"的核心：两套逻辑只写一处，前视防护只审计一处。

## 3. 接口与字段（ShadowConfig，落在 engine/interface.py）
- `warmup_days=252`：因子数据预热起点
- `train_days=252`：因子切片参考窗口（ctx.start）
- `rebal_days=5`：调仓周期（交易日）
- `top_n=10`、`cost_model="quadratic"`、`execution="t1_open"`、`max_participation=0.10`、`capital0=1e6`

## 4. 前视防护
- 因子计算只用 `prepare_panel_for_factor` 切到 as_of_date 的窗口（继承 Factor 契约）。
- ShadowAccount 信任 factor.compute 遵守契约（由 Factor 接口 + CI `assert_no_lookahead` 保证），自身不重复审计。

## 5. 成交与成本
- T+1 开盘成交（与回测一致，禁止 T 日收盘乐观假设）。
- 二次冲击成本 + 单笔 <= 10% ADV 流动性约束（复用 QuadraticCost + execute_rebalance）。

## 6. 产出（ShadowResult）
- `equity_curve`：每日净值
- `holdings`：每次调仓的目标持仓快照
- `turnover_log`：每次调仓单边换手率
- `metrics`：total_return / sharpe / max_drawdown / n_days / avg_turnover / n_rebalances / benchmark_return（指数对比缺失则 None）

## 7. 验证计划（测试）
- `test_select_targets_returns_valid_dict`：选股返回合法 dict（数量 <= top_n、价格正有限）
- `test_shadow_account_runs_and_metrics_finite`：组合因子跑通、指标有限、换手率 >=0、holdings 与 n_rebalances 一致
- `test_shadow_and_wf_both_run`：同一因子 WF 与 Shadow 都跑通且产有限净值

## 8. 失败判定（不通过则退回设计）
- 任一测试失败（选股为空 / 指标 NaN / holdings 与 rebalances 不一致）
- 影子账户净值与 WF 出现**方向性矛盾**（同因子同数据，两者 Sharpe 符号相反且幅度异常）——需排查选股层共享是否一致

## 9. 备注
- benchmark 对比依赖 `provider.get_index_returns`；LocalProvider 未实现时降级为 None（不阻塞测试），真实 Tushare 接入后自动生效。
- 方案 B 扩展点已在 HANDOFF 标注；届时 ShadowAccount 增加 broker adapter 接口，选股/成交层不变。
