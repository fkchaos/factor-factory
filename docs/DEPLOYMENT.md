# DEPLOYMENT · 部署与运维

> 面向想在本地跑起 factor-factory 的部署者 / 运维。覆盖环境、依赖、数据源、数据准备、定时任务、GitHub 同步。
> 所有涉及凭证的步骤均**脱敏**；真实 token 只存本地，绝不入库（见 `.gitignore`）。

---

## 1. 环境要求

- **Python ≥ 3.11**（本仓库测试基于 3.13 托管 venv）。
- 操作系统：Windows / Linux / macOS 均可；路径示例以 Windows 为主。
- 磁盘：`.cache/` 拉取全市场（hs1800）行情后约数 GB parquet，**已被 .gitignore 忽略，不入库**。

## 2. 安装

```bash
# 克隆（公开仓）
git clone https://github.com/fkchaos/factor-factory.git
cd factor-factory

# 建隔离 venv（推荐）
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate

# 安装为可编辑包（开发 + BaoStock 数据源）
pip install -e ".[dev,data-baostock]"
```

核心依赖：`pandas / numpy / scipy`。可选数据源适配器：`baostock`（免积分，默认）、`tushare`、`akshare`。

## 3. 数据源与凭证

因子计算依赖行情/财务数据，由 `data/` 下的 `DataProvider` 适配器提供，**只认接口不认实现**：

| 适配器 | 积分要求 | 说明 |
|---|---|---|
| `BaoStockProvider` | **免积分** | 前复权/换手率/指数池全解锁，默认数据源 |
| `TushareProvider` | 需 token（120 积分起） | 高级字段更全；token 配置 SOP 见 `docs/dev/SOP_TUSHARE_TOKEN.md` |
| `AkShareProvider` | 免积分 | Tushare 限流时的 fallback |
| `LocalProvider` | 无 | 测试用确定性 fixture |

**凭证安全**：
- Tushare token **仅**存环境变量 `TUSHARE_TOKEN` 或 `configs/tushare.yaml`（后者已被 `.gitignore` 忽略）。
- 切勿把 token 提交进仓库或贴到聊天。

## 4. 数据准备

首次运行需拉取基础行情缓存（后续读缓存、不再频繁调 API）：

```bash
make data          # = python .cache/cache_universe.py hs1800
```

全市场首次拉取较慢（可能数小时、偶发限流，属正常），可先用沪深300 验证：设置环境变量 `FF_UNIVERSE=hs300` 缩小范围。

## 5. 常用任务（Makefile）

| 命令 | 作用 |
|---|---|
| `make board` | 刷新看板 `docs/factor_board.html` |
| `make factor F=… FCODE=… NAME=… POOLS=…` | 构建一个因子包 |
| `make signal S=… SCODE=… NAME=…` | 构建一个信号包 |
| `make test` | 跑全量 pytest |
| `make export` | 导出策略组 JSON 交付物（`deliverables/strategy_export/`） |
| `make sync` | 推送当前状态到 GitHub 公开仓（交互会话用） |

## 6. 定时任务（自动化推进）

本仓库配了两个自动化（在你自己的 WorkBuddy / cron 环境里按需启用），**全程零用户交互**——只刷新看板与状态文件，不弹窗、不提问：

| 自动化 | 频率 | 职责 |
|---|---|---|
| 每日推进器 | 每日 21:00 | 数据检查 → 因子线自检(P4/P5/P7) → 信号线出包 → 灵感池消费(top-2) → 刷新看板 → 同步 HANDOFF → 写 CHANGELOG |
| 因子侦察兵 | 周一/四 12:00 | 扫描外部源补充灵感池；灵感池 ≥ 60 时自动停供（护栏） |

> 你只需看 `docs/factor_board.html` 与直接找主理人；cron 输出无需阅读。

## 7. 同步到 GitHub

仓库为公开仓，交付物与文档均可提交：

```bash
git add -A
git commit -m "chore: 交付批次 + 文档"
git push          # 经本地 Git 凭证（GCM）推公开仓
```

或交互会话中 `make sync`（封装 `scripts/gh_sync.py`）。**注意**：`.cache/` 大文件与凭证已被 `.gitignore` 排除，不会误传。

## 8. 验证

```bash
make test          # pytest：前视防护 / 数据契约 / 确定性 fixture 必须全绿
```

若测试失败，优先看 `tests/` 下对应专项测试（前视防护见 `tests/test_lookahead.py`）。
