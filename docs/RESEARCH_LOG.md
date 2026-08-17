# RESEARCH_LOG · 外部调研记录

> 本文件是"计划先行 + 外部调研交叉"要求的落地载体。
> 每条调研记录固定字段：**来源 / 核心结论 / 对本项目启示 / 可落地动作 / 可信度**。
> 维护节奏：每周调研窗口追加；重大结论同步回写 ARCHITECTURE / ADR / LESSONS_LEARNED。
> 可信度分级：高（官方文档/论文/成熟开源）/ 中（二手教程/博客）/ 低（社区经验，需自证）。

---

## R2026-0804-01 · Microsoft Qlib 架构

- **来源**：https://hivebook.wiki/wiki/qlib-microsoft-s-ai-quant-investment-platform ；https://github.com/gitter-badger/qlib
- **核心结论**：
  - Qlib 是微软开源 AI 量化平台（~42K stars，v0.9.7），四层：数据层（自研列式二进制，point-in-time correctness 内建）→ 表达式引擎（因子用 `$close / Ref / Mean` 表达式声明、惰性+缓存计算）→ 模型库 → 回测/组合（可配置成本模型、top-k）。
  - 组件**松耦合、可独立使用**；因子以"函数"声明而非"预存数据"，便于复用与 LLM 自动挖掘（RD-Agent）。
  - 数据层天生防前视；但**自定义特征/标签仍可能泄漏未来信息**，需自行校验 label 窗口不重叠特征。
  - 内置成本模型与 top-k 只是起点，不现实的假设（无滑点、完美成交）会虚高结果。
- **对本项目启示**：
  - `DataProvider` 必须把 **point-in-time 对齐**作为数据层铁律（对齐 Qlib 设计）。
  - `Factor` 用**可调用接口**声明（对齐我们的插件式设计），而非预存因子值。
  - 成本模型必须**显式、可配置**，禁止用引擎默认值。
- **可落地动作**：在 `data/interface.py` 的 `DataProvider` 契约里写入 PIT 约束；在 `engine/interface.py` 强制传入 `CostModel`。
- **可信度**：高（官方架构描述 + 多源一致）

---

## R2026-0804-02 · Alphalens 单因子验证范式

- **来源**：https://deepwiki.com/quantopian/alphalens/4.1-basic-usage-workflow ；https://cloud.baidu.com/article/5023494
- **核心结论**：
  - 因子分析标准流水线：factor（MultiIndex[date,asset] Series）+ prices + 可选 group → `get_clean_factor_and_forward_returns` → tear sheet（收益/IC/换手）。
  - 核心指标：IC 均值、IC std、分位数收益"阶梯"、IC 衰减（1–20 日）、换手率/自相关。
  - **关键规则**：prices 必须是"因子计算后下一个可得价格"（防前视）；`filter_zscore` 做极值过滤**会引入前视偏差**（文档明确 caution）；通过 prices 参数自动处理停牌/退市（存活偏差）。
- **对本项目启示**：
  - `validate/` 模块应复刻：IC/IR、分位数单调性、IC 衰减、换手/自相关。
  - 成交假设 = Alphalens 的"因子后下一可得价" → 直接对应我们 **T+1 开盘价**执行假设。
  - **禁用 filter_zscore 式全局极值过滤**；改用 MAD 去极值（见 R2026-0804-04）。
- **可落地动作**：在 `validate/` 设计 `FactorValidator` 输出与 alphalens tear sheet 同构的指标卡。
- **可信度**：高（官方/Quantopian 文档）

---

## R2026-0804-03 · Tushare Pro 数据源与坑

- **来源**：https://www.cnblogs.com/jinsonL/articles/21277838 ；https://cloud.baidu.com/article/5022839
- **核心结论**：
  - Tushare Pro 覆盖 A股/港股/美股、日/分钟/Tick、财务/资金流/龙虎榜/宏观，200+ 字段；积分制，免费档 120 分可用日线。
  - 坑：限流（需 `time.sleep(0.5)` 或批量按交易日查询）；代码须带 `.SZ/.SH` 后缀；返回空可能因格式/非交易日/停牌；高级接口有积分门槛。
  - **Tushare 不原生提供 point-in-time 财报**——返回的是"最新已披露值"，披露滞后需自行处理。
