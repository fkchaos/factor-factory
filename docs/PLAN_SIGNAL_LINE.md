# 双线架构规划 · 时序信号产品线（Signal Line）

> 状态：规划已定，骨架搭建中（2026-08-07）
> 决策来源：用户确认「做择时层 / 新建时序信号产品线 / 两条线或两事业部 / 框架逻辑同横截面因子」

---

## 0. 一句话定位

**横截面因子线（Factor Division）** 给"每只股票"打分，用于选股排序；
**时序信号线（Signal Division）** 给"整个市场"判状态，用于仓位开关 / 风险预算 overlay。
两条线**纪律完全相同**（灵感池漏斗 → 防前视 → 过拟合审计 → 编号交付 → 月度监控），**检验指标与交付物不同**——这是唯一差异，也是上次 v75 复盘识别出的盲区。

---

## 1. 为什么必须分两条线（不是把择时塞进因子组）

| 维度 | 横截面因子（每股一个值） | 时序信号（市场一个值/日） |
|---|---|---|
| 本质 | 对股票排序选股 | 判断"该不该交易 / 加减仓" |
| 检验 | RankIC / ICIR / 分层回测 | 状态命中率 / 叠加后 Sharpe·DD 改善 / 状态转移 |
| 交付物 | 因子值面板 + IC 证据 | 状态定义 + 状态序列 + 各状态绩效 |
| 消费方式 | 进选股模型打分 | 组合层 overlay（仓位开关） |

**硬塞的后果**：市场级信号每天给所有股票**同一个值**，放进因子组合后横截面贡献 ≡ 0，RankIC 直接算成 0，被误判"弱因子砍掉"。v75 复盘就是活例子——突破因子全局 IC -0.014 看着像弱信号，分状态后强势期 IC 转正 +0.009。

---

## 2. 目录与契约映射（平行镜像）

| 因子线（已有） | 信号线（新建） | 说明 |
|---|---|---|
| `factors/` | `signals/` | 实现目录 |
| `factors/interface.py` (Factor Protocol) | `signals/interface.py` (Signal Protocol) | 接口 + 注册表 + 防前视 |
| `factors/*Factor.py` | `signals/*Signal.py` | 具体实现（鸭子类型，类名结尾） |
| `deliverables/factors/_REGISTRY.csv` (f-code) | `deliverables/signals/_REGISTRY.csv` (s-code) | 交付注册表 |
| `validate/validator.py` (RankIC/ICIR/分层) | `validate/signal_validator.py` (状态绩效/叠加) | 检验模块 |
| `scripts/build_deliverable.py` | `scripts/build_signal_deliverable.py` | 交付构建 |
| `docs/factor_board.html`（单源） | 同文件、新增「时序信号」段 | 看板双段 |
| `research/idea_backlog.csv` | 同文件、`signal_type` 字段区分 | 灵感池共用 |

**编号**：因子 `fNNNNx`、信号 `sNNNNx`，各自独立计数，避免混淆。

---

## 3. Signal 接口契约（`signals/interface.py`）

```python
@runtime_checkable
class Signal(Protocol):
    name: str
    def compute(self, panel, as_of_date, ctx=None) -> float:
        """返回 as_of_date 当日的**市场级状态标量**（对所有 asset 聚合后的单一值）。
        必须只使用 as_of_date 及之前的数据（防前视，CI 强制）。"""
```

- 与 Factor 一样强制 `as_of_date` + `assert_no_lookahead`。
- 信号计算在 `compute` 内对当日 panel 做**横截面聚合**（如涨跌家数占比），返回标量。
- `build_signal_deliverable` 逐日调用 `compute` → 得到 (date → 状态标量) 序列。

---

## 4. 信号检验指标（`validate/signal_validator.py`）

不用因子 RankIC，改用：

1. **状态定义**：连续值 → 离散状态（阈值文档化，如 breadth_MA20 > 0 → risk_on）。
2. **各状态预测力**：样本数 + **未来 N 日收益/胜率**（fwd_ret_1d/5d/20d）为准；同期口径（`*_contemp`）仅作诊断。
3. **方向命中率**：T 日状态 → **T+1 日**收益是否为正；`hit_spread` = risk_on 次日上涨率 − risk_off 次日上涨率。
4. **叠加改善**：baseline = 全样本等权多头；overlay = 仅 risk_on 时持多（**已滞后 exec_lag**）。对比 Sharpe / 最大回撤改善幅度。
5. **状态转移矩阵 + 切换率**：状态切换频率（过高 = 抖动，需降频）。
6. **过拟合审计**：复用 `validate/overfit_audit.py` 的 DSR/PBO（把 overlay 策略收益序列喂入）。

### 4.1 ⚠️ exec_lag 红线（信号线专属，血泪）

时序信号最容易翻车的地方**不是前视取数，而是前视回测**：

