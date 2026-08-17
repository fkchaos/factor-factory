# ARCHITECTURE · 因子工厂架构设计

> 最后更新：2026-08-17 ｜ 对应 ADR：见 `docs/adr/` ｜ 开源文档集与目录导航见仓库根 `README.md`
> 设计基石（用户硬要求）：**XDT**（可扩展/可解耦/可测试）｜**Plan-First + Open-Research**｜**全程文档化**

---

## 1. 设计目标

建一个**因子工厂**：持续产出经样本外验证、可正交组合、可监控衰减的因子库，最终输出稳健、低相关的因子组合。

非目标：不做 ML 模型库（不引入 Qlib 式模型动物园）、不做实盘券商对接（本期纯研究/模拟）。

---

## 2. 六层解耦架构

```
factor-factory/
├── data/         # DataProvider 接口 + Tushare/AkShare/Local 适配器 + PIT 对齐 + 限流重试
├── factors/      # Factor 接口 + registry + 预处理三件套 + 各因子实现（插件式）
├── engine/       # Engine 接口（walk-forward + 真实成本 + 封板/T+1/停牌/退市）
├── validate/     # Validator（IC/IR/分层/衰减/换手/冗余 + DSR/PBO 过拟合审计）
├── portfolio/    # 正交、加权、风险约束（核心+卫星，二次规划）
├── monitor/      # 因子分布漂移 / IC 衰减 / 拥挤度 / 归因看板
├── signals/      # Signal 接口 + 时序信号实现（插件式，s-code）
├── scripts/      # 生产线脚本：出包 / 矩阵 / 月报 / 看板 / 导出
├── deliverables/ # 交付物（独立）：factors/ signals/ universe_matrix/ strategy_export/ CHANGELOG.md
├── docs/         # 用户文档：ARCHITECTURE / DEPLOYMENT / USER_GUIDE / CONTRIBUTING / DATA_CONTRACT / INTERFACE_CONTRACTS / RESEARCH_LOG / adr/（内部运维见 docs/dev/）
├── research/     # 计划文档模板 + RESEARCH_LOG + TEST_LOG + 因子墓地 + 因子卡片
├── tests/        # 单测 + 确定性合成 fixture + 前视防护专项测试
└── configs/      # 因子/组合/回测的 YAML 声明
```

**层间只依赖接口（Protocol/ABC），核心逻辑不 import 任何具体实现。**

| 层 | 职责 | 对外依赖（只认接口） |
|---|---|---|
| data | 多源行情/财务/另类，point-in-time 对齐 | `Storage`（内部） |
| factors | 预处理流水线 + 因子注册表 | `DataProvider` |
| engine | 交易模拟（walk-forward + 真实成本） | `DataProvider` / `Factor` |
| validate | IC/IR/分层/CSCV/DSR/冗余 | `Factor` 输出 |
| portfolio | 正交、加权、风险约束 | `Validator` 结果 |
| monitor | 漂移/拥挤/归因 | 全部 |

---

## 3. 核心接口契约（详见各层 `interface.py`）

- **`DataProvider`**：`get_panel(fields, start, end) -> Panel`、`get_index_returns(...)`、`get_pit_financials(...)`（按公告日期≤交易日期过滤）、`list_universe(date)`（point-in-time 成分股）。适配器：`TushareProvider`（主）、`AkShareProvider`（fallback）、`LocalProvider`（测试）。

### 3.1 数据契约（单位/格式防火墙）

可插拔数据源的核心风险是**切换源后结果悄悄漂移**。契约由 `data/contract.py` 集中定义并运行时强制：

| 项 | 契约值 |
|---|---|
| 面板索引 | MultiIndex `(date, asset)`；date=datetime64[ns] 无时区；asset=规范代码 |
| 规范代码 | 6位+交易所后缀：`000001.SZ` / `600000.SH` / `830000.BJ`（`normalize_code` 统一） |
| 价格 open/high/low/close | CNY；复权口径由 Provider 声明（免费 Tushare=raw，AkShare=qfq） |
| volume | **股(shares)**，非手（Tushare vol×100 / AkShare 手×100） |
| amount | **元(CNY)**，非千元（Tushare ×1000） |
| turnover | 百分比 0–100（非小数） |
| market_cap | 元(CNY)（Tushare total_mv 万元×1e4 / AkShare spot） |
| 收益率 | 小数（0.01=+1%），非百分数 |
| 缺失 | NaN，**禁止 0 占位、禁止静默前填** |