- **对本项目启示**：
  - 选 Tushare Pro 作为**主 `DataProvider` 适配器**；AkShare 作 fallback（双源冗余，对齐计划要求）。
  - 在 `DataProvider` 适配层内置**限流/重试/批量**逻辑。
  - **PIT 对齐是本项目责任**，不在数据源——Tushare 给的是最新披露值，需在取数时按"公告日期 ≤ 交易日期"过滤。
- **可落地动作**：`data/tushare_provider.py` 实现 `DataProvider`；`data/akshare_provider.py` 作 fallback；PIT 过滤放在 `data/base.py` 公共逻辑。
- **可信度**：中（二手教程，但与其官方接口行为一致；需自证实测）

---

## R2026-0804-04 · 预处理四层 + PIT + 中性化标准

- **来源**：https://m.10jqka.com.cn/20260703/c677938271.shtml （ITL 智能投研技术联盟）；https://blog.csdn.net/thmail/article/details/151211157
- **核心结论**：
  - 数据四层管线：**清洗 → 标准化（行业/市值中性化）→ 时序对齐（PIT，杜绝前视）→ 分层存储**。
  - PIT（时点一致性）被强调为"**最关键**"环节，彻底消除未来信息泄露。
  - 因子预处理标准三步：MAD 去极值（或 3σ）→ 截面 Z-score（**每个交易日 t 独立计算均值/标准差，用全样本均值=作弊**）→ 行业哑变量+对数市值回归取残差=纯净因子。
- **对本项目启示**：
  - `factors/` 引擎必须内置**逐截面日**的 MAD→Z-score→中性化流水线，禁止跨时间用全局统计量。
  - PIT 对齐归 `DataProvider` 责任（与 R2026-0804-03 一致）。
- **可落地动作**：在 `factors/preprocess.py` 实现 `winsorize_mad / zscore_cross_section / neutralize` 三件套，单测覆盖"全局 vs 截面"差异。
- **可信度**：高（行业技术联盟观点 + 代码实例一致）

---

## R2026-0804-05 · CSCV / DSR / PBO 过拟合审计

- **来源**：https://github.com/Aliipou/backtest-audit ；https://github.com/eslazarev/purged-cross-validation ；https://ml4trading.io/docs/diagnostic/reference/references
- **核心结论**：
  - **DSR（Deflated Sharpe Ratio, Bailey & Lopez de Prado 2014）**：用"测试过的策略数 n_trials"对最优夏普打折，要求提供**所有 trial 夏普的方差**；DSR p>0.95 才算显著。
  - **PBO（Probability of Backtest Overfitting）**：CPCV 切 S 个时间块、枚举 C(S,S/2) 种训练/测试划分，PBO = IS 胜者≠OOS 胜者的比例；**PBO>0.5 即严重过拟合**。
  - 辅助：PSR（概率夏普>0）、MinTRL（最小跟踪记录长度）。
  - 已有成熟开源实现 `backtest-audit`（124 测试）、`purgedcv`，**不必重造轮子**。
- **对本项目启示**：
  - `validate/` 必须集成 **DSR（n_trials=我们实测的策略/因子数！）+ PBO**，作为因子入库门禁。
  - 直接**依赖 `backtest-audit` / `purgedcv`** 而非自研统计实现。
  - 由于我们本就会测试大量因子（计划里的因子库），DSR 是**强制项**，不是可选项。
- **可落地动作**：在 `validate/overfit_audit.py` 封装 `backtest_audit.BacktestAuditor`，输入 returns + n_trials，输出 PASS/WARN/FAIL。
- **可信度**：高（论文方法 + 成熟开源实现）

