# docs/dev · 内部开发文档

> ⚠️ **本目录为内部开发/运维文档，非面向用户的项目文档。**
> 内容涉及 AI 协作 session 的交接、内部评审、数据源 token 接入 SOP 等，
> **不写入公开文档导航**，外部读者请以仓库根 `README.md` 与 `docs/` 下其余文档为准。

## 文件索引

| 文件 | 用途 | 是否含敏感信息 |
|---|---|---|
| `HANDOFF.md` | 当前研发快照 + 待办 + 环境信息；由每日推进器（cron）原地维护，供后续 session 续作 | 否（纯进度） |
| `HANDOFF-2026-08-06.md` | 历史交接快照（归档） | 否 |
| `REVIEW-2026-08-07-v75.md` | 内部评审记录（v75 里程碑） | 否 |
| `SOP_TUSHARE_TOKEN.md` | Tushare token 申请/配置/重测 SOP；**token 一律用占位符，真实凭证仅存本地环境变量或 `configs/tushare.yaml`（已被 .gitignore 忽略）** | 否（占位符） |

## 维护约定
- 这些文件随研发推进更新，**不进入 `docs/` 用户文档树**，也不在 `README` 引用。
- 若需在用户文档中引用其中结论，请把结论沉淀到 `ARCHITECTURE.md` / `RESEARCH_LOG.md` / `docs/adr/`，而非直接链到本目录。
