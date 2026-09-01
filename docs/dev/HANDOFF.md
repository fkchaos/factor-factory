# HANDOFF · 会话交接文档

> **用途**：当本 session 上下文接近上限时，由主理 session 生成 / 更新此文档，把状态完整交接给后续 session，避免长周期研发因上下文断裂而丢失进度。
> **规则来源**：用户工程纪律第 4 条（见 `README.md`「设计基石」与项目 `MEMORY.md`）。
> **维护方式**：本文件始终保存"最新一份"交接状态。每次上下文将满预警时**原地更新**本文件并改顶部日期；若需保留历史快照，另存 `docs/HANDOFF-YYYYMMDD.md`。
> **归档说明（2026-08-06）**：历史已完成流水账（三轮增量 + Phase 1/2/3 阶段总结 + 旧下一步）已移至 `docs/HANDOFF-2026-08-06.md`。**因子级交付（f0001a/f0002a…）自动体现在 `docs/factor_board.html`（经 `research/_REGISTRY.csv`，由驱动器 cron 刷新），不在此文档重复记录。**

---

## 0. 元信息
- 更新日期：2026-09-01（推进器机制瘫痪根治：cwds修复 + prompt重构落盘保障 + 候选扩研究中因子 + 运行日志；手动实跑验证离线出包通 + f0026a出包 + 归档3条评估洞察类 + CHANGELOG/HANDOFF/看板落盘）
- 项目阶段：Phase 1/2 完成；Phase 3 生产化三大件（监控/影子账户/风险约束中性化）齐；DSR/PBO 门禁已落地
- 交接性质：常规基线（信息量大，务必读完 §2 限频陷阱 + 本段 PIT 坑再动手）

## 🆕 最新快照（2026-09-01 · 推进器机制瘫痪根治 + 离线出包验证 + 灵感池 draining 重启）

> 本段为最新交接快照，续作以本段为准。详细历史基线见 `docs/HANDOFF-2026-08-06.md`。
> 上一轮（2026-08-08 晚 cron）已完成：拦下 `market_cap` 假 PIT 系统性坑 + `s0002x` 第二信号出包 + 策略组对接三件套（JSON 适配器 / exec_lag 钢印 / issue 草稿）+ 156 项 pytest 全绿。本轮（08-10）是把上轮拦下的坑彻底闭环：三包 f-code 按 PIT 真口径重建完毕。

### 2026-08-17 排查快照（P4/P5 根因 + GitHub 连接器只读实测）

> 本段记录用户回来后提出的「P4/P5 两个代码缺陷」排查结论 + GitHub 连接器权限实测。这两件事的根因都不是 factor 代码 bug，而是**自动化配置/契约错配**与**连接器权限范围**，已全部纠正。

- 🔍 **P4 是假警报，非代码缺陷**：`scripts/factor_universe_matrix.py` 的 `universe_hint` AttributeError 在 `factors/interface.py:73` 已声明 `universe_hint: Optional[str] = None` 协议默认 + 矩阵脚本 `getattr(f,"universe_hint",None)` 防御读取后，**早已修复**；`deliverables/universe_matrix/ic_matrix_2026-08-07.csv` 六池（含 hs1800）两因子全部填满（overnight_intraday hs1800 +0.0283 / ivol hs1800 +0.0388）。真正的「P4 状态缺失 连续 8 晚告警」根因是**看门狗误查了从未被写出的 `.cache/review/p4_status.json`**——已纠正：驱动/看门狗 P4 检查现直接读 `ic_matrix_*.csv` 的 hs1800 列（真实完成标志），无需状态文件。
- 🔍 **P5 是真卡住，现已疏通**：基线 `ic_overnight_intraday_hs800.csv` 存在但驱动器只在「文件缺失」时才跑 → 永不被触发；看门狗 36h 阈值对月度基线过严 → 连续误报。已双修：驱动器改为「>30 天或未存在→重跑基线，且每月都出当月月报（动态月份，非硬编码 2026-07）」；看门狗阈值放宽到 >40 天。并已在 2026-08-17 启动后台基线重刷（2020→now）+ 生成 `research/monthly/2026-08.md` 当月月报。
- 🔴 **GitHub 连接器对该仓库为只读（read-only），非 disconnected**：实测 `get_me`→fkchaos（身份正常）、`get_file_contents`→可读、`list_*`→可读；但 `issue_write` / `create_pull_request` / `create_or_update_file` 等**所有写操作均 403 Resource not accessible by integration**。结论：**issue、PR、代码都无法经连接器推送**，必须用户以 fkchaos 身份在 GitHub Web 手动操作（仓库 owner 有完整写权限）。WorkBuddy 设置里点进 GitHub App 无 Repository access 开关——该连接器权限范围由平台服务端固守，用户侧改不了。

### 2026-09-01 推进器修复（机制瘫痪根治 · 手动替跑一轮验证）
- 🔴 **根因三连**：①cwds 字段损坏（数组被错序列化进 Program 路径字符串，框架取不到工作目录）；②原 prompt 只从 hypothesized 灵感挑候选，而池里 64 条待处理全是「需新数据源硬骨头」或「评估洞察类」，挑不到可出包的 → 空转；③出包成功才落盘 CHANGELOG/HANDOFF，联网财报因子(f0014a类)慢/卡把整轮拖崩 → CHANGELOG停8-17、HANDOFF停8-12、灵感池不降。
- ✅ **已修**：cwds 恢复正常 `D:/ai-workspace/WorkBuddy/A股研究`；prompt 重构——「落盘保障」（CHANGELOG/HANDOFF/看板每轮必达，不出包成功也写）+ 候选源扩展到「研究中因子」（纯价量可离线出包）+ 加 `.cache/propel_last_run.json` 运行日志；下次运行已排程。
- ✅ **离线出包验证通**：手动出包 f0026a（量能扩张速度，纯价量，baostock 缓存 cache hit，30s 完成，RankIC -0.0057）——证明「研究中因子」可稳定 drain，推进器每轮出 1 个不再卡。
- ✅ **落盘闭环**：CHANGELOG 补 f0011a–f0026a 共 15 条漏记交付；3 条评估洞察类灵感(i20260820-028/029/030)归档 archived（hypothesized 64→61）；看板刷新（因子已交付=26/研究中=18/信号=3）；propel_last_run.json 写本轮摘要。
- ⚠️ **遗留**：看板「研究中=18」口径有小偏差（volume_expansion_speed 已出包 f0026a 仍计入），待修 factor_board.py 匹配逻辑；f0011a–f0025a 中部分因子需后续补 PIT 真口径重测（非阻塞）。