---

## 调研小结（截至 2026-08-04）

1. **架构对齐 Qlib 的松耦合 + 因子可调用接口**，但本项目定位是"因子工厂"而非 ML 平台，不引入模型库复杂性。
2. **PIT 是数据层铁律**，且必须由本项目（而非 Tushare）实现财报披露滞后对齐。
3. **验证套件 = Alphalens 指标 + DSR/PBO 门禁**，过拟合审计直接复用 `backtest-audit`。
4. **成交假设统一为 T+1 开盘价**（Next-Available-Price 规则），成本模型显式可配置。
5. **预处理三件套（MAD/Z-score/中性化）逐截面日执行**，是防前视的第二道防线（接口层是第一道）。

## R2026-0805-01 · BaoStock 免费数据源接入（免积分）

- **来源**：用户旧工程 a-share-quant-sim（`core/providers/baostock.py`，Apache-2.0 用户自有代码）；docs/PLAN_BAOSTOCK_PROVIDER.md
- **动机**：Tushare 免费 token 缺前复权/换手率/指数池（需 500 积分）；baostock 实测三项全通且免积分。
- **核心结论**：
  - 新增 `BaoStockProvider`（data/providers.py）：移植旧工程取数逻辑 + 适配本项目契约（volume=**股**、adjustflag=**2 前复权**、代码 `600000.SH`、parquet 缓存）。约 60-70% 代码直接复用旧工程。
  - **契约扩列**：PANEL_FIELDS 新增 `tradestatus`(0停牌/1正常) / `is_st`(0正常/1ST)——baostock 独有字段，其他源缺省 NaN。这是回测真实性（停牌不可交易、ST 剔除）的关键增量。
  - **normalize_code 增强**：支持 `sh.600000` 点分隔前缀格式（baostock 代码格式），对 Tushare/AkShare 无回归（21 项新单测覆盖）。
  - **pandas 2.x 兼容坑**：baostock 0.9.30 的 `rs.get_data()` 内部用 `df.append`（pandas>=2.0 已移除）多页必崩；改为 `next()/get_row_data()` 手动循环（`_collect_rows`），零 monkey-patch、无全局副作用。
  - **市值方案**：baostock `query_stock_basic` 实测不返回股本字段（文档过时）；复用 AkShare 东财 spot 总市值快照（口径与 AkShareProvider 完全一致，失败降级 NaN）。
  - `FF_PROVIDER` ∈ {tushare, akshare, baostock} 切换；`scripts/cross_source_check.py --source baostock` 支持免积分跨源核对。
- **验证**：sz50 全池 smoke 通过（市值量级正确：中石化 6034 亿/中信 4188 亿/三一 1788 亿）；67 项 pytest 全绿（原 46 + 新 21）；真实流水线跑通见 TEST_LOG。
- **已知限制**：当日数据收盘后才更新（适合历史回测）；baostock 免费服务偶发不稳（health_check+缓存兜底）；Windows 退出偶发崩溃 0xC0000409（不显式 logout，进程退出自然断开）。
- **可信度**：高（真实数据实测 + 契约校验 + 跨源核对）

## R2026-0805-02 · overnight 符号复核 + DSR/PBO 审计落地

- **overnight 符号复核**（双源交叉：baostock sz50 前复权 + Tushare SZ300 raw）：
  - 拆解实证：overnight 成分 SZ300 RankIC +0.024（ICIR 9.5，正信号）；intraday 成分 -0.028（ICIR -7.4，日内反转负信号）；
    旧方向 `-(overnight-intraday)` RankIC -0.040（方向反）；翻转后 `(overnight-intraday)` RankIC +0.040（ICIR 11.6@1d / 9.0@5d）。
  - **决策：因子翻转**（factors/overnight_intraday.py 已改，docstring 同步）。经济含义=做多"隔夜高开+日内冲高回落"，实质 1 日反转+隔夜延续。
  - ⚠️ 换手极高，成本敏感——组合回测必须含成本（二次冲击已含）。
