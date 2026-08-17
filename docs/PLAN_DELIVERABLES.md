# PLAN_DELIVERABLES · 因子交付包规格

> 状态：已与用户敲定方向（2026-08-05 讨论）。
> 定位：factor-factory 的产物是**可复用的数据产品**，下游消费者是**选股策略研究员**（接过因子做进一步研究与测试）。
> 因此交付物不是内部笔记，必须 self-contained：规格 + 数据 + 证据 + 元数据 四层，且严格遵循 `data/contract.py` 的格式/单位/复权口径（呼应 R2026-0805-07 的防火墙原则）。

## 1. 已敲定的三个方向

| 议题 | 决策 |
|------|------|
| 因子值 parquet 是否随包 | **先卡片后补 parquet**（Phase 1 不含原始面板，Phase 2 补） |
| 交付形态 | **索引 + 每因子独立文件夹（文件夹以 f-code 为稳定主键）** |
| 相关性基准 | **标准因子动物园 + 内部因子** |
| 因子/组合交付必带 | **详细说明文档（card.md 为强制交付物，非可选）** |
| 编号规则 | **fNNNNx：数字=因子/因子组谱系，字母=微调版本（详见 §7）** |

> ⚠️ **强制要求（用户 2026-08-05 追加）**：任何因子或因子组合交付时，**必须附带一份详细说明文档**（即包内 `card.md`，不可省略）。该文档是策略研究员能否"无需读源码即接手"的关键，缺失则视为交付不完整。文档除规格字段外，须含**消费指引**段（见 §3.2），明确告诉下游研究员怎么用、注意什么。

## 2. 交付物目录结构

```
deliverables/factors/
├── _INDEX.md                      # 因子库索引（f-code ↔ 名称 ↔ 类别 ↔ 版本 ↔ 状态，人类可读）
├── _REGISTRY.csv                  # 编号注册表（机器可读，集中分配 f-code，防碰撞）
├── f0001a/                        # overnight_intraday v1（单因子，文件夹以 f-code 为稳定主键）
│   ├── card.md                    # ★ 详细说明文档（强制交付物）
│   ├── correlation.csv            # 相关性测试（vs 动物园 + 内部）
│   ├── backtest_hs300.csv         # 多空收益序列 + 统计（含/不含成本）
│   ├── overfit_audit.json         # DSR/PBO/n_trials 信任证书
│   └── manifest.yaml              # 元数据（fcode/版本/源/窗口/合约/PIT/中性化状态）
├── f0002a/  (ivol v1，同上结构)
└── f0003a/  (因子组合 v1，同上结构；manifest.components=[f0001a,f0002a]，card.md 声明其为组合)
```

> Phase 2 在每因子包内追加 `panel_<pool>.parquet`（date×stock 因子值，合约合规，标注中性化状态）。
> 文件夹名 = f-code（稳定主键）；因子人类名写在 `card.md` 与 `_INDEX.md` 中。版本升字母时**新建文件夹**（如 f0001b），旧版保留不覆盖，便于审计溯源。
>
> ⚠️ **组合不再单独开 `combos/` 子层**：组合就是一个普通 f-code 因子，与单因子**平级置于 `deliverables/factors/` 下**，区别仅在 `manifest.components` 非空 + `card.md` 明确声明"这是一个因子组合"并写清 combination_method 与成分 f-code。这样所有 f-code 都在同一级目录，检索/复用路径一致，下游无需区分单因子/组合目录。

## 3. 各文件规格

### 3.1 `_INDEX.md`（因子库索引）
- 一张总表：因子名 | 类别 | 方向 | 主场池 | RankIC | ICIR | DSR | PBO | 状态 | 包路径
- 一句话说明每个因子的经济含义与已知限制。
- 标注哪些是单因子、哪些是组合。

### 3.2 `card.md`（详细说明文档 · 强制交付物）
> 这是因子/组合交付的**核心文档**，缺失即视为交付不完整（见 §1 强制要求）。

基于 `research/templates/factor_card_template.md`，**新增 3 个必填字段**（呼应框架一致性）：
- **中性化状态**：`raw` / `industry` / `industry+mktcap` / `custom:<desc>`——策略研究员据此决定是否再中性化（防 double-neutralization 静默抹信号）。
- **PIT 认证**：`true` + `assert_no_lookahead` 审计日期；非 PIT 必须红字警告。
- **主场池**：因子-池子配对结论（来自 `factor_universe_matrix.py`），标注 home pool + 次优池 + 换池反转预警。
- 若为组合（即 `manifest.components` 非空，仍是普通 f-code 因子、与单因子平级）：额外写 combination_method（等权 / ICIR 加权 / 正交化）、成分因子 f-code、组合是否降低与已知因子的相关性。