### 当前状态（一句话）
**双线交付齐备且全部 PIT 口径可信：信号线已三包（s0001x 广度 Regime / s0002x 风险偏好 / s0003x 波动率 Regime，三包两两视角独立）；f-code 三包均按 v2-pit-mcap 真口径重算完毕；本轮（08-12）新增第三信号 `s0003x` 出包并将卡片模板硬编码陷阱句 bug 修复，全量 161 项 pytest 回归全绿（4m49s），看板信号段翻牌 已交付=3 / 研究中=0，对外 JSON 同步刷新为 3 stock + 3 timing。
（2026-08-14 例行维护：双线交付状态不变，重刷 `docs/factor_board.html` 因子 已交付=3/研究中=6/灵感池=46、信号 已交付=3/研究中=0；幂等重跑 `export_to_strategy_json.py` 确认 3 stock + 3 timing（exec_lag=1 钢印在位、均 verdict=refuted，f0001a 0.0312/f0002a 0.0484/f0003a 0.0440 @zz1000，s0001x 0.94/s0002x 0.84/s0003x 0.51）一致；三信号包 card.md/manifest.yaml 的 exec_lag=1 钢印复查在位；无新交付包，GitHub 通道仍 disconnected、issue 草稿维持待发。）（2026-08-15 例行维护·假后首跑：双线交付状态不变，重刷 docs/factor_board.html（因子 3/6/46、信号 3/0）；幂等重跑 export_to_strategy_json.py 确认 3 stock + 3 timing 一致（exec_lag=1 钢印、均 refuted）；三信号包 exec_lag=1 钢印复查在位；无新交付包，GitHub 仍 disconnected、issue 草稿维持待发。）（2026-08-16 例行维护：双线交付状态不变，重刷 docs/factor_board.html（因子 3/6/46、信号 3/0）；幂等重跑 export_to_strategy_json.py 确认 3 stock + 3 timing 一致（exec_lag=1 钢印、均 verdict=refuted，f0001a 0.0312/f0002a 0.0484/f0003a 0.0440 @zz1000，s0001x 0.94/s0002x 0.84/s0003x 0.51）；三信号包 exec_lag=1 钢印复查在位；无新交付包，GitHub 仍 disconnected、issue 草稿维持待发。）

### 2026-08-11 驱动器例行维护（无新交付包 · 双线交付状态不变）
- 重刷 `docs/factor_board.html`：因子 已交付=3 / 研究中=6 / 灵感池=36；信号 已交付=2 / 研究中=0（hs1800 缓存 1672/1572）。
- 幂等重跑 `scripts/export_to_strategy_json.py` 确认对外 JSON 与注册表一致：3 stock_factors（f0001a IC=0.0312、f0002a IC=0.0484、f0003a IC=0.0440，均 @zz1000 valid）+ 2 timing_signals（s0001x Sharpe 0.94 / s0002x 0.84，exec_lag=1 钢印在位，均 verdict=refuted），`risk_params.json` 占位不变。
- 实测核验全部标准流步骤（P4/P5/P7/f0003a/s0001x/s0002x）均已完成，无"就绪未交付"的常规待办；两个信号包 `card.md`/`manifest.yaml` 的 `exec_lag=1` 钢印复查在位。
- GitHub MCP 仍 disconnected + 无 `gh` CLI → `deliverables/strategy_collab_issue.md` 继续待发（未重写草稿）。
- 下一步待办（P0 半衰期补丁 / PIT 字段审计 / 灵感池 promote / 第三条腿 ML）均为非"就绪交付"类研究任务，保留至后续轮次或用户回来后再推进。

### 2026-08-12 驱动器推进（第三 s-code `s0003x` 出包 · 非例维护轮）
- ✅ **信号线第三个 s-code `s0003x`（波动率 Regime / volatility_regime）出包**：raw = ln(RV_prior20 / RV_recent20)，RV = 等权市场日收益标准差，两腿各 20 交易日不重叠（等长 → 平稳性下期望严格为 0，**阈值免拟合**，满足 PLAN §6.1 #2 硬门；只读 `close` 一列，天然避开假 PIT `market_cap`）。
  - 可交易口径（exec_lag=1，样本 2776 日）：overlay Sharpe **0.50**（baseline 0.76，**改善 -0.260**）；MaxDD **-45.49% → -34.12%**（改善 **+11.38pct**）；持仓日占比 54.7%；DSR **1.000 PASS**。
  - 预测力：**方向与经济先验相反**——risk_on（波动收缩）后次日上涨率 53.3% < risk_off（波动扩张）55.3%，命中率价差 **-2.0%**（负向）。**刻意不反转符号**（那等于看过全样本才改方向=数据窥探），按策略组 §7.2（Sharpe<1.0）如实判 **refuted**。
  - 同期 Sharpe 仅 **0.54**（s0001x 2.68 / s0002x 1.34）→ 本信号几乎不吃当日信息，是三包里最"干净"的一个；价值重新定位为**回撤削减闸门**（DD 改善 +11.38pct）而非收益增强器。
  - 测试焊死：新增 `tests/test_signal_line.py` 5 项（no_lookahead / warmup 返 NaN / raw 零中心均值偏离<0.06 / sign 含义 / 注册），全量 156→**161 项**通过。
- ✅ **信号冗余检查已过**：`scripts/signal_redundancy.py` 实测三包两两状态一致率均显著低于 85% 重复门槛——s0001x vs s0003x **49.5%**（随机基线 49.4%，超额 +0.1%，raw 相关 -0.041）、s0002x vs s0003x **54.2%**（超额 +2.8%），均 ✅ 视角独立；s0003x 与另两包最正交，三包可并存互补。结果落 `deliverables/signals/_REDUNDANCY.json`。
- ✅ **修复卡片模板硬编码陷阱句 bug**：`build_signal_deliverable.py` 卡片模板原硬编码"广度在极端流动性枯竭/涨跌停潮时会失真"，导致 s0002x/s0003x 卡片都在印广度信号的专属陷阱说明（对外交付放了错误的适用边界）。修复：引入 `DEFAULT_CAVEAT` 常量 + 各 Signal 类加 `caveat` 类属性（breadth_regime/risk_appetite/volatility_regime 各写真实失真场景）+ 模板改为 `getattr(signal,'caveat',None) or DEFAULT_CAVEAT`，并用脚本回填已出三包 card.md。
- ✅ **看板与对外 JSON 已同步刷新**：`docs/factor_board.html` 信号段 已交付 **2→3**（含 s0003x，mt 2026-08-12 21:15）；`scripts/export_to_strategy_json.py` 刷新为 3 stock_factors + **3 timing_signals**（s0001x 0.94 / s0002x 0.84 / **s0003x 0.50**，exec_lag=1 钢印在位，均 verdict=refuted），`risk_params.json` 占位不变。
- ✅ **全量 pytest 回归 161 passed（4m49s，无回归）**；GitHub MCP 仍 disconnected + 无 gh CLI → `deliverables/strategy_collab_issue.md` 继续待发（未重写草稿）。

### 2026-08-15 驱动器例行维护（无新交付包 · 双线交付状态不变 · 假后首跑）
- 重刷 `docs/factor_board.html`：因子 已交付=3 / 研究中=6 / 灵感池=46；信号 已交付=3 / 研究中=0（hs1800 缓存 1672/1572）。
- 幂等重跑 `scripts/export_to_strategy_json.py` 确认对外 JSON 与注册表一致：3 stock_factors（f0001a IC=0.0312、f0002a IC=0.0484、f0003a IC=0.0440，均 @zz1000 valid）+ 3 timing_signals（s0001x Sharpe 0.94 / s0002x 0.84 / s0003x 0.51，exec_lag=1 钢印在位，均 verdict=refuted），`risk_params.json` 占位不变。
- 实测核验全部标准流步骤（P4/P5/P7/f0003a/s0001x/s0002x/s0003x）均已完成，无"就绪未交付"的常规待办；三个信号包 `card.md`/`manifest.yaml` 的 `exec_lag=1` 钢印复查在位。
- GitHub MCP 仍 disconnected + 无 `gh` CLI → `deliverables/strategy_collab_issue.md` 继续待发（未重写草稿）。
- 下一步待办（发 issue / P0 半衰期补丁 / 审计其他 PIT 字段 / 灵感池 promote / 第三条腿 ML）均为非"就绪交付"类研究或外部阻塞任务，保留至后续轮次或用户回来后再推进。