- `Signal.compute(panel, T)` 只用 T 日及之前数据 → 取数层没问题，`assert_no_lookahead` 也过。
- 但如果回测写成 `state[T] × ret[T]`，等于**用 T 日收盘才知道的状态去赚 T 日的钱**。
- 对 breadth 这类「当日涨跌家数统计」型信号，这几乎是同义反复 —— 会造出 Sharpe 5+ 的假象。

**强制约定**：
- `state_performance(..., exec_lag=1)`，overlay 一律用 `state.shift(exec_lag)`。
- `build_signal_deliverable.py --exec-lag` 默认 1，**传 0 直接拒绝出包**（exit 2）。
- 基准收益序列 `bench_ret[t]` 约定为 **t 日当天已实现收益**（`close_t/close_{t-1}-1`），
  **不是** t→t+1 前向收益。滞后统一由验证器负责，两边都滞后 = 双重滞后，指标会被莫名压平。
- 卡片同时打印 `_contemp_sharpe_ref`（同期口径参照）：两者差距越大，说明信号越依赖当日信息。
- CI 守护：`tests/test_signal_line.py::test_overlay_uses_exec_lag_not_contemporaneous`
  与 `::test_exec_lag_zero_reproduces_contemporaneous` 正反双向锁死。

---

## 5. 交付物（`build_signal_deliverable.py`）

产出 `deliverables/signals/<s-code>/`：
- `card.md`：状态定义 + 逻辑一句话 + 各状态绩效表 + 叠加改善 + 消费指引
- `state_sequence.csv`：date, raw_value, state
- `state_performance.json`：各状态统计 + 叠加改善 + 转移矩阵
- `overfit_audit.json`：DSR/PBO 信任证书
- `manifest.yaml`：元数据/溯源

---

## 6. 首个信号：`breadth_regime`（s0001x）

v75 复盘核心洞察：**最优表现来自广度过滤 = regime 选择器**。直接做广度 regime 信号：
- raw = 每日 (上涨家数 − 下跌家数) / 总数，或上涨家数占比
- 状态：breadth_MA20 > 0.5 → risk_on；< 0.5 → risk_off
- 从 `BaoStockProvider(universe=hs800/ALL)` 缓存 panel 计算，零新增数据源

---

## 6.1 信号灵感池（2026-08-08 建，驱动器 cron 自主推进）

原计划只定义了首个信号、灵感池为空 → 第二个 s-code 无候选可 promote。此处补齐，
纪律与因子线灵感池一致：**每条必须是可证伪假设 + 明确状态定义 + 数据可得性**。

**筛选约束（信号线专属，三条硬门）**：
1. **零新增数据源优先**：能从 `.cache/baostock` 日 K panel 算出的排最前。
2. **raw 必须自带零中枢**：出包脚本的状态转换是 `MA(raw, W) > threshold`，默认 threshold=0。
   若 raw 恒正（波动率、离散度这类），就必须人为挑一个阈值——**而"挑一个好阈值"本身
   就是全样本窥探**，属隐性前视，和 exec_lag 是同一类错误。故 raw 一律设计成
   **差值型（A 组 − B 组）**，阈值 0 才不需要拟合。
3. **compute 单日成本 O(截面)**：`build_signal_series` 对每个交易日调一次 compute 且传全 panel
   （约 2800 日）。需要长回看窗（如 250 日滚动 z-score）的定义会把出包从分钟级拖到小时级，
   除非先做缓存层——暂不上。
4. **🔴 用到的每个面板字段都要先验 PIT**（2026-08-08 新增，血泪）：面板列不一定是
   point-in-time 的。`market_cap` 就是 provider 拿**今日快照** `map` 到全部历史日期的
   假 PIT 列（时序 nunique==1），拿它分历史市值档，2013 年的分组一致率只有 53.7%，
   且"小盘组"= 到今天仍然小的公司 = 后视选股。**`assert_no_lookahead` 查不出这类问题**
   （它只管 compute 有没有切到 t 之后的行，不管列本身是否被未来信息污染）。
   新信号用到任何"基本面/股本/市值"类字段前，先 `nunique()` 看它随不随时间变。
   已知安全替代：`data.pit.pit_float_mcap()`（= amount / (turnover/100)，全为当日观测量）。

| # | 候选 | raw 定义 | 类别 | 零中枢 | 单日成本 | 优先级 |
|---|---|---|---|---|---|---|
| 1 | **风险偏好 Regime**（小盘−大盘） | 小市值组均值收益 − 大市值组均值收益（市值须用 PIT 口径，见硬门 #4） | sentiment | ✅ 天然 0 | O(截面) | **P0 → 本轮实现 s0002x** |
| 2 | 量能 Regime | 成交额 MA5 / MA60 − 1 | volatility | ✅ 天然 0 | 需回看 60 日 | P1（等缓存层） |
| 3 | 趋势 Regime | 等权指数收益 MA60 | trend | ✅ 天然 0 | 需回看 60 日 | P1（与广度可能高相关，须先测相关性） |
| 4 | 波动 Regime | −(20 日已实现波动 z-score) | volatility | ⚠️ 需 250 日分布 | 重 | P2（先做缓存层再上） |
| 5 | 涨跌停情绪 | (涨停数 − 跌停数)/总数 | sentiment | ✅ 天然 0 | O(截面) | P1（需先确认 baostock 可识别涨跌停板） |

