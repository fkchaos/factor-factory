#!/usr/bin/env bash
# 批量构建 P0 价格类因子（f0012a / f0013a / f0016a）
# 复用 hs300 缓存面板（turnover / amount 列已在缓存中，无需重拉数据）。
# 在 f0011a 构建完成后运行，避免并发读缓存争抢。
set -e
cd /d/ai-workspace/WorkBuddy/A股研究/factor-factory
PY=/c/Users/jiaby1/.workbuddy/binaries/python/envs/default/Scripts/python.exe
LOG=research/xuntou_factor_kanban/batch2_build.log
: > "$LOG"

build() {
  local factor="$1" fcode="$2" name="$3"
  echo "===== [$(date +%H:%M:%S)] 构建 $fcode ($factor) =====" | tee -a "$LOG"
  "$PY" scripts/build_deliverable.py \
    --factor "$factor" --fcode "$fcode" --name "$name" \
    --pools hs300 --window-start 2020-01-01 --corr-pool hs300 2>&1 | tee -a "$LOG"
  echo "===== [$(date +%H:%M:%S)] $fcode 完成 (exit ${PIPESTATUS[0]}) =====" | tee -a "$LOG"
}

build avg_turnover_10d  f0012a "10日平均换手率"
build avg_turnover_240d f0013a "240日平均换手率"
build amount_std_20d    f0016a "20日成交金额标准差"

echo "ALL DONE at $(date +%H:%M:%S)" | tee -a "$LOG"
