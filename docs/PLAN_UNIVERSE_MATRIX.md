# PLAN · 池子扩展 + 因子-池子矩阵 + 月度评审

> 状态：计划已定，开工 · 2026-08-05
> 用户决策：池子扩展与月度评审**并行推进**；方法论升级为**因子-池子配对**（避免单池验证漏掉在特定池有效的因子）。

## 1. 背景与动机

- 用户质疑：为什么只在 hs300 验证？会不会漏掉"只在特定池子有效的因子组合"？
- 实测：baostock 无 zz1000 接口（hs1800 拼不了）；但 **hs300 ∪ zz500 = 正好 800 只**（可精确拼 hs800）；全 A 可用 query_all_stock。
- 决策：**因子-池子矩阵验证**——每个因子在多个池子跑 IC，自动找"主场"，组合层多池子正交。

## 2. 池子定义（BaoStockProvider universe 扩展）

| universe | 来源 | 数量 | 说明 |
|---|---|---|---|
| sz50 / hs300 / zz500 | 现有原生接口 | 50/300/500 | 不变 |
| **hs800**（新增） | hs300 ∪ zz500 合并去重 | ~800 | 中证800 精确近似 |
| **ALL**（增强） | query_all_stock + 过滤 | ~5300 → 过滤后 | 新增过滤参数：min_mcap（市值下限，默认 50 亿）、去 ST（is_st=0）、去停牌 |

- 缓存隔离：asset_list_{mode}.csv 独立（现有机制）；全 A 拉取量大，后台分批跑。
- **全 A 现实约束**：一次性拉取 2-3 小时（缓存后复用）；内存大 → history_start 窗口 + 过滤；次新/退市前视用"市值过滤+窗口"近似（严格 PIT 列 Phase 4）。

## 3. 因子-池子矩阵验证（scripts/factor_universe_matrix.py）

```
因子 × 池子 → RankIC / ICIR / DSR → IC 矩阵
→ 每因子自动标注"主场"（IC 最高的池子）
→ Factor 接口可选 universe_hint 声明，矩阵校验声明 vs 实测一致性
→ 结果写 research/factor_cards/ 与 TEST_LOG
```

- 跑法：矩阵需要每个池子全历史面板（缓存已热时秒级）；首次跑 hs800 需先缓存。
- 目的：找出"换池子后因子强弱反转"的实例——正是用户担心的漏网之鱼。

## 4. 月度评审（monitor/monthly_review.py + docs/MONTHLY_REVIEW_TEMPLATE.md）

5 项体检 + 决策闭环：
1. 健康度：本月 RankIC/ICIR/胜率 vs 长期均值
2. 滚动衰减：20/60 日 IC 与长期均值差
3. 拥挤度：多头重叠、换手率、风格相关性漂移
4. 组合归因：影子账户月度 vs 基准、因子贡献拆解
5. 墓地复检：已淘汰因子复苏迹象
→ 输出：保留/降权/停用/复活 决策，更新因子卡片

## 5. 改动清单

| 文件 | 改动 |
|---|---|
| data/providers.py | BaoStockProvider：hs800 合并池 + ALL 过滤参数（min_mcap/去ST） |
| factors/interface.py | Factor 接口加可选 `universe_hint` |
| scripts/factor_universe_matrix.py | 新增：因子×池子 IC 矩阵 |
| monitor/monthly_review.py | 新增：5 项体检 + 决策输出 |
| docs/MONTHLY_REVIEW_TEMPLATE.md | 新增：月报模板 |
| docs/RESEARCH_LOG.md / HANDOFF.md | 追加记录 |

## 6. 执行顺序

1. 池子基础设施（hs800 + ALL 过滤）→ 2. **启动全 A 后台拉取（2-3h）** → 3. hs800 缓存拉取 → 4. 矩阵验证脚本 → 5. 月度评审脚本 + 模板 → 6. 首期月报试跑 → 7. 全 A 缓存完成后跑全 A 矩阵。

## 7. 风险与缓解

| 风险 | 缓解 |
|---|---|
| 全 A 拉取 2-3h 被中断 | 每票即写 parquet（现有机制），断点续拉 |
| 全 A 内存 OOM | min_mcap 过滤 + history_start 窗口；组合阶段单独进程 |
| hs800 首拉 ~20-30min | 后台跑，先做月度评审 |
| 因子在 ALL 池 IC 虚高 | 流动性/ST 过滤 + 成本模型约束 + 中性化（已有） |