### 本轮实现：`risk_appetite`（s0002x · 风险偏好 Regime）

- **可证伪假设**：小盘股相对大盘股走强 = 市场风险偏好上行，此时横截面 alpha 因子
  （尤其反转/低波这类小盘敏感因子）更容易赚钱；反之资金抱团大盘 = 避险，应降暴露。
  证伪条件：risk_on 与 risk_off 两态的未来 1 日收益无显著差异，或叠加后 Sharpe/MaxDD 均不改善。
- **raw**：`小盘组(后 30%)日收益均值 − 大盘组(前 30%)日收益均值`，收益取 prev→as_of。
- **市值口径（实现时被迫改过一次，记录在案）**：原计划写的是"按面板 `market_cap` 分档"，
  实现前冒烟发现该列是**今日快照回填全历史**的假 PIT 数据（详见硬门 #4）。改为
  `data.pit.pit_float_mcap()` 现算 **PIT 流通市值 = amount / (turnover/100)**，
  取**前一交易日**截止的近 5 日中位数：
  - 用 PIT 而非快照 → 消除后视选股；
  - 用**前一日**而非当日 → 防"今天大涨的票被今天涨幅推高市值排名"的**排序污染**
    （不是前视，但同样造假区分度）；
  - 取 5 日中位数 → 压掉停牌复牌/单日换手异常砸出的天量市值。
  成本仍是 O(5×截面)，与 breadth 同量级。回归测试见 `tests/test_pit_mcap.py`
  （含"把 market_cap 整列污染，信号值必须不变"的防回归断言）。
- **状态**：`MA20(raw) > 0` → risk_on（风险偏好上行）；否则 risk_off。阈值 0 无需拟合。
- **与 s0001x 的区别**（避免造重复信号）：breadth 量的是**参与度**（多少只股票在涨），
  risk_appetite 量的是**风格偏好**（钱往大盘还是小盘去）。两者可同涨同跌，但在
  "指数涨、小盘杀"的抱团行情里会分叉——出包后须报告两者**状态一致率**，
  一致率过高（>85%）说明信息重复，应降级或弃用。

---

## 7. 看板（单源双段）

`docs/factor_board.html` 保留单一文件，顶部 tile 增加「时序信号」计数，新增 section：
- 已交付信号（signals/_REGISTRY.csv）
- 研究中信号（signals/*.py Signal 类）
- 信号灵感（idea_backlog 中 signal_type=signal）

---

## 8. 红线（双线通用 + 信号专属）

通用：灵感池可证伪假设 → 防前视 → DSR/PBO 门禁 → 月度监控。
信号专属：
- **exec_lag ≥ 1 强制**：见 §4.1。同期口径回测禁止出包，CI 双向锁死。
- **不产出风控参数**（止损/止盈/仓位由策略组负责，已确认"没有就没有"）。
- **不设质量出库门槛**：我们生产因子/信号，质量高低由策略组选择（用户决策 4）。
  注意：不设门槛 ≠ 不设**真实性**门槛 —— DSR/PBO 与 exec_lag 属于"数字真不真"，与"好不好"无关，
  这两道闸永远不放。给策略组一个假 Sharpe 比不给更糟。
- **calc_factors 签名待对方提供**：开放接口契约，见 `docs/INTERFACE_CONTRACTS.md`，不阻塞研发。

---

## 9. 自动化（cron 双线自驱）

- **驱动器（每日 21:00）**：因子线推进 P4/P5/P7/f0003a + **信号线推进首个 s-code 构建** + 刷新看板 + 同步 HANDOFF。
- **看门狗（每日 21:30）**：新增 `signals/_REGISTRY.csv` 存在性 + 信号状态 flag 巡检。
- 两者均带 `cd` 兜底，避免 cwd 错乱（历史教训）。

---

## 10. 测试池补全（因子线决策 5）

因子交付覆盖全 6 池（sz50/hs300/zz500/hs800/zz1000/hs1800），不再只测 sz50。
`build_deliverable.py` 卡片改多池 IC 表；后台重跑 f0001a/f0002a/f0003a 覆盖全 6 池。

---

## 11. 路线图

- **P0（本周）**：骨架 + breadth_regime 首个 s-code + 看板双段 + HANDOFF/cron 双线化 + 6 池补全
- **P1**：分状态 IC（因子线，v75 盲区①）+ IC 衰减 + 经济逻辑长文（需求对接项）
- **P2**：信号线第二个信号（趋势/波动 regime）+ 信号叠加到 f0003a 组合做"因子+择时"联合交付样例
- **P3**：calc_factors 签名对齐（待对方提供后）
