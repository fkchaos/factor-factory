# Changelog · 交付物发布说明

> 本文件记录 factor-factory 的**交付物**变更（因子 f-code / 信号 s-code 出包）。
> 格式参考 [Keep a Changelog](https://keepachangelog.com/)。`[Unreleased]` 段由每日推进器
> 在新交付时自动追加；主理人在交互会话整理发布时把 `[Unreleased]` 内容归档为带版本号的段落。
>
> 注：本厂**不设质量门槛**——出包只保证真实性与 PIT 合规（DSR/PBO 审计 + 前视防护 CI），
> 因子强弱由下游策略组在 JSON 层筛选决定，故本文件不评价 IC 好坏，只记录"交付了什么"。

## [Unreleased]

### 补录（2026-10-10 人工核查 · 推进器漏登 + 对外发货 JSON 陈旧修复）

> 2026-10-10 主理人交互核查发现两处**产物与仓库不同步**。均非代码缺陷，是流程缺口，本次一并修复。

**① CHANGELOG 漏登 5 个已交付因子包**（推进器只在「消费灵感出包」路径写 CHANGELOG，批量补矩阵路径不写）：
- `2026-09-11 | factor | f0080a | 成交额前分位+均线突破（amount_rank_ma_breakout） | deliverables/factors/f0080a/`（hs300 RankIC −0.0163）
- `2026-09-11 | factor | f0081a | 动量向上+缩量回调（momentum_volume_shrink_pullback） | deliverables/factors/f0081a/`（hs300 RankIC +0.0013）
- `2026-09-14 | factor | f0084a | 区间嵌套事件频率（inside_day_freq） | deliverables/factors/f0084a/`（hs300 RankIC +0.0018）
- `2026-09-14 | factor | f0085a | Amihud跳跃成分占比（amihud_jump_share） | deliverables/factors/f0085a/`（hs300 RankIC −0.0014）
- `2026-09-14 | factor | f0086a | 财报更新收益（cashflow_update） | deliverables/factors/f0086a/`（hs300 RankIC −0.0000）

**② 对外发货 JSON 陈旧 31 天（对外交付缺口，重要）**：`deliverables/strategy_export/stock_factors.json`
停在 2026-09-09 的 76 条，而交付目录已有 91 个因子包 → 策略组拿到的清单**缺 f0077a–f0091a 共 15 个**。
已重跑 `scripts/export_to_strategy_json.py`，现为 **91 因子 / 4 信号**（generated 2026-10-10 10:19）。
根因：推进器 cron 步骤里**没有"重跑 export"这一步**——`docs/dev/HANDOFF.md` §关键环境变化 已写明
「因子/信号包有更新后要重跑一次，否则 JSON 是旧快照」，但仅停留在文档约定、未进 cron。
⚠️ **该流程缺口待主理人决定是否补进驱动器脚本**（改动 cron 行为，未擅自改）。

### 归档止损（2026-10-10 · 待决项③）

- `f0073a` 预告净利同比、`f0074a` 预告类型分档：**归档止损**（manifest / _REGISTRY.csv(note) / _INDEX.md / 两张 card.md 顶部停用横幅 status → archived）。
  依据：全池 RankIC≈0（hs300 0.0004 / 0.0027）、IC胜率≈50%；DSR=1.0 / PBO=PASS（真实但无截面预测力，非假因子），属预告类弱因子。
  同步发货端：修 `scripts/export_to_strategy_json.py` 跳过非 current 因子并在 JSON 带 `status` 字段，重跑后 f0073a/f0074a 不再进入 `stock_factors.json`。
  文件保留供追溯，不再纳入新策略选股；冗余簇 C13（ρ=0.748）随之消失。

### Phase 2 资金面开工（2026-10-10 · 待决项④，用户拍板「开 3 因子起步集」）
- `2026-10-10 | factor | f0095a | 龙虎榜净买入强度（lhb_netbuy_intensity） | deliverables/factors/f0095a/`
  （hs300 RankIC +0.0003 / ICIR +0.00 / 胜率 51.3% / n=1593；近 20 日历日「上榜日 龙虎榜净买额/流通市值」之和，连续型；DSR=1.0 PASS）
- `2026-10-10 | factor | f0096a | 龙虎榜上榜关注度（lhb_attention） | deliverables/factors/f0096a/`
  （hs300 RankIC +0.0013 / ICIR +0.01 / 胜率 50.6% / n=1593；近 20 日历日上榜天数；DSR=1.0 PASS）
- **新数据源接入（AkShare 免费，已实测）**：`stock_lhb_detail_em` 龙虎榜每日明细
  → 139,579 行 / 5,796 股 / 138,094 次上榜事件，预建面板
  `data/moneyflow_cache/lhb_netbuy_20d.parquet`、`lhb_attention_20d.parquet`（2838 日 × 5796 股）。
  构建器 `scripts/build_lhb_signals.py`；配套 `stock_margin_detail_sse/szse`（两融，按 `date=` 逐日取全市场 ~2000+2100 行）。
- ⚠️ **结论判读**：两个龙虎榜因子截面 RankIC≈0，属 **dud**（真实非假因子——DSR=1.0 / PBO=PASS，前视防护合规），
  只是无截面 alpha。与既有资金流因子 f0024a（RankIC≈−0.015）同向印证：**资金面/龙虎榜类信号在本厂 PIT 口径下截面预测力普遍≈0**。
  按产线纪律照常交付（不设质量门槛），好坏由下游策略组在 JSON 层自行判断。
- ⚠️ **根因诊断（覆盖率）**：龙虎榜是**稀疏事件**——预建面板里任一交易日仅约 **7.1%** 的股票在 20 日窗口内有上榜记录，
  其余 93% 恒为 0（截面大量并列）。并列值不携带排序信息，RankIC 被**机械压到 ≈0**，
  这与"因子逻辑不成立"是两回事。若要真正检验游资效应，应改用**事件研究口径**（conditional on 上榜）
  或只在"当日事件股池"内做选股，而不是全市场截面排名。融资余额不受此限（两融标的覆盖率 ~38% 且大盘股接近全覆盖）。
- `2026-10-10 | factor | f0097a | 融资余额5日增幅（margin_balance_5d） | deliverables/factors/f0097a/`
  （hs300 RankIC **−0.0099** / ICIR −0.13 / 胜率 44.4% / n=1510；DSR=1.0 PASS。
  **方向与灵感假设完全吻合**：融资盘加杠杆追涨 → 后续回吐，故 RankIC 取负；
  强度为两个龙虎榜因子的 5–10 倍，是本次 3 因子起步集里唯一有实质截面信号者。
  gross 年化 0.119 / Sharpe 0.610，net（含成本）0.0247 / Sharpe 0.221）
- **新数据源接入（AkShare 免费）· 两融**：`stock_margin_detail_sse` / `stock_margin_detail_szse`（按 `date=` 逐日取全市场）
  → 构建器 `scripts/build_margin_panel.py`（按日缓存 `.cache/margin_raw/` 可续跑），
  产出 `data/moneyflow_cache/margin_balance_panel.parquet`：**1646 交易日 × 4428 两融标的**（ok=1646 / empty=841 周末节假日）。
  周末节假日与个别 `ProxyError 502`（query.sse.com.cn）以空占位跳过，留下零星日期 NaN 缺口，对 5 日增幅口径可接受。

### 因子（f0089a/f0090a/f0091a · 2026-10-05 推进器 drain + 冗余前置闸门全过）
- `2026-10-05 | factor | f0089a | 正面成交量冲击（pos_volume_shock） | deliverables/factors/f0089a/`（hs300 RankIC −0.0048 / hs800 −0.0051 ICIR −0.08~−0.10 胜率 ~46%；纯量价：近20日上涨日异常放量强度；DSR/PBO 审计通过；全局矩阵 91×91 独立无冗余twin（|ρ|<0.7）→ 通过冗余前置闸门，计入独立有效新增）
- `2026-10-05 | factor | f0090a | K线形态综合（kline_pattern_composite） | deliverables/factors/f0090a/`（hs300 RankIC −0.0018 / hs800 −0.0018 ICIR ≈0 胜率 ~49%；纯OHLC+量能情绪系数：近10日多形态加权分×tanh(量能共振)；DSR/PBO 通过；独立无冗余twin → 通过闸门，计入独立有效新增）
- `2026-10-05 | factor | f0091a | 涨停基因回踩（limitup_gene_pullback） | deliverables/factors/f0091a/`（hs300 RankIC −0.0073 / hs800 −0.0056 ICIR −0.08~−0.09 胜率 ~46-48%；纯OHLCV：近10日涨停次数×健康回踩条件；DSR/PBO 通过；独立无冗余twin → 通过闸门，计入独立有效新增）

### ⚠️ 口径变更（2026-09-09 · 影响全部 76 个因子的顶层 IC，下游若已对接请注意）

**「主场池」概念废弃，改为「基准池」。**
- 旧行为：`card.md` 的"主场池"= manifest 第一个池；而 `strategy_export` JSON 的 `home_pool` = **全样本 |ICIR| 最大的池**，且顶层 `ic_mean`/`ir` 取该池值 → **两处口径打架**，且后者是**后视选池**（与"用今天的市值回测历史选股"同一类病），会把回测表现系统性抬高。
- 新行为：两边统一为**基准池 = manifest 声明的第一个池**（可复现、非后视）。顶层 `ic_mean`/`ir` 仅作**口径锚点**，不代表该因子在此池最强；**配池请用 `_factory_extra.metrics_by_pool` 全池明细自行判断**。
- **本厂不再提供"主场池"推荐。** `factor_universe_matrix.py` 的 home pool 列同理属**观测值**而非推荐。
- 兼容：旧字段 `home_pool` / `gate_7_2_at_home_pool` **保留同名**（值已与 `reference_pool` 一致），新增 `reference_pool` / `pool_selection_warning` / `gate_7_2_at_reference_pool`。
- **实测影响**：顶层 IC 普遍下修。例：f0001a `0.0312@zz1000` → `0.0095@sz50`；f0070a `0.0139@hs800` → `0.0083@hs300`；f0076a `0.0082@hs800` → `0.0055@hs300`。**此前给策略组的顶层 IC 含后视选池美化，请以本次后的数值为准。**
- 76 张 `card.md` 已同步回填（纯文案，数值未动）。

### 因子（f0087a · 2026-09-17 推进器 drain + 冗余前置闸门命中）
- `2026-09-17 | factor | f0087a | 第二阶段突破强度（stage2_breakout） | deliverables/factors/f0087a/`（hs300 RankIC +0.0002 / hs800 −0.0041 ICIR ≈0 胜率 49.5%；纯 close 趋势+基底突破复合：250日RPS百分位 + 偏离200日均线 + 偏离52周低点 + 200日均线抬头；⚠ **冗余twin**：↔ f0035a(12-1动量) ρ=**+0.858**（|ρ|≥0.7）→ 标 twin、灵感 i20260917-011 改 deferred、card 保留作参考、不计入独立有效计数。RPS+均线偏离本质即动量代理，与12-1动量高度同源，冗余闸门价值再证）

### 因子（f0088a · 2026-10-01 推进器 drain + 冗余前置闸门命中）
- `2026-10-01 | factor | f0088a | 短期特质动量SIMOM（simom） | deliverables/factors/f0088a/`（hs300 RankIC −0.0089 / ICIR −0.073 胜率 47.4%；hs800 RankIC −0.0145 / ICIR −0.12 胜率 45.8%；纯 close 市场模型残差复利（60日beta剥离市场收益 → 21日特质收益复利）；DSR=1.000 PASS、PBO=null；⚠ **冗余twin**：↔ f0006a(20日动量) ρ=**+0.946** 与 ↔ f0053a(rejoicing_regret) ρ=**−0.93**（|ρ|≥0.7）→ 标 twin、灵感 i20261001-001 改 deferred、card 保留作参考、不计入独立有效计数。21日残差复利实际≈原始20日动量，未剥离动量成分，冗余闸门价值再证）

### 因子（f0076a · Phase 1 第二小批 · 盈余惊喜）
- `2026-09-09 | factor | f0076a | SUE标准化未预期盈余（sue） | deliverables/factors/f0076a/`（hs300 RankIC +0.0055 / hs800 **+0.0082** ICIR 0.11 胜率 56.0%；财报线迄今**强度第二 + 独立性最好**的因子。季节性随机游走预期（Q_t 预期=Q_{t−4}），无需卖方一致预期 → 覆盖率 98%，绕开业绩预告仅 28–36% 的死穴。与 f0072a 净利同比 ρ=**0.50** <0.7 冗余门槛 → 标准化确带来增量，非重复品；全局矩阵中未出现在任何 |ρ|≥0.7 配对，通过冗余前置闸门）

### 因子（f0082a / f0083a · 2026-09-11 推进器 drain + 冗余前置闸门命中）
- `2026-09-11 | factor | f0082a | 双重增长凸性（growth_convexity） | deliverables/factors/f0082a/`（hs300 RankIC −0.0040 / hs800 −0.0007 ICIR −0.01 胜率 48%；纯 PIT 财报：operate_income_yoy × net_profit_parent_yoy，无市值口径问题；全局矩阵(83因子)中未出现在任何 |ρ|≥0.7 配对，正交性达标，计为独立有效新增）
- `2026-09-11 | factor | f0083a | 市场beta/BAB（beta_market_60d） | deliverables/factors/f0083a/`（hs300 RankIC +0.0078 / hs800 +0.0075 ICIR +0.05 胜率 53%；纯 close 60日市场beta 取负号=BAB 方向；⚠ **冗余twin**：↔ f0058a beta×量波动交互 ρ=−0.716（|ρ|≥0.7）→ 标 twin、灵感 i20260910-003 改 deferred、card 保留作参考、不计入独立有效计数）

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

### 因子（f0077a–f0079a 批量 drain · 2026-09-09 每日推进器）
> 本轮 drain 3 条 hypothesized（纯价量 DRIF + 财报线 价值B/M + ΔROE）；f0077a DRIF 触发冗余前置闸门（ρ=−0.81↔f0002a），标冗余twin，不计入有效独立计数。
- `2026-09-09 | factor | f0077a | DRIF收益分布形态（drif） | deliverables/factors/f0077a/`（hs300 RankIC −0.0163 / hs800 −0.0229 ICIR −0.13/−0.18 胜率 43.2%/41.2%；⚠️ 全局矩阵 ρ=**−0.81**↔f0002a(特质波动率) → **冗余twin**，灵感 i20260810-001 改 deferred，card 留作参考，不计入独立有效计数）
- `2026-09-09 | factor | f0078a | 价值B/M账面市值比（value_bm） | deliverables/factors/f0078a/`（hs300 +0.0074 / hs800 +0.0118 ICIR +0.10 胜率 53.5%；分母 PIT 流通市值与 pit_float_mcap 同口径，补齐池内估值类空白）
- `2026-09-09 | factor | f0079a | ΔROE盈利加速（delta_roe） | deliverables/factors/f0079a/`（hs800 +0.0118 ICIR +0.11 胜率 54.1%；相邻披露期 ROE 环比，全局最独立因子 mean|ρ|=0.021，质量边际改善增量显著）

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
