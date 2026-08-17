# 因子计划（预注册）：overnight_intraday

> 状态：✅ 已实现并通过 Phase 2 冒烟测试（回溯补登，原实现先于本计划，Walk-Forward 纪律要求补记）
> 计划日期：2026-08-04 ｜ 实现日期：2026-08-04 ｜ 负责人：量化研究组

## 1. 假设（经济学逻辑）
A 股存在显著微观结构异象：隔夜收益（open/prev_close-1）系统性为负、日内收益（close/open-1）为正，二者负相关（「拔河效应」，中信建投 2025-11）。
逻辑：散户盘后情绪在开盘集中释放制造隔夜负向跳空，专业资金盘中修复。做多「日内强、隔夜弱」方向捕捉反转 Alpha。

## 2. 因子定义
- `overnight = open / prev_close - 1`
- `intraday = close / open - 1`
- `factor = -(overnight - intraday)`（做多净日内方向）

## 3. 参数冻结（实现后不可改，改则视为新假设）
- 数据源：日 K 的 open/close（LocalProvider 已具备，零新增源）
- 窗口：单日（无滚动），仅用 as_of 当日 + 前一日 close
- 方向：反向（负值更大 = 更优）

## 4. 验证标准（门禁，任一不达标即降级为「观察」）
- RankIC ≥ 0.03（真实数据，非合成）
- |ICIR| ≥ 0.5
- 分层单调性肉眼可辨
- t ≥ 3.0
- 成本后（二次冲击 + 最低佣金）净夏普 > 0

## 5. 失败判定
- 合成随机数据上 RankIC ≈ 0（已验证：seed=7 时 ≈ -0.003，符合预期，证明框架无假显著）
- 真实数据上若 RankIC 不显著 → 因子无效，进 TEST_LOG 墓地，不进组合

## 6. 备注
- 前视防护：仅用 as_of 当日 open/close 与前一日 close，天然通过 assert_no_lookahead
- 合成数据结论**非真实**（无信号），真实 alpha 须等 Tushare/AkShare 接入后重测