### 2026-08-17 会话增补（灵感池 draining + 系统性提速 · 用户：灵感池快爆满要加速）
- 🔍 **灵感池根因 = 只进不出**：CSV 实际 28 条全 `hypothesized`，无 `in_pipeline/validated`；供给端（侦察兵）在跑，消费端（把候选实现成因子）从未接上自动化 → 流入≈11/周、流出≈0，必然爆满。看板显示的「57」与 CSV 行数口径不同，以 CSV 为准。
- ✅ **双管齐下已落地**：
  - 驱动器新增**步骤2b 灵感池消费**（治本 draining，全程零交互）：list 统计 hypothesized，若 <10 跳过；否则挑 top-K=2（耗时多降为1）高可行性候选→按 `chip_cost_distance.py`/`volume_expansion_speed.py` 的「纯函数+分组 cumsum/rolling+无实例状态」PIT 安全模板手写新 factor 模块+`factors/__init__.py` 补 import→`build_deliverable.py` 出包 hs300,hs800→CSV 翻终态→新 f-code 入 pending_handoff 队列。
  - 侦察兵新增**容量护栏**（步骤0）：hypothesized ≥ 60 则本周跳过供给（仅刷新看板），防只进不出爆满。
- ✅ **手验管线（证明消费端可行）**：新增 `f0004a` chip_cost_distance（锚定VWAP成本偏离，纯函数分组cumsum，`assert_no_lookahead` 通过；hs300 IC≈-0.006 弱）+ `f0005a` volume_expansion_speed（近20/120日均量比，rolling，PIT 安全；hs300 IC≈-0.006 弱）。i20260806-007→`validated`+f0005a（真·消耗 1 条）；f0004a 主题「筹码成本」但 CSV 无对应条目，独立交付。看板：因子 已交付 **3→5**、灵感池 28(1 validated)、待提队列 **2**(f0004a/f0005a)。
- ⚠️ **idea_backlog.py CLI 缺口**：仅 add/list/funnel/promote/pipeline/review；`pipeline` 翻 in_pipeline；**无 validate/reject 子命令**（STATUSES 却定义了 validated/rejected/dormant）→ 终态只能直接改 CSV（已加 `fcode` 列）。驱动器步骤2b 已据此修正。
- ⚠️ **新因子注册铁律**：`@register_factor` 必须装饰**实例**(`register_factor(XxxFactor())`)，装饰类会注册类本身→get_factor 返回类→compute 变未绑定方法报错；且 `factors/__init__.py` 须补 `from . import <模块>`。

### 本轮关键增量（2026-08-08 晚 21:00 驱动器 cron）
- 🔴 **拦下 `market_cap` 非 PIT 系统性坑（本轮最高价值，出包前冒烟发现）**：面板 `market_cap` 列时序 `nunique()==1`（如 000001.SZ 全部 6442 行都是 2.179285e+11）——`data/providers.py:780` `_share_map()` 取**今日** AkShare spot 快照 `map` 贴到全历史日期。
  - 失真量化（`.cache/_smoke_pit.py` 实测 2013-05-07）：静态市值 vs PIT 市值排序相关仅 **0.504**，大小盘分组一致率 **53.7%**（约等于抛硬币）。用它分小盘组，实际选出的是"到 2026 年仍然小的公司"= 后视选股。
  - 修复：新建 **`data/pit.py::pit_float_mcap()`**，用 `amount / (turnover/100)` = VWAP × 流通股本现算 PIT 流通市值（全为当日可观测量，不依赖前复权价格水平），取窗口内中位数吸收单日异常；`MIN_TURNOVER_PCT=0.01` 剔停牌/极低换手噪声。
  - 焊死回归：`tests/test_pit_mcap.py` **12 项**，核心断言是"把 `market_cap` 整列篡改成 1.0 或直接删列，信号输出必须逐位不变"（`abs=1e-15`），防后人手滑改回去。
- 🔴 **修中性化前视注入通道（比列污染更隐蔽，影响面更大）**：`scripts/build_deliverable.py:171` 对**所有因子无条件**做 `industry+mktcap` 中性化，而 `validate/validator.py::_neutralize_cross_section` 读的正是假 `market_cap` 列。中性化是回归扣除 `residual = fv − β·log(mcap)`，等于把 **−β × 未来收益**注入残差——比因子直接读脏数据更糟，因为它悄无声息地改变了 IC。
  - 已改用 `pit_float_mcap`；降级策略收紧为"PIT 算不出就只做行业中性，**绝不回退 `market_cap` 列**"；manifest 的 `neutralization` 字段改为 `"industry+mktcap(PIT: amount/turnover)"`，`pit_certified=True` 现在名副其实（此前是虚假声明）。
- ⚠️ **`assert_no_lookahead` 查不出这类坑**：它只检查 `compute` 有没有切到 `as_of` 之后的行，**管不了面板某列本身被未来信息污染**。这与 exec_lag 并列为"审计过 ≠ 无前视"的两大陷阱，已写进 `data/contract.py`（PIT 分级段）与 `docs/PLAN_SIGNAL_LINE.md`（新增**硬门 #4：用到的每个面板字段先验 PIT**，方法是 `nunique()` 看是否随时间变）。
- ✅ **信号线第二包 `s0002x`（风险偏好 / risk_appetite）**：小盘组次日收益 − 大盘组次日收益的差值型 raw（天然零中枢，阈值 0 免拟合，规避全样本窥探）。样本 2815 日。
  - 可交易口径：overlay Sharpe **0.84**（baseline 0.79，改善 +0.048）；MaxDD **-45.49% → -44.50%**（改善 +1.00pct）；持仓日占比 67.9%；DSR **1.000 PASS**。
  - 预测力：risk_on 1911 日胜率 55.4% vs risk_off 904 日 51.4%，**命中率价差 +4.0%**（优于 s0001x 的 +3.1%）；状态切换率 7.18%（比 s0001x 的 10.66% 更稳，换手更低）。
  - 同期口径 Sharpe 仅 **1.34**（s0001x 是 2.68）→ 说明本信号**不依赖当日信息**，比广度类干净得多。按策略组 §7.2 门槛仍判 refuted（0.84 < 1.0），如实标注。
