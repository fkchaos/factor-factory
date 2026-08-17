# DATA_CONTRACT · 数据契约（单位/格式规范）

> 版本：R2026-0804-05 · 状态：已生效（运行时强制）
> 一句话：**切换数据源 MUST NOT 改变因子结果。** 违反契约的 Provider 在返回前抛错，而非污染下游。

## 为什么需要它

`DataProvider` 是可插拔的，但"可插拔"本身不等于"结果一致"。历史教训（v61b 式单位坑）表明，切换源后结果漂移的根因几乎都是：

1. 单位不一致：成交量 手 vs 股、成交额 千元 vs 元、换手率 百分比 vs 小数；
2. 代码格式不一致：`000001` vs `000001.SZ`（跨源 join 直接失败或静默错配）；
3. 索引名不一致：`trade_date/asset` vs `date/asset`；
4. 复权口径不一致：前复权 vs 不复权 vs 后复权；
5. 缺失值处理不一致：0 占位 vs NaN（0 会被当成真实数值参与计算）。

## 契约内容（所有 Provider 必须遵守）

### 1. 面板索引
- MultiIndex，level0 名 **`date`**，level1 名 **`asset`**；
- date 层 dtype = `datetime64[ns]`，无时区，日粒度；
- asset 层为 str，规范代码（见下）。

### 2. 规范代码格式
- `{6位数字}.{交易所后缀}`：`000001.SZ` / `600000.SH` / `830000.BJ`；
- `normalize_code()` 统一 `000001`、`sz000001`、`600000.SH` 等各种写法；
- 交易所推断规则：60/68→SH，00/30→SZ，8/4→BJ。

### 3. 字段单位表（`PANEL_FIELDS`）

| 字段 | 单位/语义 | 软校验区间 | 说明 |
|---|---|---|---|
| open/high/low/close/pre_close | CNY（元） | (0.01, 1e6) | 复权口径由 Provider 声明 |
| volume | **股 (shares)** | (0, 1e13) | Tushare `vol`=手 → ×100；AkShare 手 → ×100 |
| amount | **元 (CNY)** | (0, 1e15) | Tushare `amount`=千元 → ×1000 |
| turnover | 百分比（典型 0–100） | (0, 1000) | 非小数。**上限刻意留到 1000**：单日换手 >100% 在次新/ST/小盘妖股上真实存在，卡 100 会把真数据误判成单位错（2026-08-07 六池回填即因样例值 106.48 崩在 hs1800） |
| market_cap | **元 (CNY)** | (0, 1e16) | Tushare `total_mv`=万元 → ×1e4 |

### 4. 收益率表示
- `get_index_returns` / 一切收益率序列：**小数**（0.01 = +1.00%），非百分数；
- 校验阈值：A股日涨跌幅上限 30%，|r| > 0.5 即视为百分数误传。

### 5. 缺失值
- 一律用 **NaN** 表示；**禁止 0 占位**、禁止静默前向填充。

### 6. 复权口径
- 价格必须声明口径：当前 `TushareProvider`（免费档）= **不复权(raw)**（`adj_factor` 免费限频 1次/小时），`AkShareProvider` = **前复权(qfq)**；
- 升级 Tushare 积分后可切回 qfq（`_fetch_one` 里 `pro_bar` 加 `adj='qfq'` 一行即可）；
- 跨源对比时须注意口径差异（除权除息日附近 raw 与 qfq 不同）。

## 强制机制（运行时）

```python
# 每个 Provider 的 get_panel 返回前 MUST 执行：
sub = canonicalize_panel(sub)   # 索引名统一 + 代码补后缀
validate_panel(sub, "Provider名", fields)  # 违反即抛 ValueError
```

- `canonicalize_panel`：修复索引名（trade_date→date）、asset 代码补后缀；
- `validate_panel`：检查索引名/dtype/代码格式/字段软区间/0 占位；
- `validate_returns`：检查收益率索引与小数表示。

## 已知边界（校验器不覆盖）

- 细微单位错（如 turnover 0.02 vs 2%、volume 手与股都为正数）**运行时无法自动区分**——依赖 Provider 层换算正确 + 跨源一致性核对（见 `scripts/cross_source_check.py` 思路 / RESEARCH_LOG R2026-0804-05）；
- 复权口径差异不在校验器范围内（软区间检查无法分辨 raw/qfq 价格），由 Provider 文档声明。

## 测试

`tests/test_provider_contract.py`（19 项，无网络依赖）：
- normalize_code 各种写法 → 规范代码；
- validate_panel 拦住：索引名错 / 代码无后缀 / 0 占位 / 明显单位越界；
- LocalProvider 自带合规；
- canonicalize 修复 trade_date + 无后缀代码；
- validate_returns 拦住百分数误传。