- **DSR/PBO 审计落地**（validate/overfit_audit.py + validator 接入）：
  - DSR（Bailey & LdP 2014）自研：经 n_trials 多试打折；n_trials=8（诚实估计试过策略数，含翻转前方向）。
  - PBO（Bailey et al. 2015）自研 CSCV：候选集=[主因子, 等权, 1日反转, 1日动量]，S=12 块 924 组合。
  - 调研发现：backtest-audit 是**代码审计器**（AST 查泄漏）非统计器；purgedcv 接口面向 ML 时序 CV——故按论文公式自研（公式公开权威）。
  - 门禁：DSR≥0.95 且 PBO≤0.30 为 PASS；sz50 实测两因子 DSR=1.0 / PBO=0.0（小池+强信号，候选基准弱，PBO≈0 属正常）。
  - 新增单测 12 项（公式 sanity + 边界），全量 pytest **79 项全绿**（67+12）。
- **验证**：FF_PROVIDER=baostock sz50 2024 起：overnight 翻转后 RankIC +0.033；组合 **+27.6% / Sharpe 1.02 / MaxDD -15.1%**（翻转前 +21.3%/0.70）。
- **可信度**：高（双源交叉 + 论文公式 + 门禁单测）

## R2026-0805-03 · 因子行业/市值中性化落地

- **动机**：Phase 3 风险模型约束；此前因子未中性化（数据源受限），市值/行业暴露可能伪装成 alpha。
- **实现**：validate/validator.py 预处理链路升级为 MAD → **行业+市值中性化**（回归残差）→ Z-score：
  - 市值：panel market_cap（AkShare 快照口径，点估值近似）
  - 行业：BaoStockProvider 新增 `get_industries()`（query_stock_industry 全市场快照，证监会分类，缓存 csv）
  - 降级链：无市值 → 跳过；无行业（非 baostock provider）→ 仅市值中性化
  - factors/interface.py neutralize 支持 industry_dummies=None（纯市值）
- **实证**（baostock sz50 2024 起，中性化前后对比）：
  - overnight_intraday：RankIC 0.033→0.017，ICIR 3.21→3.06（风格暴露剥离，IC 减半，信噪比持平）
  - ivol：RankIC 0.030→0.018，ICIR **2.35→3.09**（剥离小市值暴露后信号更稳）
- **解读**：IC 下降 = 原预测力含市值/行业暴露；残余为正的 IC 是纯增量 alpha，组合层面更可托底。
- **单测**：tests/test_neutralize.py 3 项（市值剥离/行业哑变量/全链路），全量 pytest **82 项全绿**（79+3）。

## R2026-0805-04 · 池子扩展（hs800 + 全A）与因子-池子矩阵

- **决策（用户）**：因子-池子配对方法论——单池验证会漏掉"只在特定池有效的因子组合"；不同因子配不同池子。
- **池子基础设施**（BaoStockProvider）：
  - `hs800`：hs300∪zz500 合并去重 = 精确 800 只（中证800 近似；实测 baostock 无 zz1000 接口，hs1800 拼不了）
  - `ALL`：query_stock_basic type=1 全市场（5541 只）→ min_mcap 市值过滤（50亿 → 3107 只）
  - **接口踩坑**：query_all_stock 实测不稳定（当日数据未更新时返回 0、大结果集分页崩溃 0xC0000409）→ 弃用，改 query_stock_basic
  - **并发教训**：两个 baostock 进程并行拉取触发服务器断连（WinError 10054），且失败票被静默跳过（58/800 残缺）→ 已加缺失告警 + 串行拉取策略
