# PLAN · BaoStockProvider 接入（免积分数据源）

> 状态：✅ **已实现**（2026-08-05；实现过程见 RESEARCH_LOG R2026-0805-01，验证见 TEST_LOG）· 计划经内部交叉 review（见文末）
> 目标：新增 baostock 免费数据源适配器，`FF_PROVIDER=baostock` 一键切换，绕开 Tushare 积分限制。

## 1. 背景

- Tushare 免费 token 缺三项能力（前复权/换手率/指数池），升级 500 积分门槛高。
- 用户旧工程 `a-share-quant-sim`（本机 `D:/ai-workspace/WorkBuddy/A股研究/a-share-quant-sim`）已实现 DataProvider 架构 + baostock/tencent 适配器，**实测 baostock 三项能力全通**（2026-08-05 探测）。
- 本计划：移植旧工程 baostock **取数逻辑**（约 60-70% 直接复用），适配 factor-factory 数据契约。

## 2. 复用什么 / 改什么

### 复用（来自 a-share-quant-sim/core/providers/baostock.py）
| 片段 | 说明 |
|---|---|
| `_to_bs_code` / `_normalize_code` | 6位 ↔ sh./sz./bj. 前缀转换（需改为适配 `600000.SH` 格式） |
| `_login` / `_connected` 防重入 | baostock 会话管理 |
| `query_history_k_data_plus` 字段集 | date,code,open,high,low,close,volume,amount,turn,tradestatus,pctChg,isST |
| `get_index_components` | hs300/zz500/sz50 成分股（`query_hs300/zz500/sz50_stocks`） |
| `health_check` | 数据源可用性探测 |

### 必改（适配 factor-factory 契约，红线）
| 差异 | 旧工程 | 本实现 |
|---|---|---|
| volume 单位 | 手（`//100`） | **股**（原样，契约死线） |
| 复权 | adjustflag="3" 不复权 | **adjustflag="2" 前复权**（对齐 ADJ_POLICY=qfq） |
| 代码格式 | `600519` | `600519.SH`（复用 contract.normalize_code） |
| 索引 | 普通 df | MultiIndex(date, asset) + canonicalize_panel + validate_panel |
| 缓存 | 内存 dict TTL | **parquet 磁盘缓存**（.cache/baostock/，与 Tushare 同款 `_fetch_one` 模式） |
| market_cap | 无 | `query_stock_basic` 总股本 × close（点估值近似，同 AkShare 快照口径） |

### 契约扩列（纯增量）
`contract.py` PANEL_FIELDS 新增两个 baostock 独有字段（其他源缺省 NaN，契约允许）：
- `tradestatus`: float64, 停牌标记 0/1（0=停牌 1=正常）
- `is_st`: float64, ST 标记 0/1

## 3. 改动清单

| 文件 | 改动 |
|---|---|
| `data/contract.py` | PANEL_FIELDS + tradestatus/is_st |
| `data/providers.py` | + `BaoStockProvider`（约 200 行） |
| `scripts/real_research.py` | 支持 `FF_PROVIDER` ∈ {tushare, akshare, baostock}，默认 tushare；baostock 无需 token |
| `scripts/cross_source_check.py` | 增加 baostock 对照（volume/amount 容忍 1%，close 因复权口径容忍放宽） |
| `tests/test_providers_baostock.py` | 新增：代码转换/字段映射/契约校验（mock 或本地小样本） |
| `docs/RESEARCH_LOG.md` / `research/TEST_LOG.md` | 追加本接入记录 |

## 4. 关键设计决策

1. **登录生命周期**：进程内单会话（`_connected` 防重入）；**不显式 logout**——baostock 在 Windows 退出时偶发崩溃（实测 0xC0000409，不影响已落盘数据），logout 反而增加中断风险；进程自然退出即断开。
2. **拉取粒度**：每票拉全历史 → 立即写 parquet → 切片复用（Tushare 同款，崩溃只损失当前票）。
3. **指数池**：支持 `FF_UNIVERSE=hs300/csi500/zz500/sz50`（baostock 原生接口，当前快照口径，与 Tushare index_weight 限制一致）；交易所子集 SZ/SH/BJ 无原生接口，**本轮不支持**（文档写明）；`ALL` 走 `query_all_stock(当日)`。
4. **指数收益**：`get_index_returns` 走 `sh.000300` 等指数 K 线，pctChg/100（契约小数）。
5. **市值**：`query_stock_basic(code)` 总股本（当前快照）× close → market_cap（元）；拉取失败降级 NaN（契约允许）。注意这是点估值近似，与 AkShare spot 快照口径一致可比。
6. **腾讯源（akshare `stock_zh_a_hist_tx`）**：本轮**不做**（范围控制），列为后续 fallback 增量；已知其 amount=vwap×vol 估算有瑕疵，仅可作 last-resort。

## 5. 测试计划

1. 单元：`to_bs_code` 三市场转换、字段映射、空数据处理
2. 契约：`get_panel` 返回经 canonicalize+validate（真源小样本 2-3 票短窗口）
3. 跨源：cross_source_check 扩展 baostock vs Tushare（volume/amount 应 <1%）
4. 回归：全量 pytest 46 项不破
5. 真实 smoke：`FF_PROVIDER=baostock FF_UNIVERSE=sz50 FF_START=2024-01-01` 单因子 RankIC 跑通

## 6. 风险与缓解

| 风险 | 缓解 |
|---|---|
| baostock 服务器偶发不稳 | `health_check` + 重试 + parquet 缓存（缓存命中零网络） |
| 前复权 vs raw 跨源 close 差异 | 跨源核对 close 容忍度放宽（复权预期内），volume/amount 从严 |
| 当日数据收盘后才更新 | 文档标注：适合历史回测，不适合盘中当日信号 |
| Windows 退出崩溃 | 不显式 logout；每票即写缓存 |

## 7. 内部交叉 review 记录（主理人自审）

- [x] 契约死线核对：volume=股 ✅ / qfq ✅ / `600000.SH` ✅ / NaN 缺失 ✅ / MultiIndex ✅
- [x] XDT 解耦：改动全部收敛在 data 层 + 脚本选源行，engine/factors 零侵入
- [x] 复用标注：provider 逻辑来源 a-share-quant-sim，许可证 Apache-2.0（用户自有代码，无合规问题）
- [x] 范围控制：腾讯源/ProviderManager 不搬，避免过度设计
- [x] 测试覆盖：单元 + 契约 + 跨源 + 回归 + 真实 smoke 五层
- [ ] ~~ProviderManager fallback 链~~ → 决策：不做（调度层职责，research 场景 FF_PROVIDER 足够）
- 结论：**通过，可开工**

### 实现期补充发现（2026-08-05，已全部解决）
| 发现 | 处理 |
|---|---|
| baostock 0.9.30 `rs.get_data()` 用 pandas2 移除的 `df.append`，多页必崩 | `_collect_rows` 手动循环迭代，零 monkey-patch |
| baostock 源字段名是 `turn` 非 `turnover` | 映射层修正 |
| `query_stock_basic` 实测不返回股本字段（文档过时） | 市值改复用 AkShare spot 快照（口径一致） |
| `normalize_code` 不认 `sh.600000` 格式 | contract 增强支持点分隔前缀（21 项单测无回归） |

**验证结果**：sz50 全池 smoke 通过（市值量级正确）；67 项 pytest 全绿（原 46 + 新 21）；真实流水线 `FF_PROVIDER=baostock FF_UNIVERSE=sz50` 跑通。
