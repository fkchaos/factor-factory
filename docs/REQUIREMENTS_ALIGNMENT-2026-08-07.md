# 因子交付 × 策略组需求 对齐分析 v2

> 日期：2026-08-07（v2 更新）| 对齐方：factor-factory（因子/信号研发生产线） vs a-share-quant-sim（策略生产线）
> 需求来源：
> - `docs/experiments/2026-08-07_strategy_input_requirements.md`（三层输入项 consolidated v1.0：**版本化命名 + 精确 JSON schema + §7.2 验证门槛**）
> - `docs/experiments/2026-08-07_strategy_rnd_framework.md`（策略研发 6 阶段流程，**揭示我们交付物如何被消费**）
> v1 基线：`docs/experiments/2026-08-07_factor_requirements_spec.md`（早期 stock 单线 spec）

---

## 0. 一句话结论（v2 更新）

选股因子层 **~70% 可对接**（差量 = 分 regime IC / IC 衰减 / 经济逻辑长文 / JSON 适配器）；**择时信号层已从 v1 的「~0%」跃升为「已具备交付能力」**——时序信号产品线已立（s0001x breadth_regime + signal_validator + exec_lag=1 防护），天然命中 regime 类；风控参数层 **0% 且正确不出**（边界已划清）。即我们实际能覆盖对方三层里的 **2/3**。

**v2 头号协作风险**：对方《研发框架》全文**零提及**执行 lag / 前视 / shift / T+1，而我们把 `exec_lag=1` 焊死在信号线。交付择时信号时**必须盖 lag 钢印**，否则他们用同期收益评估会复现我们刚堵掉的 Sharpe 虚高（5.99→5.15 那一类）。

---

## 1. 供给侧快照（不变）

已交付 3 个横截面因子包（f0001a / f0002a / f0003a）+ 1 个时序信号包（s0001x，待今晚 21:00 驱动器出包），每包内含：

| 文件 | 内容 | 对应需求 |
|---|---|---|
| `card.md` | 验证指标表 + 消费指引（方向、中性化、PIT、主场池、复现命令、已知陷阱） | 因子说明 + 部分验证 |
| `manifest.yaml` | 元数据（fcode/scode、provider=baostock、adj=qfq、window、neutralization、pit_certified、reproduce 命令） | 数据源说明 + 溯源 |
| `metrics_<pool>.json` | IC（rank_ic / icir / ic_win_rate / n_days）+ 回测（gross/net 的 ann_ret / sharpe / max_dd）+ cost_rate | IC/IR + 回测 |
| `overfit_audit.json` | DSR / PBO / verdict / n_trials / n_splits | 过拟合审计 |
| `correlation.csv` | 因子间相关性矩阵 | 因子相关性（可选交付） |
| `backtest_<pool>.csv` | 逐日因子值 + 净值序列 | 回测明细 |
| *(信号线)* `state_sequence.csv` / `state_performance.json` | 市场级状态序列 + 各状态绩效（fwd_*, exec_lag=1）+ 转移矩阵 | 择时信号 |

**实测数据（以 f0001a 为例，sz50 池）**：rank_ic=0.0102，icir=0.074，ic_win=51.9%，sharpe_net=0.426，max_dd_net=-35.89%，DSR=1.0。六池回填（yAi3H2 后台）完成后见 §5.3。

---

## 2. 逐层对照（v2 更新）

### 2.1 选股因子层（stock）—— 满足度 ~70%

字段级对照（对方 JSON schema ↔ 我们现状），详见 §6。核心结论：格式能对上，**但缺三块元数据**（分 regime IC、IC 衰减、经济逻辑长文）和一个 JSON 适配层；`type/category/source` 标签需显式补。

### 2.2 择时信号层（timing）—— **从 ~0% → 已具备交付能力（v2 重大更新）**

v1 结论「需新建时序信号产品线，否则 0%」——现已建成（用户 5 项决策后）：

- 长线镜像：`signals/` 目录 + `interface.py`（Signal Protocol，compute 返回**市场级标量**而非逐股 Series，这是与 Factor 的本质分界）+ `_REGISTRY.csv`（s-code）+ `breadth_regime.py`（首信号 s0001x，v75 复盘「广度过滤=regime 选择器」洞察，零新增数据源）+ `validate/signal_validator.py`（状态预测力/方向命中/叠加改善/转移矩阵 + DSR）+ `scripts/build_signal_deliverable.py`（s-code 包）。

**对方 timing 字段 ↔ 我们 s-code 交付规格映射**：

| 对方字段 | 我们对应 | 判定 |
|---|---|---|
| `name` | s-code（如 s0001x） | ✅ |
| `type` | 显式 `timing` | ✅（包内标注） |
| `category` ∈ regime\|sentiment\|trend\|volatility | s0001x = `regime`；其余 3 类待建信号 | ⚠️ 仅 regime 有 |
| `trigger_logic` | 状态切换条件（广度阈值） | ✅ |
| `position_logic` | overlay 规则（state.shift(1) 叠加） | ✅ |
| `thresholds{high,low}` | 广度上下阈值 | ✅ |
| `backtest_sharpe` | `fwd_sharpe`（exec_lag=1 口径） | ✅ |
| `win_rate` | 状态方向命中率 | ✅ |
| `regime_dependency` | 强/弱市依赖（待量化） | ⚠️ 待补 |
| `decay_status` | 半衰期（待量化） | ⚠️ 待补（P0 半衰期补丁） |
| `source` | `external`（我们产） | ✅ |
| `description` | card 一句话 | ✅ |