- **因子-池子矩阵**（scripts/factor_universe_matrix.py）：因子 × [sz50/hs300/hs800/ALL] → RankIC/ICIR/DSR 矩阵 + 主场标注 + 换池反转检测；Factor 接口加 universe_hint 声明校验。
- **月度评审**（monitor/monthly_review.py + docs/MONTHLY_REVIEW_TEMPLATE.md）：5 项体检（健康度/滚动衰减/拥挤度/归因/墓地复检）+ 决策闭环；首期 baseline 落盘逐日 IC。
- **待跑**：hs800/ALL 缓存完成后跑矩阵 + 首期月报 baseline（串行续拉，避免并发断连）。

## R2026-0805-05 · 并发 baostock 进程级硬崩溃确认 + 月报基线文件名池子隔离

- **并发崩溃升级（实测）**：ALL 后台拉取（任务 5BlgW5）运行中，前台另起 baostock 进程（monthly_review baseline / factor_universe_matrix）直接**进程级硬崩溃**——exit 1、无 Python traceback、重定向日志空白；而 R2026-0805-04 记录的"并发"仅表现为服务器断连（WinError 10054）。
  - 推论：baostock 全局登录会话/本地查询服务在跨进程间冲突，第二个 `login()` 直接 abort 整个进程，远比网络断连严重（断连尚可重试，硬崩溃无输出、无法诊断）。
  - **规则升级（铁律）**：ALL 后台拉取完成前，**禁止任何前台 baostock 命令**（矩阵/月报/baseline 一律等 ALL 完成后跑）；ALL 完成后各池串行跑（含 hs800/ALL 缺失票补拉），绝不再并发。
- **修复：月报基线文件名池子隔离**：`monitor/monthly_review.py` 的 `_ic_history_path` 原无池子后缀（`ic_{name}.csv`），多池 baseline 会互相覆盖（hs800 写盖 sz50）。改为 `ic_{name}_{pool}.csv`（池子感知），`baseline`/`report` 调用点同步传入 `args.pool`；旧池子无关文件后续清理。
- **矩阵脚本静态校验**：逐项核对 `validate_factor` 返回字典，确认含 `rank_ic / icir / dsr / pbo` 四键，与 `factor_universe_matrix.py` 读取完全一致；`home` 主场标注与换池反转检测逻辑无误，待 ALL 后跑全 4 池得真实主场。
- **当前阻塞态**：ALL 拉取进行中（截至 24min 已写 196/3107 parquet，预计还需数小时，完成后自动通知）；sz50 50/50 完整，hs300 77/300、hs800 108/800 部分（均由 ALL 超集补全，无需单独续拉）。
- **下一步（ALL 完成后）**：① `factor_universe_matrix.py --pools sz50,hs300,hs800,ALL` 全量；② `monthly_review.py baseline --pool hs800`（必要时 ALL）；③ `monthly_review.py report` 首期月报；④ 清理旧池子无关基线文件。

## R2026-0805-06 · 池子策略 pivot：弃全A、转指数分层池（zz1000 + hs1800 组合池）

- **用户决策（pivot）**：全A（3107）资源偏重 → **优先级放低**；因子组合研发先聚焦指数分层池 **50/300/500/800/1000 + 组合池**。这一转向同时解决了 R2026-0805-04 的"无 zz1000 拼不了 hs1800"死结。
- **zz1000 缺口（baostock 无接口）**：baostock 仅 `query_hs300/zz500/sz50_stocks`，无中证1000。改用 **AkShare `index_stock_cons("000852")`** 取成分股（已为依赖，market_cap 也走它），缓存 csv 同行业表口径。
  - **踩坑**：akshare 该接口返回 1000 行但仅 **772 唯一**（214 重复行，接口数据怪象）→ `_asset_list_zz1000` 内 `sorted(set(...))` 去重，真实成分股 772 只。
  - 列名 `品种代码/品种名称/纳入日期`（akshare 1.18）。
