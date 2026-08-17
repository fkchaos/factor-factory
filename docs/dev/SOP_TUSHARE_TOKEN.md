# SOP：Tushare Token 接入与真实数据重测

> 本 SOP 由研究方（量化机构）提供，操作方（你）按步骤自行完成 token 的申请、配置与连接验证。
> 代码侧（`data/providers.py` 的 `TushareProvider`、一键重测脚本 `scripts/real_research.py`）已就绪，
> 你只需补齐"凭证 + 环境"，即可在本地一键重测 `overnight_intraday` 与 `ivol` 两个因子的**真实 alpha**。
>
> ⚠️ **token 属敏感凭证**：切勿提交进 git 仓库；本项目 `.gitignore` 已忽略 `.cache/` 与 `configs/*.yaml`，
> 但请将 token 仅放在环境变量或 `configs/tushare.yaml`（该文件已被忽略）。

---

## 步骤 1 · 注册 Tushare Pro 账号
- 打开 https://tushare.pro/register 注册（手机号即可）。
- 登录后进入「个人主页」→ 右上角「接口 TOKEN」复制你的 token（一长串字母数字）。

## 步骤 2 · 了解积分（重要）
Tushare 的接口按**积分**开放权限，不是所有数据都能拉：
- 注册即 **120 积分**（基础日线 `pro_bar` / `daily_basic` / `stock_basic` 通常可用）。
- 沪深300 指数日线 `index_daily` 一般基础权限即可。
- 要提高积分：完成**实名认证（+50）**、在**社区签到/发帖/贡献**（累计可达 2000+，解锁更多高级接口）。
- 本流水线只用到基础接口，120 积分即可跑通；但**首次全 A 拉取慢且可能触发限流**，见步骤 7。

## 步骤 3 · 安装 tushare（托管 Python venv）
本项目测试/运行统一用托管 venv（系统默认 python 无 pandas/pytest）：

```bash
# 在 factor-factory 目录下
VENV="C:/Users/jiaby1/.workbuddy/binaries/python/envs/default"
"$VENV/Scripts/pip.exe" install tushare
```

> 若 venv 不存在，先建：`"C:/Users/jiaby1/.workbuddy/binaries/python/versions/3.13.12/python.exe" -m venv "$VENV"`

## 步骤 4 · 配置 token（二选一）
**方式 A · 环境变量（推荐，最安全）**
```bash
# Windows PowerShell
$env:TUSHARE_TOKEN = "你的token"
# 或写进用户环境变量（系统属性 → 高级 → 环境变量），永久生效
```

**方式 B · 配置文件（已被 .gitignore 忽略，不会入库）**
复制模板并填入：
```bash
cp configs/tushare.yaml.example configs/tushare.yaml
# 编辑 configs/tushare.yaml，把 token: "YOUR_TOKEN_HERE" 改成你的真实 token
```

## 步骤 5 · 验证连接
```bash
cd D:/ai-workspace/WorkBuddy/A股研究/factor-factory
"$VENV/Scripts/python.exe" -c "from data.providers import TushareProvider; p=TushareProvider(); print('OK universe size=', len(p.list_universe('2024-12-31')))"
```
看到 `OK universe size= ...` 即连接成功。若报「积分不足 / 权限」请回到步骤 2 攒积分。

## 步骤 6 · 数据范围与字段映射（给研究方备案）
`TushareProvider` 已做单位统一，避免历史「vol 单位=手导致 100 倍偏差」的坑：
| Tushare 原始 | 内部字段 | 单位转换 |
|---|---|---|
| `pro_bar.vol` | `volume` | 手 ×100 → 股 |
| `pro_bar.amount` | `amount` | 千元 ×1000 → 元 |
| `daily_basic.total_mv` | `market_cap` | 万元 ×1e4 → 元 |
| `daily_basic.turnover` | `turnover` | 百分比，原样 |
| `index_daily.pct_chg` | 指数收益 | /100 → 小数收益率 |

- 股票池：`stock_basic(list_status='L')` 当前上市列表（**近似全 A，非严格 point-in-time**，会引入轻微幸存者偏差；Phase 4 改用指数/历史成分股）。
- 复权：默认前复权 `adj='qfq'`。
- 首次拉取会写缓存到 `.cache/tushare/*.parquet`，后续运行直接读缓存、不再调用 API。

## 步骤 7 · 限流与首次拉取预期
- `TushareProvider` 内置限流（默认 50 次/分钟）+ 重试退避。
- **首次全 A 拉取约 5000 只股票 × 2 接口 ≈ 上万次调用**，可能数小时且偶发限流——属正常。
- 建议先在 `scripts/real_research.py` 里把 `universe` 缩到沪深300（约 300 只）跑通验证，再放开全 A。
  改法：运行前设置环境变量 `FF_UNIVERSE=hs300`（脚本读取，见脚本注释）。

## 步骤 8 · 一键重测（核心动作）
```bash
cd D:/ai-workspace/WorkBuddy/A股研究/factor-factory
"$VENV/Scripts/python.exe" scripts/real_research.py
```
脚本会自动：
1. 读 token → 实例化 `TushareProvider`；
2. 拉取窗口（默认 2021-01-01 ~ 2024-12-31）日线 + 指数基准；
3. 对 `overnight_intraday`、`ivol` 跑单因子验证（RankIC/ICIR/分层/衰减）；
4. 跑组合回测（WalkForward + 二次冲击成本 + T+1 开盘）；
5. **自动把真实指标写入 `research/TEST_LOG.md` 与 `research/factor_cards/`**（覆盖合成数据的占位结论）。

## 步骤 9 · 故障排查
| 现象 | 原因 | 处理 |
|---|---|---|
| `需要 TUSHARE_TOKEN` | 未配置 | 回步骤 4 |
| `积分不足 / 权限不足` | 积分不够 | 回步骤 2 攒积分 |
| `每分钟最多访问该接口 N 次` | 限流 | 脚本已重试；仍频繁则调低 `calls_per_min` |
| `pro_bar 返回空` | 停牌/未上市/停牌期 | 正常，缓存跳过 |
| 首次极慢 | 全 A 拉取量大 | 先用 hs300 验证（步骤 7） |

## 安全与合规
- token 仅存环境变量 / `configs/tushare.yaml`（已 gitignore），**严禁**提交仓库或贴到聊天。
- 仅用于个人研究/模拟盘，**非实盘交易信号**；遵守 Tushare 使用条款与数据版权。
- 真实数据结论需经 Phase 3 的 DSR/PBO 过拟合审计（见 `validate/validator.py`）方可纳入生产组合。