Provider 的 `get_panel` 返回前 MUST 过 `canonicalize_panel + validate_panel`，违反即抛错（而非污染因子）。新增源只写实现类即可，测试见 `tests/test_provider_contract.py`。完整规范见 `docs/DATA_CONTRACT.md`。
- **`Factor`**：`compute(panel, as_of_date, ctx) -> pd.Series`。**`as_of_date` 是接口层防前视的关键参数**——引擎保证传入的 `panel` 只含 `as_of_date` 及之前的数据；因子实现不得自行取全样本。注册到 `registry`。
- **`Engine`**：`run(factor, provider, config) -> BacktestResult`。内部 walk-forward（train/test/step 可配），调用 `CostModel` 计算真实成本，处理涨跌停封板、停牌、退市。
- **`CostModel`**：`cost(trade_volume, adv, side) -> float`。默认二次冲击成本 + 最低佣金；禁止引擎内部写死成本。

---

## 4. 数据流

```
定时/手动触发
   │
   ▼
DataProvider.get_panel / get_pit_financials   →  原始面板（已 PIT 对齐）
   │
   ▼
Factor.compute(panel[≤as_of_date], as_of_date) →  原始因子值（接口层已保证无前视）
   │
   ▼
factors/preprocess：MAD 去极值 → 截面 Z-score → 行业/市值中性化   →  纯净因子
   │
   ▼
Engine.run：walk-forward 切片 → 选股 → CostModel 成交 → 组合序列
   │
   ▼
validate：IC/IR/分层/衰减/换手 + DSR/PBO 审计   →  因子卡片 + PASS/WARN/FAIL
   │
   ▼
portfolio：正交化 + 加权 + 风险约束   →  因子组合
   │
   ▼
monitor：漂移/拥挤/归因看板
```

**前视防护双保险**：① 接口层 `Factor.compute` 只用 `as_of_date` 及之前窗口（引擎强制）；② 预处理三件套逐截面日执行，禁止全局统计量。

---

## 5. 扩展点（XDT 落地）

- **新因子** = 新文件实现 `Factor` + 注册到 `registry`，零改核心。
- **新数据源** = 新文件实现 `DataProvider`（Tushare 挂了切 AkShare，核心不动）。
- **新验证指标** = `validate/` 插件，输出并入因子卡片。
- **新成本模型** = 实现 `CostModel`，YAML 切换。
- 所有参数（回测窗口、成本、股票池、因子权重）走 `configs/*.yaml`，禁止硬编码。

---

## 6. 测试与文档约束

- 核心引擎（成本计算、时间切片、前视防护、封板/停牌）必须单测 + 确定性合成 fixture；CI 门禁 pytest + coverage。
- 前视防护专项测试：构造"已知会前视"的合成因子，验证引擎**拒绝**用未来数据（详见 `tests/test_lookahead.py`）。
- 文档集（用户向）：`ARCHITECTURE` / `ADR` / `DEPLOYMENT` / `USER_GUIDE` / `CONTRIBUTING` / `DATA_CONTRACT` / `INTERFACE_CONTRACTS` / `RESEARCH_LOG`（研究记录入口）+ 因子卡片；内部运维文档见 `docs/dev/`（不计入公开交付）。缺一视为交付不全。

---

## 7. 关键决策索引

- ADR-0001：六层解耦 + 插件式 Factor 接口；前视防护放在接口层而非靠自觉。
- （后续 ADR 在 `docs/adr/` 追加）

---

## 8. 生产线与交付物边界（开源布局核心）

本仓库刻意把**生成侧（生产线）**与**产物侧（交付物）**分离，二者只在看板聚合、互不耦合：

| 侧 | 目录 | 角色 | 谁改 |
|---|---|---|---|
| 生产线 | `data/ engine/ factors/ validate/ portfolio/ monitor/ configs/ scripts/` | 产出因子的**代码与流程** | 开发者（PR） |
| 交付物 | `deliverables/` | 因子/信号包、矩阵、导出 JSON、CHANGELOG | 推进器自动产出；下游只读消费 |

- 生产线**永不反向依赖**交付物内容；交付物是生产线的纯输出，可整体复制给策略组而不带任何代码。
- `deliverables/CHANGELOG.md` 是本仓的发布说明（替代原跨仓库 issue 机制），新交付由推进器写入 `[Unreleased]`，交互会话整理归档。
- 看板 `docs/factor_board.html` 只读聚合两侧状态，不写任何一侧。
- 内部运维文档（HANDOFF / 评审 / 数据源 SOP）归入 `docs/dev/`，**不进公开文档导航**，避免泄露协作细节。