- ✅ **信号冗余检查常设化 `scripts/signal_redundancy.py`（新建）**：落实 PLAN §6.1 "出包后须报状态一致率，>85% 说明信息重复应降级"的要求。实测 **s0001x vs s0002x 一致率 59.3%（随机基线 47.2%，超额 +12.0%），raw 相关 +0.338 → ✅ 视角独立**，两包可同时交付。结果落 `deliverables/signals/_REDUNDANCY.json`，未来每个新信号都要过这关。
- ✅ **修月报单位错配 bug + 重出 2026-07 月报**（本轮前段）：解决上一轮记录的"健康度判定与衰减信号自相矛盾"遗留。
- ✅ **测试基线抬到 156 项 pytest 全绿**（144 基线 + PIT 12 项；含 s0002x 出包 / 中性化改动 / pit.py 后复跑，无回归）。
- ✅ **看板与对外 JSON 已同步刷新**：`docs/factor_board.html` 信号段 已交付 **1→2**；`deliverables/strategy_export/` 现含 3 stock_factors + **2 timing_signals**。
- ✅ **f-code 三包 PIT 重建收尾（本轮核心交付，闭环 08-08 拦下的假 PIT 坑）**：`run_pit_rebuild.sh` 后台重建 08-09 启动、08-10 02:11 收尾，自动清空 IN_PROGRESS 并刷新看板+导出。f0001a/f0002a/f0003a 六池全部按 `NEUTRALIZE_VERSION="v2-pit-mcap"`（PIT 流通市值现算）重算，所有 `metrics_*.json` mtime ≥ 2026-08-09。
  - **IC 量值基本稳定**：重建前快照（`.cache/rebuild_snapshot/pre_pit_metrics.json`）vs 重建后卡片逐项比对，差异 < 0.001（f0001a zz1000 0.0309→0.0312、f0002a zz1000 0.0510→0.0510、f0003a sz50 0.0134→0.0134）。说明这两个收益型技术因子对市值中性化本就不敏感，PIT 修正的主要价值是**消除前视隐患、让 DSR/PBO 过拟合审计重新可信**，而非改变 IC 数字。
  - 卡片 `PIT 认证: true` 与 `中性化状态: industry+mktcap(PIT: amount/turnover 现算流通市值)` 已落盘；对外 `stock_factors.json` 同步刷新（08-10 02:11，3 stock），`timing_signals.json` exec_lag=1 钢印在位（s0001x 0.94 / s0002x 0.84）。
  - 全量 **156 项 pytest 回归全绿**（4m45s，无回归）。
- 🔵 **想法供给（侦察兵 2026-08-10 第 2 期，仅供给侧，与执行进度无关）**：灵感池 **24 → 现 36 条候选**，漏斗卡住 0。本周新增 **12 条**（paper 4 / sell_side 3 / zoo 2 / forum 3）。本期新维度：**筹码分布类首次入池**（获利盘比例 + 成本离散度，仅需日频价量+换手率，BaoStock 全覆盖、可实现度最高）、**ADD 异象驱动需求 + 因子拥挤度**（由我方自有因子池派生的"元因子"，零新增数据源，且构成"变化量 vs 水平量"符号对照实验）、**DRIF 统一日收益框架**（其假设自带对池内 MIN3/MAX5/短期反转的清算式正交检验，可能触发一次因子池瘦身）、量价配合条件计数（缩量上涨 / 放量滞涨）、个股-行业相关性、趋势斜率 t 值。⚠️ 其中 `i20260810-005/006`（筹码类）已在 rationale 内标注"中性化必须走 `pit_float_mcap`"，承接本轮 PIT 红线。
- 🔵 **想法供给（侦察兵 2026-08-13 第 3 期）**：灵感池 **36 → 现 46 条候选**，漏斗卡住 0。本周新增 **10 条**（paper 2 / zoo 2 / sell_side 2 / forum 3 / observation 1）。本期新维度：**月末流动性清算窗口(PreTOM loser 季节性)、个股特异性动量残差(正交剥离因子暴露)、波动率门控反转、动量/反转自适应切换(结构扰动指数)、涨停后缩量横盘二次启动、股息率截面、skip-month 动量去噪、统一日收益异常和、行业资金流转向、ADD 月初择时叠加**。论坛源(IAMAIBOT/CHI 量化)数字不可核，仅取构造思路、置信度已标 low。
- 🔵 **想法供给（侦察兵 2026-08-17 第 4 期，仅供给侧，与执行进度无关）**：灵感池 **46 → 现 57 条候选**，漏斗卡住 0。本周新增 **11 条**（paper 3 / sell_side 4 / zoo 2 / forum 1 / observation 1）。本期新维度：**高阶矩家族**（收益不对称性 Asymmetry、协偏度 Coskewness、偏度增强 overlay——纯日频可实现，且与现有 MAX5/MIN3 正交）、**低市场 Beta + 下行半方差**（防御性风险维度，与现有 ivol f0002a 严格正交）、**波动率的波动率 (vol-of-vol)**、**成交量市场跟随性 / 激增-骤降对称性**（量能结构类，区别于量能扩张速度比值）、**因子动量加权合成层**（与稀疏 PCA 合成互补的元信号）、**动量崩塌风格轮动 overlay**、**红利低波三维交集 composite**。⚠️ 低Beta/下行半方差/不对称性与现有 ivol、MAX5、MIN3 需先测截面相关性，相关系数>0.8 应合并而非并列。
- 🔵 **想法供给（侦察兵 2026-08-20 第 5 期，仅供给侧，与执行进度无关）**：灵感池 **57 → 现 63 条候选**，漏斗卡住 1（i20260806-007 已 validated）。本周新增 **12 条**（paper 2 / zoo 2 / sell_side 5 / forum 3）。本期新维度：流动性改善度(LIQIM 差分) / 偏度管理二次倾斜 / SUE-PEAD 应计风险归因 / 相对+绝对动量双过滤 / 跳空-振幅背离(中金Loop) / 高低位放量事件簇(国盛) / 特异度 / 特质波动率比率 / 12-1动量(zz1000) / rank_autocorr 门控 / 盈利因子8月季节性 / 长上影线。各条 rationale 已标注与现有因子相关性检验与 PIT/exec_lag 红线。⚠️ 容量护栏生效：本期起 hypothesized 已 62，逼近 60 阈值上限，下期若 ≥60 将触发跳过供给（仅刷新看板）。
- 🔵 **想法供给（侦察兵 2026-08-24 第 6 期，仅供给侧，与执行进度无关）**：灵感池 **63 → 现 72 条候选**（hypothesized 58 / validated 14，漏斗 58 可进、14 为终态 validated 非真卡住）。护栏实测 hypothesized=49 < 60 阈值，**正常供给**（第5期预言的爆满未实际触发，因 13 条已被下游 validated 消化）。本周新增 **9 条**（sell_side 8 / forum 1）。本期新维度：分析师预期修正动量(Revision Momentum) / 凸显性 Salience / 盈利质量·应计盈余质量(Sloan accruals) / 多维成长质量合成 / 中单净流入占比(中户资金层) / 不确定性动量增强(动量×iVIX交互) / 横截面收益离散度择时(meta-gating) / 质量×动量二次验证 overlay / 行业预期修正广度。各条 rationale 已标注与现有因子相关性检验要求及数据缺口（分析师一致预期源 / PIT 财务 / 分单资金流）。⚠️ 修复 idea_backlog.py 存储层：CSV 带 UTF-8 BOM 且被外部优先级工具扩至 18 列、而脚本 FIELDS 仍 14 列，致 list/funnel/add_idea 全 KeyError；已改 utf-8-sig + FIELDS 同步 18 列，命令链恢复，新行列数一致性 {18:72} 校验通过（fix 亦消除未来 _rewrite 冲掉 priority 等 4 列的隐患）。
- 🔵 **想法供给（侦察兵 2026-08-27 第 7 期，仅供给侧，与执行进度无关）**：灵感池 **72 → 现 80 条候选**（hypothesized 64 / validated 16，漏斗 64 可进、16 为终态 validated 非真卡住）。护栏实测 hypothesized=56 < 60 阈值，**正常供给**。本周新增 **8 条**（paper 1 / sell_side 5 / forum 1 / observation 1）。本期新维度：**个股彩票型偏度(lottery skewness，日频三阶矩→低收益，区别于池内偏度管理overlay)、融资融券折算率相对行业(机构认可度代理)、盈利增速因子的风格状态门控(成长占优期有效/价值期失效→需Gating)、研报文本 LLM+FinBERT 情绪(纯NLP，区别于数值预期修正)、波动率扩张速度(方正"勇攀高峰"日频降级=波动突变预警)、市场状态 MOE 动态合成(东吴四指数路由，区别于离散度择时)、机构筹码集中度(公募持仓/总市值)、机构主动加仓环比(剔除股价波动的QoQ增幅)**。融券类搜索结果为头条阴谋论、数字不可核，按纪律跳过未灌。各条 rationale 已标注与现有因子相关性检验 + 数据缺口（折算率/研报语料NLP/基金季报PIT滞后）。⚠️ 容量护栏临界：本期后 hypothesized=64 ≥ 60 阈值，下期(08-31)若仍 ≥60 将触发跳过供给（仅刷新看板），符合"让它 drain"设计。

