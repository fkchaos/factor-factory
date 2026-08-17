# DELIVERABLES · 交付物查阅指引

> 面向**只看不贡献**的外部用户 / 下游策略组：本厂所有交付物都落在 `deliverables/`。
> 看板 `docs/factor_board.html` 只是**总体状态快照**（进度、缓存、待发布数），不是明细。
> **要看某个因子的假设、某信号的叠加效果、某池的回测、机器可读导出**——按下面的地图去对应路径。

---

## 0. 第一入口

| 入口 | 是什么 | 什么时候用 |
|---|---|---|
| `docs/factor_board.html` | 单文件美观看板（零依赖，双击即开） | 想一眼看总体进度 / 已交付清单 / 待发布数 |
| 本文件 `docs/DELIVERABLES.md` | 交付物明细地图 | 想定位"某个交付物去哪查、里面是什么、怎么消费" |
| `deliverables/factors/_INDEX.md` | 因子库总索引（f-code 表） | 想快速扫全部因子编号与状态 |

> 看板与 CHANGELOG 都是**人类可读视图**，由生产线自动生成、只读不写；真源是下面各目录里的 `card.md` / `*.json` / `*.csv`。

---

## 1. 因子线 · `deliverables/factors/`

| 路径 | 内容 | 读者 |
|---|---|---|
| `_INDEX.md` | 因子库总索引：f-code / 名称 / 类别（single·combo）/ 状态 / 创建日 | 人类（速览） |
| `_REGISTRY.csv` | 机器可读注册表（同 `_INDEX`，供程序解析） | 程序 |
| `fXXXX/card.md` | **核心卡片**：假设 / 可证伪条件 / PIT 处理 / 分池 RankIC / 主池验证指标 / DSR·PBO 审计结论 | 人类（必读） |
| `fXXXX/manifest.yaml` | 包元信息：编号 / 名称 / 池 / 出包时间 / 口径版本（`NEUTRALIZE_VERSION`） | 人类+程序 |
| `fXXXX/metrics_<pool>.json` | 逐池指标（sz50·hs300·zz500·hs800·zz1000·hs1800） | 程序 |
| `fXXXX/backtest_<pool>.csv` | 逐池回测序列（组合净值 / 收益） | 程序 |
| `fXXXX/correlation.csv` | 同池冗余相关（与已交付因子的 RankIC 相关） | 人类+程序 |
| `fXXXX/overfit_audit.json` | DSR / PBO 过拟合审计（**只证明真实性，不评价质量高低**） | 程序 |

> 一个因子目录示例：`deliverables/factors/f0001a/`（隔夜-日内反转）。

---

## 2. 信号线 · `deliverables/signals/`

| 路径 | 内容 | 读者 |
|---|---|---|
| `_REGISTRY.csv` | 信号注册表 | 程序 |
| `_REDUNDANCY.json` | 跨信号冗余 / 视角独立性检查 | 程序 |
| `sXXXX/card.md` | **核心卡片**：状态定义 / `exec_lag=1` 钢印 / 叠加 Sharpe·DD 改善 / 同期诊断（`*_contemp` 仅供诊断，不可用于评估） | 人类（必读） |
| `sXXXX/manifest.yaml` | 包元信息 | 人类+程序 |
| `sXXXX/state_sequence.csv` | 市场级状态序列（逐交易日） | 程序 |
| `sXXXX/state_performance.json` | 状态叠加绩效（已 `shift(1)`） | 程序 |
| `sXXXX/overfit_audit.json` | DSR / PBO 审计 | 程序 |

> ⚠️ **exec_lag 红线**：时序信号 T 日收盘才算得出 T 日状态，最早 T+1 建仓；评估必须用 `shift(1)` 口径，同期口径对广度类信号近似同义反复。详情见 `deliverables/strategy_export/README.md`。

---

## 3. 组合导出 · `deliverables/strategy_export/`

下游消费**用这一层**，不是看板。

| 文件 | 内容 | 条目 |
|---|---|---|
| `stock_factors.json` | 横截面选股因子（f-code），机器可读真源 | 当前 3 |
| `timing_signals.json` | 市场级择时信号（s-code），含 `exec_lag` 钢印 | 当前 3 |
| `risk_params.json` | **占位**：止损 / 止盈 / 仓位等风控参数不在本厂范围 | 0 |
| `README.md` | 怎么被下游消费（对齐 `a-share-quant-sim` 阶段 0），字段说明与判决随池翻转注意 | 人类 |

> 把上面三个 JSON 直接放到下游 `alpha-research/inputs/` 即可被阶段 0 消费；`source` 均已标 `external`。

---

## 4. 跨因子矩阵 · `deliverables/universe_matrix/`

| 文件 | 内容 |
|---|---|
| `ic_matrix_YYYY-MM-DD.csv` | 全因子 RankIC 相关（冗余检查） |
| `icir_matrix_YYYY-MM-DD.csv` | 全因子 ICIR 矩阵 |
| `dsr_matrix_YYYY-MM-DD.csv` | 全因子 DSR / PBO 过拟合矩阵 |

> 按日留存历史快照，可对比因子库扩张前后的冗余演化。

---

## 5. 发布说明 · `deliverables/CHANGELOG.md`

- 格式：[Keep a Changelog](https://keepachangelog.com/)。
- `[Unreleased]` = 推进器新交付、待主理人归档的内容；带版本号段（如 `[0.1.0]`）= 已发布批次。
- **只记录"交付了什么"，不评价 IC 好坏**（本厂不设质量门槛）。

---

## 怎么消费（外部用户视角小结）

1. **要机器可读真源** → 直接用 `deliverables/strategy_export/*.json`；看板 / CHANGELOG 只是人类视图。
2. **想读懂某个因子的假设与边界** → 读 `deliverables/factors/<fcode>/card.md`。
3. **想看某因子在某池的回测** → `backtest_<pool>.csv` + `metrics_<pool>.json`。
4. **想看某信号能不能改善回撤** → `deliverables/signals/<scode>/card.md` 的"叠加 Sharpe·DD 改善"段。
5. **本厂不设质量门槛**：DSR/PBO 通过即出包，因子强弱由下游在 JSON 层筛选——我们给多池原始 IC 表，主场池选择权交给你。

> ⚠️ `deliverables/` 是生产线的**纯输出**，可整体复制给下游而不带任何代码；它与 `data/…monitor/scripts/` 只在看板聚合、互不耦合（详见 `docs/ARCHITECTURE.md` §8）。
