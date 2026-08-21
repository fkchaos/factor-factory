#!/usr/bin/env bash
# 批量构建 P1 价格/量能类因子（9 个），hs300 / PIT 口径 / exec_lag=1 / DSR+PBO 审计
# 编号 f0017a–f0025a（f0014a/f0015a 留给数据阻塞的周转天数因子）
set -u
PY=/c/Users/jiaby1/.workbuddy/binaries/python/envs/default/Scripts/python.exe
cd /d/ai-workspace/WorkBuddy/A股研究/factor-factory

build() {
  local fac="$1" fcode="$2" name="$3"
  echo "=== build $fcode ($fac) ==="
  $PY scripts/build_deliverable.py --factor "$fac" --fcode "$fcode" --name "$name" \
    --pools hs300 --window-start 2020-01-01 --corr-pool hs300 2>&1 | tail -5
  echo "exit=$?"
}

build avg_turnover_5d   f0017a "5日平均换手率"
build ema_5d            f0018a "5日EMA"
build ema_10d           f0019a "10日EMA"
build ema_12d           f0020a "12日EMA"
build ema_120d          f0021a "120日EMA"
build ma_5d             f0022a "5日MA"
build amount_ma_20d     f0023a "20日成交金额MA"
build money_flow_ma_20d f0024a "20日资金流量"
build bollinger_upper_20d f0025a "布林上轨(20日)"

echo "=== ALL DONE ==="
