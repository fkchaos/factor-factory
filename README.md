# factor-factory · 量化因子生产线

> A 股日频多因子**研发工厂**：持续产出经样本外验证、可正交组合、可监控衰减的因子库与时序信号库。
> 定位：**研究 / 模拟盘，非实盘、非投资建议**。本仓库内容开源，欢迎复用与共建。

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)

---

## 它解决什么

建一个**因子工厂**，而不是一堆一次性的因子脚本：持续产出**经样本外验证、可正交组合、可监控衰减**的因子库，最终输出稳健、低相关的因子组合与时序信号，交给下游策略组直接使用。

非目标：不做 ML 模型动物园（不引入 Qlib 式模型库）、不做实盘券商对接（本期纯研究/模拟）。

## 核心特性

- **XDT 设计基石**：可扩展（Extensible）/ 可解耦（Decoupled）/ 可测试（Testable）——六层解耦 + 插件式接口。
- **双线架构**：横截面因子线（f-code，选股打分）+ 时序信号线（s-code，市场状态 overlay），纪律完全平行。
- **PIT 真实口径**：市值/财务严格 point-in-time 对齐，杜绝"今日快照回填全历史"式前视（详见 `docs/DATA_CONTRACT.md`）。
- **前视防护双保险**：接口层 `Factor.compute` 只用 `as_of_date` 及之前窗口 + 预处理逐截面执行；CI 专项测试拒绝用未来数据。
- **真实性门槛（非质量门槛）**：出包只保证 DSR/PBO 过拟合审计 + 前视防护通过；因子强弱交下游策略组筛选，本厂不设 IC 下限。
- **自动化推进**：每日推进器（cron，零交互）自动出包 + 刷新看板 + 同步状态；侦察兵持续供给灵感池。

## 快速开始

```bash
# 1. 安装为可编辑包（含开发依赖 + BaoStock 数据源）
pip install -e ".[dev,data-baostock]"

# 2. 刷新研发看板（浏览器打开 docs/factor_board.html）
make board

# 3. 跑全量测试（前视防护 / 契约 / 确定性 fixture）
make test
```

## 目录结构

```
factor-factory/
├── data/         # DataProvider 接口 + 多源适配器(Tushare/AkShare/BaoStock/Local) + PIT 对齐
├── factors/      # Factor 接口 + registry + 预处理三件套 + 各因子实现（插件式）
├── signals/      # Signal 接口 + 时序信号实现（插件式，s-code）
├── engine/       # Engine（walk-forward + 真实成本 + 封板/T+1/停牌/退市）
├── validate/     # Validator（IC/IR/分层/衰减/换手 + DSR/PBO 过拟合审计）
├── portfolio/    # 正交、加权、风险约束（核心+卫星）
├── monitor/      # 因子分布漂移 / IC 衰减 / 拥挤度 / 归因
├── scripts/      # 生产线脚本：出包 / 矩阵 / 月报 / 看板 / 导出
├── configs/      # 因子/组合/回测 YAML 声明
├── research/     # 计划文档模板 + RESEARCH_LOG + TEST_LOG（含因子墓地）+ 因子卡片
├── tests/        # 单测 + 确定性合成 fixture + 前视防护专项测试
├── deliverables/ # 交付物（独立）：factors/ signals/ universe_matrix/ strategy_export/ CHANGELOG.md
└── docs/         # 用户文档（下方导航）
```

> **生产线 vs 交付物**：`data/…monitor/scripts/` 是生成侧（代码与流程），`deliverables/` 是产物侧（下游只读消费），二者只在看板聚合、互不耦合。详见 `docs/ARCHITECTURE.md` §8。

## 文档导航

| 文档 | 读者 | 内容 |
|---|---|---|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | 架构/研发 | 六层解耦、双线、接口契约、数据流、扩展点、**生产线与交付物边界** |
| [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) | 部署/运维 | 环境、依赖、数据源 token、数据准备、定时任务、GitHub 同步 |
| [docs/USER_GUIDE.md](docs/USER_GUIDE.md) | 使用者 | 看板怎么看、怎么加因子/信号、怎么读交付卡、灵感池 |
| [docs/CONTRIBUTING.md](docs/CONTRIBUTING.md) | 贡献者 | PR 检查清单、PIT 规则、测试纪律、文档要求 |
| [docs/DATA_CONTRACT.md](docs/DATA_CONTRACT.md) | 数据层 | 单位/格式防火墙、多源一致性契约 |
| [docs/INTERFACE_CONTRACTS.md](docs/INTERFACE_CONTRACTS.md) | 接口层 | Factor/Signal/Engine/CostModel 签名与约束 |
| [docs/RESEARCH_LOG.md](docs/RESEARCH_LOG.md) | 研究 | 外部调研与外部调研交叉记录（Open-Research） |
| docs/adr/ | 决策 | ADR-0001 等架构决策记录 |

> ⚠️ `docs/dev/` 为**内部开发/运维文档**（HANDOFF、评审、数据源 SOP），不计入公开文档导航，外部读者无需关注。

## 免责声明

本项目为量化因子**研发/模拟盘**工具，所有因子、信号、回测结论均来自历史数据，**不构成任何投资建议或个股推荐，非实盘交易信号**。投资有风险，决策需谨慎；使用本仓库即表示理解并同意仅用于个人研究。