- **hs1800 组合池（递归合并）**：`hs1800 = hs800 ∪ zz1000` = 800 + 772 = **1572 只，0 重叠**——即用户原想要的"中证1800"近似，且**无需全A**。
- **BaoStockProvider 重构**：`_asset_list` 改为委托 `_resolve_universe(mode)`（递归）；`_asset_list_merge` 改为子池递归合并（支持嵌套：hs1800→hs800→hs300/zz500 + zz1000）；新增 `_asset_list_zz1000`（AkShare）。错误提示补齐 zz1000/ALL。
- **停止 ALL 后台拉取（任务 5BlgW5）**：用户 deprioritize + 并发硬崩溃铁律（R2026-0805-05）导致 ALL 运行期间任何前台 baostock 命令不可跑；为立即转指数池研发，**杀掉 ALL 拉取**（已跑 35min，写盘 260 只 parquet 按 code 保留复用，非丢失）。
- **启动 hs1800 缓存拉取（任务 O79RDe，后台）**：`hs1800` 是指数分层超集，一次拉取即补全 sz50(已50/50)/hs300/hz500/zz1000 全部价格缓存（hs800/hs1800 复用子集）。`cache_universe.py hs1800` 串行拉取，缺失票告警沿用。
- **矩阵脚本同步**：`factor_universe_matrix.py` 的 `POOLS/ALL_POOLS` 增补 zz500/zz1000/hs1800（默认池列表含 7 个）。
- **下一步（O79RDe 完成后，自动通知）**：① `factor_universe_matrix.py --pools sz50,hs300,zz500,hs800,zz1000,hs1800` 全 6 池因子-池子配对验证（回应"不同因子配不同池子，防漏"）；② `monthly_review.py baseline/report` 首期月报（先 sz50，再扩 hs800/hs1800）；③ 清理旧池子无关基线文件。

## R2026-0805-07 · 数据源契约一致性审计 + 复权口径防火墙（用户硬要求）

- **用户硬要求**：不同数据源必须严恪框架设计——接口层（contract）定死格式/单位，provider 负责转换，**绝不允许不一致**。本次对 4 个 provider 逐处转换点做了一致性审计。
- **审计结论**：单位/代码格式硬转换基本都做对了；**发现 2 处真实不一致 + 1 处缓存漂移 + 1 处防火墙缺口**：
  1. **【不一致·高】Tushare 复权口径 = raw，契约 `ADJ_POLICY="qfq"`**：免费 token 拉不了 qfq（`adj_factor` 限频），`TushareProvider` 静默返回不复权价——正是契约想防的"切换源结果悄悄变"（除权除息日伪信号）。
  2. **【不一致·中】市值快照缓存两份**：BaoStock 写 `.cache/baostock/market_cap.csv`、AkShare 写 `.cache/akshare/market_cap.csv`，同一份 AkShare 东财 spot 快照拉两次、口径漂移风险。
  3. **【防火墙缺口】LocalProvider.get_panel 未过 `canonicalize_panel`/`validate_panel`**——合成数据虽规范，但与其他 provider 不一致，且少一道兜底。
  4. **【测试缺口】无跨 provider 的复权口径/缓存一致性自动测试**。
- **实证验证（无网络前提下）**：用已落盘 `.cache/baostock/market_cap.csv` 反推——max 3.66e12、min 4.0e8，茅台 2026-08-04 qfq close=1328.36 量级吻合 → **AkShare `总市值` 单位确为元（非亿元），符合契约 `market_cap=元`，此坑未触发**。东财实时端点从沙箱连不上（已知"东财断连新浪降级"），故未能实时复测，但缓存数据已验证。
- **修复**：
  1. `contract.py` 新增 `assert_adj_policy(provider_adj, allow_mismatch=False)`：不一致默认 `raise RuntimeError`（fail-loud），仅诊断场景 `allow_mismatch=True` 放行并 `warnings.warn`。
  2. 4 个 provider 均声明 `adj_policy` 类属性：`BaoStockProvider="qfq"`、`AkShareProvider="qfq"`（符合契约）、`TushareProvider="raw"`、`LocalProvider="raw"`（合成无公司行为）。
  3. `scripts/real_research.py _make_provider`：构造 provider 后 `assert_adj_policy(...)`——baostock/akshare 直接过；tushare 须 `FF_ALLOW_ADJ_MISMATCH=1` 显式放行（主流程禁止静默 raw）。
  4. `scripts/cross_source_check.py`：tushare 分支 `assert_adj_policy(pa.adj_policy, allow_mismatch=True)`（方向性诊断，产物已标注跨口径）。
  5. `data/interface.py` DataProvider 协议补 `adj_policy` 声明要求。
  6. **市值缓存统一**：新增模块常量 `_SHARED_MARKET_CAP_CACHE = .cache/akshare/market_cap.csv`；BaoStock `_share_map` 与 AkShare `_market_cap_map` 共用同一文件 + `key.parent.mkdir`；旧的 `.cache/baostock/market_cap.csv` 已成孤儿（已复制正确数据到共享路径，旧文件可手动删）。
  7. `LocalProvider.get_panel` 补 `canonicalize_panel` + `validate_panel`。