**必含「消费指引」段**（写给下游选股策略研究员，告诉 TA 怎么用、踩什么坑）：
- 因子值是否已中性化、能否直接进选股模型，还是需先处理。
- 适用池子 / 不适用的池子（换池反转预警）。
- 成本敏感性（如 overnight_intraday 净 alpha 对换手极敏感，低换手场景才用）。
- 与已知因子的冗余关系（ρ≥0.7 时提醒勿重复入模）。
- 复现命令（与 manifest 一致）。
- 已知陷阱 / 失效场景（如特定牛熊阶段、流动性枯竭）。

### 3.3 `correlation.csv`（相关性测试 / 冗余度）
- 格式：对称相关矩阵 `factor × factor`，值 = 截面 Pearson ρ 的时序均值（或 Spearman，manifest 注明）。
- **行/列 = 标准因子动物园 + 内部因子**：
  - 动物园（Phase 1 需实现的基准因子）：`momentum`(20d 漂移) / `reversal`(5d 短期反转) / `size`(log 总市值)
  - 内部：`ivol` / `overnight_intraday` / 组合（如有）
- 目的：揭示本因子与已知因子的冗余度（ρ≥0.7 视为高度冗余，交出去要特别提醒）。
- ⚠️ 依赖：动物园因子当前**未实现**（validator 里的 reversal/momentum 是基准收益组合，非因子面板）。见 §5。

### 3.4 `backtest_<pool>.csv`（回测数据）
- 列：`date, ls_ret_gross, ls_ret_net, cum_gross, cum_net`（多空组合，按因子值分组 top/bottom 多空）。
- 统计段（同 card 验证指标或单独表）：total_return / Sharpe / MaxDD / 双边换手(年) / 成本模型说明。
- **必须含成本与不含成本两列**——策略研究员据此判断容量与净 alpha（overnight_intraday 成本敏感性高，已在 card 标注）。
- 多池子各一份（呼应因子-池子配对）。

### 3.5 `overfit_audit.json`（过拟合信任证书）
- 字段：`dsr`(≥0.95 PASS) / `pbo`(≤0.25~0.30 PASS) / `n_trials`(含符号翻转等试过的方向数) / `pass`(bool) / `method`(CSCV S=12)。
- 直接复用 `validate/overfit_audit.py` 的输出，机器可读，策略研究员可自动筛选通过审计的因子。

### 3.6 `manifest.yaml`（元数据 / 溯源）
```yaml
fcode: f0001a                  # 交付编号（§7）；文件夹名与之一致
factor: overnight_intraday
version: 1.0.0
doc_rev: 1                     # 纯文档修订（不改变因子值）累计；升字母时归 1
status: current               # current | superseded
supersedes: null              # 被本版取代的旧 f-code（如 f0001a 取代 f0001_旧）
components: null              # 组合包填成分 f-code 列表，如 [f0001a, f0002a]
generated: 2026-08-05
contract_version: 1            # data/contract.py 版本号（防火墙基准）
provider: baostock             # 数据源
adj_policy: qfq                # 复权口径（必须与契约一致，否则 fail-loud）
universe: hs300                # 主场池
window: {start: 2020-01-01, end: 2026-08-04}
neutralization: industry+mktcap # 交付因子值的中性化状态（Phase 2 parquet 用）
pit_certified: true            # 严格 point-in-time
reproduce: "FF_PROVIDER=baostock python scripts/real_research.py --factor overnight_intraday --pool hs300"
known_limits:
  - "1日反转换手极高，净alpha对成本敏感"
```
- 策略研究员 6 个月后重跑可完全复现。

## 4. 分期

- **Phase 1（hs1800 缓存拉完后即可）**：`_INDEX.md` + 每因子 `card.md` / `correlation.csv` / `backtest_*.csv` / `overfit_audit.json` / `manifest.yaml`。不含 parquet。
- **Phase 2（后续）**：补 `panel_<pool>.parquet`（合约合规因子值），策略研究员直接 load 进选股回测。

## 5. 依赖 / 待办

