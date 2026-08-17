# USER_GUIDE · 用户手册

> 面向想**用** factor-factory 产出/消费因子的人：怎么看板、怎么加因子、怎么读交付卡、灵感池怎么用。
> 部署与环境见 [DEPLOYMENT.md](DEPLOYMENT.md)；架构见 [ARCHITECTURE.md](ARCHITECTURE.md)。

---

## 1. 看板（第一入口）

`docs/factor_board.html` 是单一信息源，**双击即可在浏览器打开**（单文件零依赖）。它聚合：

- **因子线**：已交付（f-code 包）/ 研究中（代码已实现未交付）/ 灵感池（候选假设）/ 已拒绝
- **信号线**：已交付（s-code 包）/ 研究中
- **数据管线**：hs1800 全市场缓存进度

刷新：`make board`（或 `python scripts/factor_board.py`）。

## 2. 加一个新因子（5 步）

> 前置：已 `pip install -e ".[dev,data-baostock]"` 且数据缓存就绪。

1. **写因子模块**：在 `factors/` 下新建 `my_factor.py`，实现 `Factor` 接口（参考 `factors/chip_cost_distance.py`）：

   ```python
   from factors.interface import Factor, register_factor

   @register_factor
   class MyFactor(Factor):
       fcode = "f0006a"          # 下一个可用编号
       name = "我的因子"
       universe_hint = "zz1000"  # 实测主场池（可选）

       def compute(self, panel, as_of_date, ctx=None):
           # panel 已保证只含 as_of_date 及之前的数据（接口层防前视）
           # 纯函数 + 分组操作，禁止读全样本 / 全局统计量
           out = panel["close"].groupby("asset").transform(...)  # 例
           return out.dropna()
   ```

2. **注册**：在 `factors/__init__.py` 补一行 `from . import my_factor`。

3. **出包**：

   ```bash
   make factor F=my_factor FCODE=f0006a NAME=我的因子 POOLS=hs300,hs800
   ```

   出包脚本跑 IC/IR/分层/DSR/PBO，产物落到 `deliverables/factors/f0006a/`。

4. **看板验证**：`make board` → 该因子出现在「已交付」。

5. **登记发布**：推进器会自动把新交付写入 `deliverables/CHANGELOG.md` 的 `[Unreleased]`；交互会话整理归档。

### PIT 红线（必读）
- `compute` **只用 `as_of_date` 及之前**的数据；任何"读取未来"都会在前视防护 CI 失败。
- 市值/财务必须用 PIT 口径（`data/pit.py` 的 `pit_float_mcap()`），**禁止**直接用 `market_cap` 快照列（今日快照回填全历史，是假 PIT）。
- 中性化前也走 PIT 市值，避免把未来收益注入残差。

## 3. 加一个时序信号（s-code）

与因子同理，但实现 `Signal` 接口、产出**市场级状态标量**（非逐股打分）：

```bash
make signal S=my_regime SCODE=s0004x NAME=我的Regime
```

信号包 `card.md` 必须标注 `exec_lag=1`（状态用 T 日及之前数据，overlay 时 `state.shift(1)`）。

## 4. 读交付卡

每个交付物 `deliverables/factors/<fcode>/card.md` 含：

- **说明**：假设、可证伪条件、PIT 处理
- **相关性**：与同池其他因子的 RankIC 相关（冗余检查）
- **回测**：RankIC / ICIR / 胜率 / 分层收益（历史样本，非未来保证）
- **审计**：DSR / PBO 过拟合审计结果

> 本厂**不设质量门槛**：审计通过即出包，因子强弱由下游策略组在 `deliverables/strategy_export/*.json` 层筛选。

## 5. 灵感池

`research/idea_backlog.csv` 是候选假设池，状态机：`backlog → hypothesized → in_pipeline → validated/rejected`。

- **侦察兵**自动供给（周一/四）；≥60 条时停供。
- **推进器**每日消费 top-2 `hypothesized` 高可行性候选，自动实现成因子。
- 手动加入：参考 `scripts/idea_backlog.py add_idea` 的子命令。

## 6. 导出给下游

```bash
make export        # 聚合 f-code/s-code → deliverables/strategy_export/{stock_factors,timing_signals,risk_params}.json
```

JSON 是机器可读的真源；看板/CHANGELOG 只是人类可读视图。
