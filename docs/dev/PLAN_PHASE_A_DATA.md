# PLAN · Phase A 数据源扩展（2026-10-10 开工）

> 用户拍板「按建议顺序来」：A1 扩财报字段 → A2 行业分类 → （下一轮）A3 资金面。
> 本文件先记**开工前的实测结论**，再记计划。实测推翻了上一轮的两个假设，必须先更正。

---

## 0. 🔴 开工实测结论（推翻上一轮建议的前提）

### 0.1 A2「接申万行业分类」——前提错误，该事项降级

上一轮（09-21）我判断"面板无行业列，行业中性化是按市值分组降级的假中性化"。
**实测证明这个判断是错的**：

| 核查项 | 实测结果 |
|---|---|
| `BaoStockProvider.get_industries()` | **已存在**（`data/providers.py:976`），baostock `query_stock_industry` |
| 覆盖度 | **5203 只全市场覆盖，83 个行业类别**（证监会 2012 分类，如 `J66货币金融服务`） |
| 出包时用的 provider | `BaoStockProvider`（tushare 因无 token + adj_policy=raw 被契约 `assert_adj_policy` 拒绝，故实际必走 baostock） |
| `validate/validator.py::_neutralize_cross_section` | **已接好**：L61 取 `get_industries()` → L64 `pd.get_dummies` → L68 `neutralize(fv, dummies, log_mktcap)` |
| 卡片实证 | f0001a `calc_logic` 写明「中性化：industry+mktcap(PIT: amount/turnover)」 |

**结论：行业中性化一直在正常工作，不是降级态。** 83 类粒度比申万一级（31 类）更细，
对中性化而言更优。A2 从「接数据源」降级为「用现有分类落地行业因子」。

遗留的真实局限（不是 bug，是数据性质）：
- 行业标签是**当前快照，非 PIT 时间序列**。公司主营变更/重组后，历史期会被归入现行业。
- 影响评估：行业分类变更频率远低于市值/价格，前视程度远小于 `market_cap` 那类（每日变且直接关联未来收益）。
- **纪律**：落地行业因子时必须在卡片标注该局限，不静默当 PIT 用。

### 0.2 A1「扩 current_assets/current_liabilities」——东财字段不可用，改道 baostock

| 数据源 | 字段 | 实测（茅台/平安/招行/宁德/中芯） |
|---|---|---|
| AkShare 东财 `stock_balance_sheet_by_report_em` | `CURRENT_ASSET_BALANCE` | **不可用**：茅台 `0.0`、宁德 `-1000`（哨兵值）、平安/招行 `NaN` |
| 同上 | `CURRENT_LIAB_BALANCE` | **不可用**：同上全 0 或 NaN |
| 同上 | `RESEARCH_EXPENSE`（利润表） | **可用**：茅台 1.15e8 / 宁德 1.14e10 / 中芯 2.73e9（金融股 NaN 属正常，银行不列研发） |
| **baostock `query_balance_data`** | `currentRatio` / `quickRatio` | **可用且更好**：茅台 5.73/4.45、宁德 1.69/1.47，34 期全覆盖、0 缺失 |
| baostock 同上 | `cashRatio` / `liabilityToAsset` / `assetToEquity` / `YOYLiability` | 可用；`assetToEquity` **连银行都有值**（10~11），可跨全行业 |

**结论**：
- 速动/流动比率**不用自己算**（东财原始字段不可靠），直接取 baostock 现成比率——
  且 baostock 官方计算口径一致，比我们用脏数据自算更安全。
- 金融股 `currentRatio` 天然 NaN 是**行业特性**（银行报表无流动/非流动之分），非数据缺陷，
  因子侧按 NaN 处理，不填充、不伪造。

### 0.3 跨源问题（本次要解决的架构点）

`data/pit_fundamentals.py::default_store()` 硬编码 **AkShareProvider** 作财报后端
（历史原因：只有东财能给 cogs/inventory/accounts_receivable）。
而 `currentRatio` 只有 baostock 有 → **必须让 PIT 财报服务支持多后端**。

---

## 1. A1 实施计划

### 1.1 数据层
1. `AkShareProvider`：`_PIT_FIELD_MAP` 加 `rd_expense → RESEARCH_EXPENSE`；
   `_PIT_CACHE_COLS` 加该列（列指纹自动使旧缓存失效重拉）。
2. `BaoStockProvider`：`_PIT_FIELD_MAP` 加
   `current_ratio/quick_ratio/cash_ratio/liability_to_asset/asset_to_equity/liability_yoy`；
   `_fetch_financial_history` **增加 balance_data 流**（原注释 L1149「balance_data 仅含比率、
   无可用行项目，跳过」——该判断对行项目成立，但**比率本身正是所需**，予以修正）；
   加列指纹缓存校验（对齐 AkShare 的 `_PIT_CACHE_COLS` 机制，防静默缺列）。
3. `data/pit_fundamentals.py`：`PitFinancialsService` 支持**多后端合并**——
   按 (statDate, pubDate) 外连接多条披露流，field_map 取并集；
   `_DEFAULT_PIT_FIELDS` 扩展新字段。

### 1.2 因子层（解锁灵感）
| f-code | 因子 | 灵感 | 口径 |
|---|---|---|---|
| f0092a | 流动比率 current_ratio | i20260903-008 | baostock 现成比率，PIT 按 pubDate |
| f0093a | 速动比率 quick_ratio | i20260903-008 | 同上 |
| f0094a | 研发强度 rd_expense / revenue | i20260903-009 前置件 | 东财 RESEARCH_EXPENSE ÷ 营收 |

调整后 B/M（i20260903-009 本体）需要**近 5 年研发支出序列**做 20% 年摊销资本化，
属多期历史依赖，单字段快照不够 → 单独排 f0095a，本次视工作量决定。

### 1.3 测试
- 新字段 PIT 合规：`pubDate > as_of` 的值绝不出现（复用 `assert_no_lookahead`）。
- 字段非空率：抽样 20 只票验 `current_ratio` 非全 NaN（金融股除外）。
- 缓存列指纹：旧缓存缺新列必须重拉而非静默 NaN。

---

## 2. A2 调整后计划（行业分类已就绪 → 改为落地因子）

直接落地的灵感：
- **i20260903-002 行业动量**：只需行业分类 + 个股收益，**无新数据源**，立即可做。
  （个股短期反转 vs 行业动量方向相反，可正交叠加——文献支持最强的一条）
- i20260914-005 / -006：需行业成交额/价格序列 → 可由成分股 amount/close 聚合，**可做**。
- i20260914-011 cross-momentum：需供应链同伴映射（额外数据）→ 暂缓。
- i20261001-007 行业生命周期：需外部成长期/成熟/停滞分类 → 暂缓。

**所有行业因子必须在卡片标注**：行业标签为当前快照、非 PIT 时间序列。

---

## 3. A3 顺手修（低风险）
1. `factor_universe_matrix.py:130` 的 `universe_hint` AttributeError → Factor 基类补默认属性。
2. 推进器 cron 补「重跑 `export_to_strategy_json.py`」步骤，防发货 JSON 再次陈旧（已发生一次）。
