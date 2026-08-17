#!/usr/bin/env bash
# PIT 口径重出包 · 一键断点续跑
#
# 背景：2026-08-08 修掉 market_cap 假 PIT + 中性化前视注入后，
#       NEUTRALIZE_VERSION 升到 v2-pit-mcap，旧 .cache/factor_series 指纹全部失配，
#       f0001a/f0002a/f0003a 三个包的 IC 必须按新口径重算。
#
# 特性：**幂等 + 可断点续跑**。因子序列缓存按 (因子, 池, 起始日, 版本) 落盘，
#       中途被杀后重跑会命中已算好的池，只补没算完的部分，不会白跑。
#
# 用法（Git Bash）：
#   bash scripts/run_pit_rebuild.sh
# 日志：.cache/rebuild_snapshot/rebuild.log
#
# ⚠️ 跑之前确认没有别的进程在占 baostock / 大量吃内存：tasklist | grep python

set -u
cd "$(dirname "$0")/.." || exit 1

PY="C:/Users/jiaby1/.workbuddy/binaries/python/envs/default/Scripts/python.exe"
POOLS="sz50,hs300,zz500,hs800,zz1000,hs1800"
# 相关性只算 hs300（2026-08-09 起 correlation.csv 显式单池，池名写进 manifest.corr_pool）。
# 选 hs300 而不是 sz50：sz50 只有 50 只，截面相关噪声大；hs300 的对照因子缓存本轮已全算好，命中即免费。
CORR_POOL="hs300"
LOG=".cache/rebuild_snapshot/rebuild.log"
mkdir -p .cache/rebuild_snapshot

log() { echo "[$(date '+%F %T')] $*" | tee -a "$LOG"; }

log "=== PIT 重出包开始 ==="

log "--- f0001a overnight_intraday ---"
"$PY" scripts/build_deliverable.py --factor overnight_intraday --fcode f0001a \
    --name "隔夜-日内反转" --pools "$POOLS" --corr-pool "$CORR_POOL" >>"$LOG" 2>&1
rc1=$?; log "f0001a exit=$rc1"

log "--- f0002a ivol ---"
"$PY" scripts/build_deliverable.py --factor ivol --fcode f0002a \
    --name "特质波动率(低波溢价)" --pools "$POOLS" --corr-pool "$CORR_POOL" >>"$LOG" 2>&1
rc2=$?; log "f0002a exit=$rc2"

log "--- f0003a combo_equal_v1 ---"
"$PY" scripts/build_deliverable.py --factor combo_equal_v1 --fcode f0003a --combo \
    --components f0001a,f0002a --name "等权组合(隔夜反转+低波)" --pools "$POOLS" --corr-pool "$CORR_POOL" >>"$LOG" 2>&1
rc3=$?; log "f0003a exit=$rc3"

if [ "$rc1" -eq 0 ] && [ "$rc2" -eq 0 ] && [ "$rc3" -eq 0 ]; then
    log "--- 三包全绿，收口：刷看板 + 刷对外 JSON ---"
    "$PY" scripts/factor_board.py >>"$LOG" 2>&1 && log "factor_board.py ok"
    "$PY" scripts/export_to_strategy_json.py >>"$LOG" 2>&1 && log "export_to_strategy_json.py ok"
    rm -f .cache/rebuild_snapshot/IN_PROGRESS.md && log "已清除 IN_PROGRESS 断点标记"
    log "=== 全部完成 ==="
else
    log "!!! 有包失败，保留 IN_PROGRESS.md，看板与 JSON 未刷新（避免把混龄数字发出去）"
fi