- **测试**：`tests/test_provider_contract.py` 扩 `test_adj_policy_conformance`（4 provider adj_policy 断言）、`test_assert_adj_policy_ok_and_block`（一致过/不一致抛/放行告警）、`test_local_provider_get_panel_canonicalized_sorted`（Local 过防火墙+升序+代码规范）。
- **回归**：全量 pytest 各文件单独跑 **rc=0 全绿**（含新增 3 项）；整跑退出码 1 为 Windows 进程退出崩溃（0xC0000409，与 baostock 同源良性，非回归——逐文件均过）。

---

## R2026-0805-08 · P6 动物园因子 + 交付物脚本骨架（hs1800 拉取并行推进）

- **背景**：用户确认交付物下游是选股策略研究员，要求因子/组合 + 相关性测试 + 回测数据；并明确"组合即平级 f-code 因子"。hs1800 后台拉取（O79RDe）仍在进行（371/1572），故本轮推进**不依赖 baostock 拉取**的 P6 代码。
- **P6 动物园基准因子（factors/zoo_basics.py，新）**：实现 3 个标准因子动物园基准，供 correlation.csv 对标冗余度：
  - `momentum_20`：close[t-1]/close[t-21]-1（跳过 1 日，规避微观结构）
  - `reversal_5`：-(close[t-1]/close[t-6]-1)（短期反转，做空近期赢家）
  - `size_log_mcap`：log(总市值)（与 Fama-French SMB 同向）
  - 全部仅用 as_of_date 及之前数据 → 通过 `assert_no_lookahead`（与内部因子同一前视纪律）。
  - 测试 `tests/test_zoo_factors.py`（4 项，合成数据）：compute 形状 / 前视防护 / momentum-reversal 负相关 sanity / size=log(mcap)。
- **card 模板扩展（research/templates/factor_card_template.md）**：补「框架一致性字段」（中性化状态/PIT认证/主场池）+「消费指引」段（能否直接进模型/适用池/成本敏感/冗余提醒/复现命令/已知陷阱）——交付物强制段（PLAN_DELIVERABLES §3.2）。
- **build_deliverable.py（scripts/，新骨架）**：四层交付包构建脚本。纯函数（allocate_fcode / render_manifest / _upsert_registry）可独立单测；数据密集部分（compute_factor_series / compute_correlation / build_backtest）复刻 validator 中性化链，需 baostock 缓存才能跑（hs1800 完成后端到端验证）。
  - 测试 `tests/test_build_deliverable.py`（5 项）：f-code 起号/组合成分/增号语义/ manifest 渲染 / registry upsert。
- **测试汇总（不依赖 baostock）**：test_zoo_factors + test_build_deliverable + test_provider_contract = **31 passed**。
- **下一步（O79RDe 完成后）**：① `factor_universe_matrix.py` 全 6 池 → 主场池字段；② `build_deliverable.py` 端到端跑 f0001a/f0002a 样板包；③ `monthly_review.py` 首期月报。