- [ ] 实现 3 个基准因子（遵循 `Factor` 接口 + `contract`）：`momentum`(20d) / `reversal`(5d) / `size`(log mktcap)。用于相关性动物园。
- [ ] `factor_universe_matrix.py` 跑全 6 池（hs1800 拉完触发）→ 填主场池。
- [ ] `monthly_review.py baseline/report` 首期月报（健康度/衰减/拥挤/归因/墓地复检）。
- [ ] 新增 `scripts/build_deliverable.py`：读缓存 + 产出上述四层文件到 `deliverables/factors/<f-code>/`，并同步 `_REGISTRY.csv` / `_INDEX.md`。
- [ ] 落地编号：历史因子 retro-fit 为 `f0001a`(overnight_intraday) / `f0002a`(ivol)；首个组合预留 `f0003a`。
- [ ] 在 `card.md` 模板补「消费指引」段（§3.2），`build_deliverable.py` 生成时填实。

## 6. 验收标准

- 策略研究员拿到任意单因子包，无需读源码即可：知道因子是什么、怎么复现、因子值是否中性化/PIT、与已知因子冗余度、含成本回测表现、过拟合审计是否通过。
- 每个因子/组合包**含强制 `card.md` 详细说明文档**（含消费指引段）。
- 每个交付物有唯一 `f-code`，可在 `_REGISTRY.csv` / `_INDEX.md` 中查到谱系、版本、状态、成分。
- 所有数字来自 westock/baostock 连接器或已验证缓存，无编造；单位/代码/复权口径与 `contract.py` 一致（防火墙不破）。

## 7. 编号规则（f-code 交付编号）

> 用户对交付物编号的约定（2026-08-05）：用 `f` + 数字 + 字母，数字区分"大的因子/因子组序列"，字母区分"因子或因子组微调后的版本"。以下为落地细则。

### 7.1 格式
`f` + 4 位零填充数字 + 小写字母，例：`f0001a`、`f0001b`、`f0002a`。
- `f`：factor deliverable 前缀。
- `NNNN`：**谱系号**（0001–9999）。每个不同的因子或因子组占用一个号码，谱系内共享，不因微调改变。
- `x`：**版本字母**（a–z）。同一逻辑、不同微调 → 一个新字母。

### 7.2 号码分配
- 新因子 / 新组合 → 取 `_REGISTRY.csv` 中当前最大号码 +1，**集中分配，禁止私下占用**。
- 号码 = 因子谱系（不因微调变）；字母 = 版本（微调升字母）。

### 7.3 字母升位触发条件
以下任一改动使交付因子值变化 → **升字母**（新建文件夹，旧版保留不覆盖）：
- 参数重调（窗口 / 阈值 / 加权）
- 中性化范围变化（raw → industry → industry+mktcap）
- 主场池 / 宇宙变化（hs300 → hs800）
- 数据源 / 复权口径变化
- 符号约定翻转
- 组合方法变化（等权 → ICIR 加权 → 正交化）

**纯文档 / 说明澄清、不改变因子值** → **不升字母**，仅 `manifest.yaml` 的 `doc_rev` +1（如 `f0001a.doc_rev=2`）。

### 7.4 组合编号
组合是独立交付物 → 占**独立号码**（如 `f0003`），与单因子**平级**置于 `deliverables/factors/<f-code>/` 下，**不单独开 `combos/` 子层**。成分因子在 manifest 的 `components: [f0001a, f0002a]` 声明，便于溯源与下游复用。组合与单因子唯一的目录层差异是：组合包内 `manifest.components` 非空、`card.md` 显式声明其为组合——结构完全一致，下游检索路径统一。

### 7.5 已落地映射（历史因子 retro-fit）
- `f0001a` = overnight_intraday（v1，当前）
- `f0002a` = ivol（v1，当前）
- `f0003a` = 首个组合（待建）

### 7.6 边界
- 字母默认 a–z（26 版 / 谱系）。超 26 微调版用双字母（`aa`、`ab`…），极罕见。
- 经济性逻辑发生**根本性改变** = 视为**新因子** → 新号码，而非新字母。

### 7.7 注册表
- `_REGISTRY.csv` 字段：`fcode, name, type(single|combo), components, status(current|superseded), supersedes, created, note`。
- `_INDEX.md` 是其人类可读镜像；`build_deliverable.py` 写包时同步更新两者，保证编号权威、可防碰撞。
