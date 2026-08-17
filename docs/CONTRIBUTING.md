# CONTRIBUTING · 贡献指南

> 欢迎 PR。本仓库对因子/信号的**真实性**有硬要求（PIT 合规 + 前视防护 + DSR/PBO 审计），对**质量强弱**不设门槛（交下游筛选）。
> 架构与接口约束见 [ARCHITECTURE.md](ARCHITECTURE.md)；用户视角见 [USER_GUIDE.md](USER_GUIDE.md)。

---

## 1. 开发环境

```bash
pip install -e ".[dev,data-baostock]"
make test          # 提交前必须全绿
```

## 2. 因子 PR 检查清单

新增/修改因子（f-code）请确认：

- [ ] **实现 `Factor` 接口**：`compute(panel, as_of_date, ctx)` 签名正确，`as_of_date` 是防前视关键参数。
- [ ] **PIT 安全**：只用 `as_of_date` 及之前数据；市值/财务走 `data/pit.py` 的 PIT API，**不读 `market_cap` 快照列**。
- [ ] **无全局统计量**：预处理逐截面日执行，禁止 `groupby` 之外的全样本均值/标准差泄露。
- [ ] **纯函数 + 分组操作**：推荐 `groupby("asset").transform(...)`；避免实例状态跨 `as_of_date` 污染（CI `assert_no_lookahead` 会测）。
- [ ] **注册**：`factors/__init__.py` 补 `from . import <模块>`；`@register_factor` 装饰**实例**（非类）。
- [ ] **出包**：`make factor ...` 跑通，产物落 `deliverables/factors/<fcode>/`。
- [ ] **审计通过**：DSR/PBO 无异常；若 WARN/FAIL 需在研究记录说明。
- [ ] **测试**：`tests/` 加对应用例（含前视防护）；`make test` 全绿。
- [ ] **文档**：假设/可证伪条件写入因子 docstring 或计划文档；重大决策补 `docs/adr/`。

## 3. 信号 PR 检查清单

- [ ] 实现 `Signal` 接口，产出**市场级状态标量**（非逐股打分）。
- [ ] 标注 `exec_lag=1`；overlay 时下游必须 `state.shift(1)`（禁止同期收益评估）。
- [ ] 阈值**免拟合**（优先构造性分界，如对数比值的 0；避免全样本挑阈值）。
- [ ] 出包 `make signal ...`，`card.md` 三项（fwd_ret_1d / hit_spread / overlay Sharpe）不为"—"。

## 4. 代码风格（自注释）

- **自注释优先**：接口/契约/红线写在代码与 `docs/` 里，少靠口头约定。
- **层间只依赖接口**：核心逻辑不 `import` 任何具体实现（`data` 只认 `DataProvider`，`factors` 只认 `Factor`…）。
- **参数走 YAML**：回测窗口、成本、股票池、权重均在 `configs/*.yaml`，禁止硬编码。
- **命名**：因子类 `XxxFactor` + `fcode`；信号类 `XxxSignal` + `scode`。

## 5. 测试纪律

- 前视防护专项：`tests/test_lookahead.py` 用"已知会前视"的合成因子验证引擎拒绝未来数据。
- 数据契约：`tests/test_provider_contract.py` 校验多源单位/格式一致。
- 确定性 fixture：核心引擎（成本、时间切片、封板/停牌）必须有合成 fixture 单测。

## 6. 文档要求

- 架构/接口变更 → 同步 `docs/ARCHITECTURE.md` / `docs/INTERFACE_CONTRACTS.md` 与 `docs/adr/`。
- 外部调研交叉 → 记 `docs/RESEARCH_LOG.md`（Open-Research）。
- 内部运维（HANDOFF/评审/数据源 SOP）放 `docs/dev/`，**不进公开导航**。

## 7. 提交规范

- 提交信息清晰（中文亦可）；交付批次同步更新 `deliverables/CHANGELOG.md`。
- 不提交 `.cache/`、凭证、大文件（已 `.gitignore`）。
