# 接口契约 · calc_factors 对齐（开放契约，待对方提供）

> 状态：开放契约，**当前未知**，待策略研究组提供 §4.1 的因子代码签名要求。
> 决策来源：用户确认「calc_factors 签名：这个是啥没动，按建议处理」→ 我们的建议是：此为**接口对齐项**，不是阻塞项，研发照常推进，签名对齐留待对方给出后一次性接入。

---

## 1. 背景

策略研究组的需求规格（`2026-08-07_factor_requirements_spec.md` §4.1）要求因子代码**符合他们的 `calc_factors` 函数签名**，以便直接 load 进他们的选股引擎。

我们当前**不知道**这个签名长什么样（对方未提供）。因此：

- **不阻塞**：因子线 / 信号线的研发、检验、交付全部照常推进。
- **不臆造**：不在没有对方规格的情况下猜测签名去改我们的 Factor 接口。
- **留接口位**：本文件记录我们的接口现状，等对方给签名后做一次性适配（适配器层，不碰核心）。

---

## 2. 我们的因子接口现状（`factors/interface.py`）

```python
@runtime_checkable
class Factor(Protocol):
    name: str
    universe_hint: Optional[str] = None
    def compute(self, panel: pd.DataFrame, as_of_date, ctx: Optional[dict] = None) -> pd.Series:
        """返回以 asset 为索引的因子值（已切片到 as_of_date）。"""
```

- **输入**：`panel`（MultiIndex(date, asset) 的 OHLCV 面板）、`as_of_date`（防前视契约参数）、`ctx`（可选上下文）。
- **输出**：`pd.Series`，index=asset，value=因子值。
- **预处理三件套**：MAD 去极值 → 截面 Z-score → 行业/市值中性化（逐截面日，禁全局统计）。
- **防前视**：`assert_no_lookahead` CI 门禁。

### 信号接口现状（`signals/interface.py`）

```python
@runtime_checkable
class Signal(Protocol):
    name: str
    universe_hint: Optional[str] = None
    state_def: Optional[str] = None
    def compute(self, panel, as_of_date, ctx=None) -> float:
        """返回 as_of_date 当日的**市场级状态标量**。"""
```

---

## 3. 待对方提供的签名信息（对齐清单）

请策略组补充以下任一项，我们即可做适配器：

1. `calc_factors` 的函数签名（参数名 / 类型 / 返回值形态）。
2. 因子值的容器形态（numpy / pandas / 他们的自定义 Frame）。
3. 期望的 `as_of_date` 语义（他们是否自带面板切片，还是需要我们内部切片）。
4. 是否要求因子类继承某个基类（我们是 duck typing + Protocol，无强制基类）。
5. 因子注册方式（我们靠 `register_factor` + `_REGISTRY`，他们是否要 import 路径约定）。

---

## 4. 对齐策略（一旦对方提供）

- **适配器层** `adapters/strategy_bridge.py`：把我们的 `Factor.compute(panel, as_of)` → 他们的 `calc_factors` 调用约定，零改核心。
- 信号线同理：他们的 overlay 消费的是状态序列（CSV/每日标量），与我们的 `state_sequence.csv` 天然对接，**签名对齐风险最低**。
- 验证：对齐后补一个 `tests/test_strategy_bridge.py`，确保适配器输出与他们引擎输入契约一致。

---

## 5. 当前结论

- 因子/信号的**数据与检验产出**完全可独立交付（f-code / s-code 包已就位）。
- `calc_factors` 签名是**最后一公里对接**，不影响"生产优质因子"这个核心目标。
- 等对方给签名 → 一次性适配器接入 → 策略组可直接消费。