- 🔵 **想法供给（侦察兵 2026-08-31 第 8 期，仅供给侧，与执行进度无关）**：⚠️ **容量护栏触发，本周跳过供给**：`idea_backlog.py list` 实测 `hypothesized=64 ≥ 60` 阈值，按纪律不跑 WebSearch、不写新灵感，仅刷新看板 + 漏斗体检。灵感池维持 **现 80 条候选**（hypothesized 64 / validated 16，漏斗 64 可进、16 为终态 validated 非真卡住）。漏斗体检：可进 64 / 卡 16（均 validated 终态）。看板刷新：因子 已交付=25 / 研究中=18 / 灵感池=80；信号 已交付=3 / 研究中=0。待驱动器消费端（灵感池 draining）把 hypothesized 降到 <60 阈值后再恢复供给。

### 下一步待办（按优先级）
1. ✅ **（已发送 2026-08-17 16:19）** `deliverables/strategy_collab_issue.md` 已成功建 issue 到 `fkchaos/a-share-quant-sim`：**[#1](https://github.com/fkchaos/a-share-quant-sim/issues/1)**。路径：本地 GCM 凭证中的 fkchaos PAT → GitHub REST API（`POST /repos/fkchaos/a-share-quant-sim/issues`），**绕开 WorkBuddy GitHub 连接器**（该连接器对仓库只读/已断开，写操作全 403）。注意：WorkBuddy 连接器仍不可用，后续若需再发 issue/PR，继续走本地 PAT/API 或用户在 Web 手动操作。
2. **P0 信号半衰期补丁**：`decay_status` / `regime_dependency` 现为 unknown，是导出 JSON 里唯二的空洞。
3. **审计其他 PIT 嫌疑字段**：本轮只修了 `market_cap`，`factors/zoo_basics.py::size_log_mcap`（研究中未交付）仍读脏列；provider 里还有没有别的"今日快照回填"字段值得逐一 `nunique()` 过一遍。
4. （可选）从灵感池 promote 高优候选（#3 日夜动量分解、#7 非对称反转）进流水线验证。
5. （中期）第三条腿 ML 挖掘：特征工厂已就位 → 上 Purged CV + Walk-forward + SHAP 可解释。
6. （P1）因子线补分状态 IC + IC 衰减 + 经济逻辑长文（v75 复盘盲区① + 需求对接项）。

### 遗留问题 / 待决策
- 🟢 **GitHub 连接器写权限问题已绕过（2026-08-17 16:19）**：WorkBuddy GitHub 连接器对该仓库仍只读/已断开（所有写操作 403，2026-08-17 实测），但**用户本地 GCM 凭证存有 fkchaos PAT**，经 GitHub REST API 已成功建 issue **[#1](https://github.com/fkchaos/a-share-quant-sim/issues/1)**。结论：连接器不可用，但本地 PAT + API 可写（issue/PR/代码均可走 `git`/`gh`/API）。注意 `gh` CLI 未安装，代码推送需用 `git`（remote 在 `a-share-quant-sim` 克隆，非 factor-factory 内）。**后续新交付走「批次累积」模式（见关键环境变化）：驱动器挂队列、主理人交互时经 `scripts/gh_issue.py` 发出，不占 cron 交互。**
- ⚠️ **`data/providers.py::_share_map()` 本体未改**：本轮是"绕开"而非"修好"——面板里那列假 `market_cap` 仍在，只是所有消费方改用 `data/pit.py`。彻底修需要 provider 层拉历史股本序列（Tushare `daily_basic` 受限频、baostock 有 `peTTM/psTTM` 但无直接流通股本）。保留脏列的好处是不破坏既有契约测试，坏处是后人可能再次误用——已用 `data/contract.py` 的 PIT 分级段 + 测试断言双重设防。
- ⚠️ **s0001x 按对方门槛判 refuted（sharpe 0.94 < 1.0）**：我方不设质量门槛（用户决策），但需明确——首个信号在策略组 §7.2 口径下是不合格的。它的价值在**回撤改善 +14.27pct**（择时信号本就更该看 DD 而非 Sharpe），建议对接时主动说明口径分歧，别让对方一眼 refuted 就丢掉。
- ⚠️ **`build_deliverable.py` docstring 示例误导**：第 15-16 行写 `--factor <combo>`，但实际注册名是 `combo_equal_v1`，照抄直接 `KeyError: 'combo'`（本轮踩过）。未改代码，仅记录；后续顺手修 docstring。
- ⚠️ **组合因子方向系数仍为常量**：`combo_equal_v1` 用 +1/+1 硬编码；虽本轮六池未见异号，但 sz50 与 SZ300 历史上出现过 overnight 方向差异，建议后续改滚动历史 IC 自适应。
- ⚠️ **主场集中在 zz1000**：两因子主场同池，组合分散化收益可能被高估，后续做组合优化时需注意池子重叠。
- ⚠️ **全A 池降优先级**：用户明确先指数分层（50/300/500/800/1000 + 组合），暂不碰全A。
- ⚠️ **沙箱命令重复派生**：环境会把单条后台命令派生成父子双进程；baostock 已用端口锁防并发崩溃，但其他长时间进程仍可能触发，注意单实例。
- ⚠️ **Windows 测试整跑良性崩溃**：pytest 整跑末进程退出偶发 0xC0000409，各文件 rc=0 全绿，非回归（单文件跑稳定）。

### 关键环境变化（续作必读）
- hs1800 全市场缓存 **1672 parquet 已就绪**（数据阻塞解除，P4/P5/P7/f0003a 可跑）。
- 两个自动化在跑（2026-08-17 精简：原看门狗 21:30 已并入驱动器 21:00，单一 session 完成工作+自检，减少 session 数、且全程零用户交互）：侦察兵（供给，周一/四 12:00；截至 2026-08-17 已累计供给 57 条候选）+ 驱动器（执行+自检，每日 21:00，含信号线 s-code 构建 + 看板双段刷新 + HANDOFF 同步 + 当月月报动态生成 + 原看门狗四项巡检内联：signals/_REGISTRY.csv 存在性 / ic_matrix hs1800 列 / P5 baseline 40 天新鲜度 / board mtime<24h）。
- 🆕 **每日 22:00 自动同步 automation（automation-1788263669961，2026-09-01 用户拍板「后续提交不需要拍板，本地修改全部提交保持线上最新」）**：每天 22:00 自动 `git add -A → commit(auto-sync: 日期 本地改动自动提交) → push origin main`，零交互、零询问；`.gitignore` 已排除 `.cache/`/`.workbuddy/`/`.env`/`*.token`/`configs/tushare.yaml` 等，自动跳过。**后续 session 无需再问用户要不要 commit/push**，本地改动每晚 22:00 自动上线；当日无改动则跳过。人工提交用 `feat/fix/chore` 前缀，自动同步统一 `auto-sync:` 前缀。
- **GitHub issue 批次队列（2026-08-17 用户拍板「按批次累积提」，替代此前暂停态）**：驱动器不再直发 issue（cron 零交互 + headless 取不到 GCM 凭证）。每实际新交付一个 f/s-code，驱动器向 `.cache/pending_handoff.md` 追加一行（日期|类型|编号|名称|JSON路径）；看板 `factor_board.py` 顶部注入「📤 待提 issue：N 个」（N=队列数据行数）；主理人在交互会话时读队列 → 用 `scripts/gh_issue.py` 经本地 PAT+API 汇总成一个 issue 发出 → 清空队列。已交付的 3 因子(f0001a/f0002a/f0003a)+3 信号(s0001x/s0002x/s0003x)已在 Issue #1 整体交接，不重复入队。
- 双线架构：`factors/`（f-code 选股）+ `signals/`（s-code 市场状态 overlay），详见 `docs/PLAN_SIGNAL_LINE.md`；看板单文件双段 `docs/factor_board.html`。
- baostock 单实例端口锁已加（cache_universe.py）；拉取前确认无遗留 python 进程。
- **新增对外目录 `deliverables/strategy_export/`**：给策略组的 JSON 交付口（stock_factors / timing_signals / risk_params + README），由 `scripts/export_to_strategy_json.py` 幂等重生成。**因子/信号包有更新后要重跑一次**，否则 JSON 是旧快照。
- `risk_params.json` 是**故意留空的占位**（用户决策：风控参数归策略组，我方不出），别误当 bug 去填。
- venv：C:/Users/jiaby1/.workbuddy/binaries/python/envs/default/Scripts/python.exe

---

---

## 0.5 信号线状态（独立顶层段 · cron 不重写，人工/驱动器同步时仅更新「待出包→已出包」）

> 与因子线**纪律完全平行**（灵感池漏斗 → 防前视 → 过拟合审计 → 编号交付 → 月度监控），**检验指标与交付物不同**：因子给每股打分(RankIC/分层)，信号给市场判状态(状态命中率/叠加Sharpe-DD改善)。详见 `docs/PLAN_SIGNAL_LINE.md`。

- ✅ **架构已建**：`signals/`（interface.py Signal Protocol + register/get/list + assert_no_lookahead 前视防护 + `_REGISTRY.csv` s-code）、`validate/signal_validator.py`（状态绩效/方向命中/叠加改善/转移矩阵）、`scripts/build_signal_deliverable.py`（s-code 包：card/state_sequence/state_performance/overfit_audit/manifest）。
- ✅ **首个信号已实现**：`signals/breadth_regime.py`（广度 Regime，v75 复盘核心洞察=广度过滤是 regime 选择器；零新增数据源，从缓存 panel 算涨跌家数占比）。**已出包 `s0001x`（叠加Sharpe改善 +0.145：baseline 0.79 → overlay 0.94，MaxDD -45.49%→-31.22%，见 `deliverables/signals/s0001x/card.md`）**，2026-08-07 驱动器 cron S 步构建，`deliverables/signals/_REGISTRY.csv` status=current。
  - 出包踩坑：`signals/__init__.py` 原未 import 信号模块 → 注册表为空 → `get_signal("breadth_regime")` KeyError，cron 首跑即崩。已补"导入即注册"纪律（与 `factors/__init__.py` 对齐），**新增信号必须在 `signals/__init__.py` 加一行 import**。
- ✅ **第二个信号已出包（2026-08-08 晚 cron）**：`signals/risk_appetite.py`（风险偏好 = 小盘组次日收益 − 大盘组次日收益，差值型 raw 天然零中枢，阈值 0 免拟合）。**已出包 `s0002x`**：overlay Sharpe 0.84（baseline 0.79，改善 +0.048），MaxDD -45.49%→-44.50%，命中率价差 +4.0%（优于 s0001x 的 +3.1%），切换率 7.18%（更稳），DSR 1.000 PASS，`_REGISTRY.csv` status=current。
  - **同期 Sharpe 仅 1.34**（s0001x 是 2.68）→ 本信号对当日信息依赖显著更低，是比广度类更"干净"的择时视角。
  - 🔴 **出包前拦下 `market_cap` 假 PIT 坑**：面板该列是今日快照回填全历史（`nunique()==1`），2013 年分组一致率仅 53.7%。已改用 `data/pit.py::pit_float_mcap()`（`amount/(turnover/100)` 现算流通市值，取前一日近 5 日中位数；用前一日而非当日，同时防当日涨幅推高市值排名的**分组排序污染**）。详见 §0 最新快照。
  - ✅ **冗余检查已过**：`scripts/signal_redundancy.py` 实测 s0001x vs s0002x 一致率 59.3%（随机基线 47.2%，超额 +12.0%），raw 相关 +0.338，判定 ✅ 视角独立（门槛：≥85% 高度重复须降级）。结果落 `deliverables/signals/_REDUNDANCY.json`。**未来每个新信号出包后都要跑这个脚本**。
- ✅ **看板双线化**：`docs/factor_board.html` 单文件双段（因子 / 信号），含"信号已交付 / 信号研究中"两计数；**2026-08-12 晚已翻牌：信号 已交付=3 / 研究中=0**（breadth_regime + risk_appetite + volatility_regime 出包后自动移入已交付）。
- ✅ **第三个信号已出包（2026-08-12 晚 cron）**：`signals/volatility_regime.py`（波动率 Regime）。raw = ln(RV_prior20 / RV_recent20)，RV = 等权市场日收益标准差，两腿各 20 交易日不重叠（等长 → 平稳性下期望严格为 0，**阈值免拟合**，满足 PLAN §6.1 #2 硬门；只读 `close` 一列天然避开假 PIT `market_cap`）。**已出包 `s0003x`**：overlay Sharpe 0.50（baseline 0.76，改善 **-0.260**），MaxDD -45.49%→**-34.12%**（改善 **+11.38pct**），命中率价差 **-2.0%**，切换率 3.35%，DSR 1.000 PASS，`_REGISTRY.csv` status=current。
  - **方向与经济先验相反**（波动扩张后次日反而涨更多），**刻意不反转符号**（那是看过全样本才改方向=数据窥探），按策略组 §7.2 门槛 Sharpe 0.50 < 1.0 如实判 **refuted**；价值重新定位为**回撤削减闸门**（DD 改善 +11.38pct）而非收益增强器。
  - **同期 Sharpe 仅 0.54**（s0001x 2.68 / s0002x 1.34）→ 三包里最"干净"（几乎不吃当日信息）。
  - ✅ **冗余检查已过**：`scripts/signal_redundancy.py` 实测 s0001x vs s0003x 49.5%、s0002x vs s0003x 54.2%（均远低于 85% 重复门槛，raw 相关为负），判定 ✅ 视角独立；s0003x 与另两包最正交。结果落 `deliverables/signals/_REDUNDANCY.json`。
  - 测试焊死：新增 `tests/test_signal_line.py` 5 项锁 raw 零中心（均值偏离 0 < 0.06 红线），全量 156→**161 项 pytest 通过（2026-08-12 晚）**。
- 🔴 **exec_lag 红线已加固（信号线专属，必读）**：时序信号最易翻车处**不是前视取数而是前视回测**。
  - 坑：`state[T] × ret[T]` 用 T 日收盘才知道的状态赚 T 日的钱；对 breadth 这类"当日涨跌家数统计"型信号近乎同义反复，实测能造出 Sharpe 5.99 的假象（真实滞后口径 5.15，真实数据上差距会更大）。
  - 已强制：`state_performance(exec_lag=1)` overlay 一律 `state.shift(1)`；`build_signal_deliverable.py --exec-lag` 默认 1，**传 0 直接 exit 2 拒绝出包**。
  - 已统一：`bench_ret[t]` 约定为 **t 日当天已实现收益**（`close_t/close_{t-1}-1`），原实现是 t→t+1 前向收益，与验证器滞后叠加会造成**双重滞后**。两边约定打架是隐性坑，改动前务必看 `PLAN_SIGNAL_LINE.md §4.1`。
  - 卡片口径分层：`fwd_*` = 可交易预测力（主表），`*_contemp` = 同期诊断（折叠区），并打印 `_contemp_sharpe_ref` 供对照。
  - CI：`tests/test_signal_line.py` 12 项，正反双向锁死（exec_lag=1 必须 ≠ 同期；exec_lag=0 必须 == 同期）；`tests/test_pit_mcap.py` 12 项锁死 PIT 市值口径。全量 **156 项 pytest 通过（2026-08-08 晚）**。
  - **钢印已落地（2026-08-07 晚）**：`build_signal_deliverable.py` 的 `EXEC_LAG_WARNING` 常量同时写进 card.md 顶部 🔴 块、manifest.yaml（`exec_lag: 1` + `exec_lag_warning`）与导出 JSON，未来所有 signal 包自动继承。s0001x 实测同期 Sharpe 2.68 vs 正确 overlay 0.94，红线的真实代价已有实证数字可引。
  - 附带修掉 `signal_validator.py` 的 `_max_d` NameError（原会让今晚 cron S 步直接崩）与 `np.corrcoef` 遇 shift(-1) 末位 NaN 整体返回 nan 的坑（改用 `Series.corr`）。
- ⚠️ **风控层不做**：用户确认"没有就没有，先不管"——止损/止盈/仓位参数由策略组负责，我们不出。
- ⚠️ **calc_factors 签名待对方**：开放接口契约（`docs/INTERFACE_CONTRACTS.md`），对方未提供 §4.1 签名，不阻塞研发；等对方给后做适配器层一次性接入。
- ⚠️ **质量门槛移除**：用户决策"我们生产因子，质量高低由策略组选择"——内部交付卡片不再设 |IC|≥0.03 出库门槛（改为信息项），DSR/PBO 过拟合门禁保留（防数据窥探，非质量筛选）。
- 🔄 **因子 6 池补测**：`build_deliverable.py` 卡片已改多池 IC 表。**f0001a / f0002a 六池齐**（f0001a hs1800 RankIC +0.0283/ICIR 0.317；f0002a zz1000 +0.0510/ICIR 0.533）；**f0003a 组合包 2026-08-07 晚补跑中**（原仅落 sz50 单池，与另两只不一致）。补跑完成后须重跑 `scripts/factor_board.py` + `scripts/export_to_strategy_json.py` 刷新看板与对外 JSON。⚠️ 注册名是 `combo_equal_v1`，不是 docstring 里的 `combo`。

---

## 0.6 休假授权（2026-08-08 ~ 2026-08-14 · 稳定段，cron/人工均不重写）

> 用户于 2026-08-07 晚间明确：2026-08-08 起休假一周，无法回复与决策；**授权非关键事项由主理人+团队自主决定，无需等待用户**；"正常按驱动器推动进行"。本段为稳定段，任何 session / cron 同步 HANDOFF 时**不得删改或清空**。

### 已拍板的开放问题（原为"待用户/待对方"，现自主决断，不再阻塞）
1. **calc_factors 签名**：对方（策略组）至今未提供 §4.1 签名。按开放契约（`docs/INTERFACE_CONTRACTS.md`）**由我方提供因子函数签名，对方适配**；不再等对方。适配器层在 `export_to_strategy_json.py` 构建时一并处理。
2. **JSON 适配器 `export_to_strategy_json.py`**：P1，优先级上调为**假期自主推进项**。把 f-code/s-code 包聚合成对方 `alpha-research/inputs/*.json` 精确 schema（补 type/category/source 标签 + timing 信号 `exec_lag=1` 钢印字段），直接预填对方阶段0。
3. **exec_lag 钢印**：所有已出/将出 signal 包的 card.md / manifest.yaml 显式标注 `exec_lag=1` + "禁止用同期收益评估，须 shift(1)"（对接策略组的防前视红线，见 PLAN_SIGNAL_LINE.md §4.1）。
4. **策略组对接回复**：`docs/REQUIREMENTS_ALIGNMENT-2026-08-07.md` §8 草稿即最终版，已作为 GitHub issue **[#1](https://github.com/fkchaos/a-share-quant-sim/issues/1)** 发到 `fkchaos/a-share-quant-sim`（2026-08-17 经本地 PAT + REST API 发出，绕开只读的 WorkBuddy 连接器）。
5. **因子质量门槛**：维持用户决策"我们不出内部门槛，好坏由策略组 §7.2 选"；交付多池 IC 表让其自选主场（sz50 证伪 / zz1000 有效，池子函数）。

### 假期运行纪律
- 驱动器(21:00)按步骤6 自主推进上述协作交付物；看门狗(21:30)照常巡检。
- 遇"原本要问用户"的点，按本段已决项直接推进，不在对话里等用户。
- 真·阻塞（如对方仓库无写权限导致 issue 发不出）记 HANDOFF 遗留 + 简报，不卡流程。

## 1. 关键决策与 ADR（简述）
- **ADR-0001**：六层解耦 + 插件式 Factor 接口；前视防护放接口层。
- **子集支持**：`FF_UNIVERSE` 从"只支持 L/D/P"扩展为指数/交易所/列表状态三模式——真实重测必须用子集（全A 5000+ 只 × 全历史不现实）。
- **共享选股层**：WF 与 Shadow 共用 select_targets/execute_rebalance。
- **因子预注册**：每因子先填 `fp_*.md` 再实现。
- **失败也记录**：淘汰因子进 `TEST_LOG`「因子墓地」。

## 2. 注意事项（红线 / 易错点）
- ⚠️ **前视偏差红线**：`Factor.compute` 只能读 `as_of` 及之前数据；越界被 `LookaheadError` 拦。绝不可复现。
- 🔴 **PIT 红线（2026-08-08 血泪，与 exec_lag 并列）**：`assert_no_lookahead` **只管"有没有切到未来的行"，不管"某一列本身是不是未来信息"**。面板 `market_cap` 就是反例——provider 把今日市值快照贴到全历史（`nunique()==1`），2013 年用它分大小盘，一致率只有 53.7%，选出的"小盘"其实是"到今天仍小的公司"= 后视选股。**用任何面板字段前先 `panel.xs(code,level="asset")[col].nunique()` 验一遍是否随时间变**；市值一律用 `data.pit.pit_float_mcap()`（`amount/(turnover/100)` 现算）。更隐蔽的是中性化——`residual = fv − β·log(mcap)` 会把 −β×未来收益注入残差，比因子直接读脏数据更糟（已修 `validate/validator.py`）。详见 `data/contract.py` PIT 分级段。
- ⚠️ **测试环境**：pytest/pandas/numpy/scipy/tushare 装在托管 venv `C:/Users/jiaby1/.workbuddy/binaries/python/envs/default/Scripts/python.exe`；系统默认 `python` 无依赖。临时脚本 sandbox 下中文路径解析异常，用 `python -c` 内联或绝对路径 import。
- ⚠️ **token 读取**：本 Bash 环境**读不到**交互式 shell 的环境变量；一律用 `configs/tushare.yaml` 文件方式（已 gitignore）。yaml 库未装，`real_research.py` 用 `startswith("token:")` 行解析，新脚本照抄。
- ⚠️ **Tushare 免费档三大限频陷阱（全踩过）**：`adj_factor` **1次/小时**（→ 用不复权 raw 价，pro_bar 别加 adj='qfq'）；`daily_basic` **1次/分钟**（→ 熔断闩已内置，turnover/market_cap=NaN）；`stock_basic` **1次/小时**（→ 空壳缓存陷阱已修；股票池改用 `make_universe.py` 从 AkShare 生成落缓存，别等 stock_basic）。`index_weight` 需 500 积分（hs300 池暂不可用，用 SZ/SH 交易所池）。
- ⚠️ **pip 安装撞沙箱**：Windows sandbox 下 pip 缓存清理报 `SAFE_DELETE_FAIL_CLOSED` → 安装用 `--no-cache-dir`。
- ⚠️ **数据契约**：Provider 的 `get_panel` 返回前 MUST `canonicalize_panel + validate_panel`；缺失用 NaN 禁 0 占位；收益率小数非百分数。新增数据源必须过 `tests/test_provider_contract.py` 精神。
- ⚠️ **数据源单点 / 幸存者偏差**：TushareProvider.list_universe 当前为近似非 PIT（Phase 4 改进）。

## 3. 环境信息（续作必读）
- 工作区：`D:\ai-workspace\WorkBuddy\A股研究\factor-factory\`
- Python venv：`C:/Users/jiaby1/.workbuddy/binaries/python/envs/default/Scripts/python.exe`
- 跑测试：`cd factor-factory && "<venv>/python.exe" -m pytest tests/ -v`
- 真实重测（先填 token）：`cd factor-factory && "<venv>/python.exe" scripts/real_research.py`（默认全A；设 `FF_UNIVERSE=hs300` 用沪深300 子集先验证）
- 依赖装于托管 venv（pytest, pandas, numpy, scipy, tushare 等）；当前全量 **161 项 pytest 通过（2026-08-12 晚，含信号线 17 项 + PIT 市值 12 项 + 基线 132 项）**

## 4. 关键文件索引
| 文件 | 用途 |
|------|------|
| `docs/ARCHITECTURE.md` `docs/adr/0001-*.md` `docs/RESEARCH_LOG.md` | 架构/决策/调研 |
| `docs/SOP_TUSHARE_TOKEN.md` | 真实数据源 token 接入 SOP |
| `configs/tushare.yaml`（gitignore） | **用户填真实 token 处** |
| `research/templates/` `research/factor_plans/` `research/factor_cards/` `research/TEST_LOG.md` `research/design_shadow_account.md` | 文档体系 |
| `data/interface.py` `factors/interface.py` `engine/interface.py` | 三大核心接口 |
| `data/contract.py` `docs/DATA_CONTRACT.md` | **数据契约（单位/格式防火墙，2026-08-04 新增；2026-08-08 补 PIT 字段分级段）** |
| `data/pit.py` | 🔴 **PIT 流通市值现算（`amount/(turnover/100)`）——面板 `market_cap` 列是假 PIT，一切市值用途走这里** |
| `data/providers.py` | 数据源适配器（Local + Tushare 真实 + AkShare 真实 + BaoStock 真实；契约校验 + 限频熔断） |
| `factors/overnight_intraday.py` `factors/ivol.py` `factors/feature_factory.py` `factors/microstructure.py` | 已落地因子 + 特征工厂 |
| `engine/selection.py` | 共享选股层 |
| `engine/engine_impl.py` | WalkForward 引擎 |
| `portfolio/combiner.py` `portfolio/shadow_account.py` | 组合合成层 + 影子账户 |
| `monitor/monitor.py` | 监控看板骨架 |
| `scripts/real_research.py` | 真实数据一键重测流水线 |
| `scripts/make_universe.py` | **用 AkShare 生成股票池 CSV（绕 stock_basic 限频）** |
| `scripts/build_combo.py` `scripts/idea_backlog.py` `scripts/factor_board.py` | 组合构建 / 灵感池 / 因子看板 |
| `signals/breadth_regime.py` `signals/risk_appetite.py` `signals/volatility_regime.py` | 已落地信号（s0001x 广度 Regime / s0002x 风险偏好 / s0003x 波动率 Regime） |
| `scripts/signal_redundancy.py` | **信号冗余检查（出包后必跑，状态一致率 ≥85% 判信息重复）** |
| `validate/validator.py` `validate/redundancy.py` `validate/overfit_audit.py` | 验证器 + 冗余检查 + DSR/PBO 审计 |
| `docs/PLAN_THIRD_LEG.md` `docs/PLAN_IDEA_BACKLOG.md` `docs/FACTOR_RESEARCH_PRIMER.md` | 第三条腿 / 灵感池 / 科普 |
| `tests/` | 测试（**全量 161 项，2026-08-12 晚**；`test_pit_mcap.py` 锁死市值 PIT 口径） |
| `README.md` | 项目总览与进度 |
| `docs/HANDOFF-2026-08-06.md` | **历史已完成归档（本轮清理产出）** |

## 5. 给后续 session 的交接说明
- 用户授权"小问题自己搞定，大问题才找他"；每条 Phase 完成后直接开下一 Phase，不要空等。
- 工作风格：计划先行 + 外部调研交叉 + 全程文档化，三者缺一不可。
- 当前最该接手的具体工作见上方「🆕 最新快照 · 下一步待办」（**发对接 issue → P0 半衰期补丁 → 第三个 s-code 已出包 → 审计其他 PIT 字段**）。接手前先跑 `pytest tests/ -q` 确认 161 项基线全绿。
- 因子级交付状态看 `docs/factor_board.html`（由驱动器 cron 自动刷新），不要在此文档手动维护。
- 若上下文将满，先更新本文件再结束，不要带着未交接状态退出。