**缺口（待补）**：①category 枚举完整（sentiment/trend/volatility 需新建信号）；②decay_status/regime_dependency 量化（P0 半衰期补丁）；③JSON 适配器尚未写（见 §5.1）。

### 2.3 风控参数层（risk）—— 0% 且正确不出

对方要 stop_loss / take_profit / hold_days_max / max_position / max_holdings + backtest_sharpe + max_drawdown。**这是策略层的事，因子/信号工厂不交付**。我们仅提供「因子层面风险属性」（最大回撤 / 成本敏感性 / 中性化状态），对接时应明确划界，避免对方误以为我们会交止损止盈参数。

---

## 3. 格式适配（v2：直接落 alpha-research/inputs）

对方选股因子是扁平 JSON（§3.1），我们是多文件包。技术上可适配：每个 JSON 字段都有数据源（ic_mean←metrics.rank_ic，ir←metrics.icir，direction←card，data_source←manifest…），写 `export_to_strategy_json.py` 聚包成对方 schema 即可（工作量小，见 §7 P1）。

**v2 新增落点**：对方框架**阶段 0** 把全部外部输入归一化为 `alpha-research/inputs/{stock_factors,timing_signals,risk_params}.json` 并标 `source=external`，阶段 1 按类型用 §7.2 验证。→ 我们的适配器直接产出该 schema，**预填阶段 0**，让他们的阶段 1 直接吃。

---

## 4. 关键卡点（v2 精简，待对方/用户拍板）

1. **calc_factors 签名**：开放契约已写 `docs/INTERFACE_CONTRACTS.md`（对方未给签名，我方当开放契约处理）。新文档 §4.1 仍要求「符合 calc_factors 签名规范」——需确认是他们提供签名还是我们提供。
2. **因子质量门槛**：决策 4 = 我们**不出内部门槛**，好坏由策略组 §7.2 gate。但为避免他们阶段 1 surprise-reject，我们应**预跑 §7.2 贴徽章**（见 §5.3）。
3. **测试池**：六池回填（yAi3H2 后台）完成后，卡片/看板补 zz1000/hs1800——届时 f0001a 在该池实际**过 §7.2**（详见 §5.3）。
4. **择时信号前视口径**：必须盖 `exec_lag=1` 钢印（见 §5.4），这是 v2 头号风险。

---

## 5. 协作机制关键发现（v2 新增）

### 5.1 消费流：我们的 JSON → 他们的阶段 0

框架阶段 0–5：阶段 0 归一化全部外部输入为标准 JSON（`alpha-research/inputs/*.json`，`source=external`）→ 阶段 1 按类型用 §7.2 验证 → 阶段 2 策略构建 → 阶段 3 验证（全量回测→Walk-Forward→压力测试）→ 阶段 4 集成上线 → 阶段 5 持续监控。

→ **行动**：写 `export_to_strategy_json.py`，把 f-code / s-code 包聚合成他们 `inputs/*.json` 的精确 schema（补 `type/category/source` 标签），预填阶段 0。这样他们阶段 1 直接吃，不需二次搬运。

### 5.2 §7.2 三类型验证门槛（verbatim）

| 类型 | 有效（valid） | 证伪（refuted） |
|---|---|---|
| **stock** | \|IC Mean\|>0.03 **且** \|IR\|>0.3 | \|IC\|<0.01 **或** \|IR\|<0.1 |
| **timing** | backtest_sharpe > 1.5 | backtest_sharpe < 1.0 |
| **risk** | backtest_sharpe > 1.0 | backtest_sharpe < 0.8 |

（介于两者之间 = 灰区，需人工判断。）

### 5.3 判决随池子翻转（关键！）

f0001a 按 §7.2 逐池判决（sz50/hs300/zz500/hs800 已出，zz1000/hs1800 回填中）：

| 池 | IC | ICIR | §7.2 判决 |
|---|---|---|---|
| sz50 | 0.0102 | 0.074 | **证伪**（IR<0.1） |
| hs300 | 0.0258 | 0.260 | 灰区 |
| zz500 | 0.0256 | 0.263 | 灰区 |
| hs800 | 0.0260 | 0.278 | 灰区 |
| zz1000 | 0.0309 | 0.34 | **有效**（IC>0.03 & IR>0.3） |
| hs1800 | (回填中) | (回填中) | 待 |

→ **「因子质量」是池子函数**：单看 sz50 显式「证伪」，看 zz1000 却是「有效」。**我们交多池 IC 表、让策略组自己选主场**，比单池 sz50 显式证伪公平得多——这也是决策 4「不出内部门槛」的正确落地方式：原始多池数据全给，判定权交给对方 §7.2 + 他们的域选择。

