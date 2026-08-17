# 灵感池与论坛漏斗设计（PLAN_IDEA_BACKLOG）

> 状态：骨架设计，不动代码。hs1800 拉取完成后实现。
> 关联：PLAN_DELIVERABLES.md（交付物）、ARCHITECTURE.md（XDT 六层）

## 1. 背景与核心目标

**痛点**：论文、论坛是"存量"——逛两天就没新东西了。而因子工厂要能**持续**运转，前提是"想法火花"要持续供给。

**目标**：建一套系统化的想法捕获机制（灵感池 idea backlog），让任何来源（论文 / 论坛 / 自己观察 / 盘感 / 聊天）的火花都能被记录、被假设化、被送进已有的工厂流水线，持续产出新因子 → 新策略。

**价值链**：
```
想法火花 → 假设定调 → 因子构造 → 检验(IC/DSR/PBO) → f-code 交付 → 下游选股策略 → 持续迭代
```

## 2. 因子来源三条腿（架构回顾）

| 腿 | 定位 | source_type | 当前状态 |
|----|------|-------------|----------|
| 腿1 继承验证 | 站别人肩膀 | paper / sell_side / factor_zoo | 已在跑（zoo_basics、overnight、ivol） |
| 腿2 原创假设 | 自己产出 | observation / logic / chat | 依赖人的盘感，待装反馈闭环 |
| 腿3 系统挖掘 | 机器/数据驱动 | ml_mining / alt_data / combo | combo 在做(f0003a)，其余待立 |

**论坛野路子归入腿1漏斗**，置信度预设最低，不直接采信，必须过统一闸门。

## 3. 灵感池（idea backlog）数据模型

| 字段 | 类型 | 说明 |
|------|------|------|
| idea_id | str | `iYYYYMMDD-NNN` |
| source_type | enum | paper/sell_side/zoo/forum/observation/logic/chat/ml_mining |
| source_ref | str | 论文标题 / 论坛帖链接 / 观察笔记路径 |
| raw_idea | text | 原始人话描述（"我觉得 XX 现象有点怪"） |
| hypothesis | text | **可证伪假设**（必须有方向，如"X 高 → 未来 N 日收益高"） |
| rationale | text | 为什么觉得能成（逻辑 / 盘感 / 文献支撑） |
| confidence_seed | enum | high(paper) / mid(zoo) / low(forum,observation) |
| status | enum | backlog → hypothesized → in_pipeline → validated / rejected / dormant |
| created_at | date | |
| owner | str | 提出者或源标识 |
| linked_fcode | str | 进流水线后关联的 f-code |
| review_cycle | date | 3 个月后回看日 |
| hit_status | enum | pending / hit / miss |
| note | text | 复盘备注 |

**状态机**：
```
backlog（原始火花）
  → hypothesized（写成可证伪假设）
  → in_pipeline（触发因子构造）
  → validated（过闸门，分配 f-code） / rejected（未过） / dormant（暂搁置）
```

## 4. 论坛漏斗机制

- 论坛源进入：`source_type=forum`，`confidence_seed=low`
- **硬性闸门**：必须能写出 `hypothesis`（不能写可证伪假设的，留在 backlog，不进流程）
- 进流程后与学术源走**完全相同**的 IC / DSR/PBO / 月度监控
- **意义**：扩大假设候选池，质量由统一闸门保证；论坛结论本身不被采信，只当"待验证假设"

## 5. 反馈闭环（盘感校准）

- `review_cycle` 到期：统计各 `source_type` 的 `hit_rate`
- 来源维度复盘：哪类源命中率高 → 提高该源 `confidence_seed`；哪类低 → 降低
- **价值**：把"人的盘感"变成可度量、可改进的资产，而非靠天赋硬扛

## 6. 与现有流水线接驳

- `idea(status=hypothesized)` → 因子构造（复用 Factor 协议 + validator 链中性化 / 前视防护）
- `validated` → `allocate_fcode` 分配 f-code（复用 `_REGISTRY.csv`）
- `rejected` → 保留记录供复盘（不删）
- 复用：`monthly_review` 月度监控、`overfit_audit` DSR/PBO 门禁

## 7. 本期范围

- 只定骨架 + 字段，不动代码
- 下一步（hs1800 拉完后）：实现 idea backlog 存储（CSV / 轻量） + 漏斗校验脚本 + 复盘统计