### 5.4 头号风险：前视盲点（v2 头号）

对方《研发框架》**全文零提及** exec_lag / 前视 / shift / T+1 / lookahead。我们信号线已强制 `exec_lag=1`（`fwd_*` 主表 vs `*_contemp` 同期诊断，两者差距 = 信号对当日信息的依赖度）。

危险场景：若他们用**同期收益**（`ret[T]`）评估我们的择时信号，会复现我们刚堵掉的虚高——breadth 类信号实测 Sharpe 从真值 5.15 被撑到 5.99（合成 AR(1) 强持续差距小，真实数据差距会更大）。

→ **行动**：每个择时交付包（card / manifest / JSON 适配器输出）**显式标注 `exec_lag=1` + 「禁止用同期收益评估本信号，须 shift(1)」**，并在适配器里写入该字段，堵死对方框架的盲点。

---

## 6. 字段级对照表（v2 精确化）

### 6.1 选股因子（stock）

| 对方字段 | 我们现状 | 判定 |
|---|---|---|
| `name` | card 中文名 + fcode | ✅ |
| `type` | 隐含，无显式 "stock" | ⚠️ 补 |
| `category` (technical/fundamental/alternative) | 隐含，无显式标签 | ⚠️ 补 |
| `direction` | card 正向/负向 | ✅ |
| `data_source` | manifest: baostock/qfq | ✅ |
| `calc_logic` | card 一句话 + 复现命令 | ⚠️ 扩写完整逻辑 |
| `ic_mean` | metrics.rank_ic | ✅ |
| `ir` | metrics.icir | ✅ |
| `regime_dependency` | ❌ 无分 regime IC | ❌ P0 |
| `decay_status` | ❌ 无 IC 衰减 | ❌ P0 |
| `expiry_date` | 可 null | ✅ |
| `source` | 隐含 external | ⚠️ 补 |
| `description` | card 一句话 | ✅ |

### 6.2 择时信号（timing，v2 新增）

见 §2.2 映射表。要点：s-code 包已覆盖 name/type/category(regime)/trigger/position/thresholds/backtest_sharpe/win_rate/source/description；缺口是 category 完整枚举 + regime_dependency/decay_status 量化。

### 6.3 风控参数（risk）

我们不交付（见 §2.3）。

---

## 7. 差量补丁清单（v2 状态更新）

| 优先级 | 补丁 | 状态 | 说明 |
|---|---|---|---|
| **P0** | 分 regime IC | 待做 | validator + universe_matrix 按趋势/广度/波动分组算 IC |
| **P0** | IC 衰减分析 | 待做 | monthly_review 加滚动 IC + 近 12 月趋势 + 半衰期 |
| **P0** | 经济逻辑长文档 | 待做 | 每 f-code 补「为什么有效」章节 |
| **P0** | 信号半衰期量化 | 待做（信号线） | 供给侧 decay_status 数据来源 |
| **P1** | **JSON 适配器** `export_to_strategy_json.py` | 待做（**优先级上调**） | 直接落对方 `alpha-research/inputs/*.json`，预填阶段 0 |
| **P1** | 交易胜率 | 待做 | 回测脚本补 win_rate |
| **P1** | 数据源文档 | 待做 | 补更新频率 + 历史长度 |
| **P1** | **exec_lag 钢印** | 待做 | 每个择时包显式标注，堵对方前视盲点 |
| **P2** | 压力测试 / 参数敏感性 | 待做 | 不同市场环境表现 |
| **P2** | 全池交付 | 回填中（yAi3H2） | 交付包 metrics 补 zz1000/hs1800 |

> 备注：P0 三件（分 regime IC / 衰减 / 经济逻辑）在 v75 复盘就标记「该做」，现被外部需求正式确认——需求驱动，早做不吃亏。JSON 适配器 + exec_lag 钢印是本轮回应对方框架的**新增必做项**。

---

## 8. 给策略组的对接回复建议（v2 草稿）

> 我们可稳定交付**选股因子层**（横截面，含因子值面板 + 全局/多池 IC-IR + 过拟合审计 + 相关性 + 中性化/PIT 认证 + 复现命令）与**择时信号层**（s-code，市场级状态序列 + 各状态绩效 `exec_lag=1` 口径 + 转移矩阵 + DSR）。格式可经 `export_to_strategy_json.py` 直接适配为你们的 `alpha-research/inputs/*.json`（source=external），预填阶段 0。随包附 §7.2 **多池判决徽章**。
> **风控参数层**不在我们交付范围（止损/止盈/仓位由你们策略层自行集成，我们仅提供因子层面风险属性）。
> 需对齐：①你们的 calc_factors 签名规范；②我们交付多池 IC 表，§7.2 判定按池各自生效，请按你们的域选主场；③每个择时信号我们盖 `exec_lag=1` 钢印，**请勿用同期收益评估**，须 shift(1)。
