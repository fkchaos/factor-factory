#!/bin/bash
# 迅投因子看板 · 续跑脚本（只抓缺失/空的分类，保留已落盘文件）
# 用法：bash research/xuntou_factor_kanban/scrape_continue.sh
set -u
OUT="research/xuntou_factor_kanban"
mkdir -p "$OUT/cat_raw"

CATS=("基础科目及衍生类因子" "情绪类因子" "质量类因子" "成长类因子" "每股指标因子" "风险/风格类因子" "技术指标因子" "动量类因子" "财务类因子")

grab_table() {
  local name="$1"
  local total=""
  for try in 1 2 3 4; do
    total=$(agent-browser eval "(() => Array.from(document.querySelectorAll('tr')).filter(tr=>tr.querySelectorAll('td').length>=8).length)()" 2>/dev/null | tr -d '"')
    if [[ "$total" =~ ^[0-9]+$ ]] && [ "$total" -gt 0 ]; then break; fi
    echo "  [retry $try] 行数获取为空，等待 2s..."
    sleep 2
  done
  echo "  [$name] 行数=$total"
  if ! [[ "$total" =~ ^[0-9]+$ ]] || [ "$total" -le 0 ]; then
    echo "  [跳过 $name] 无法获取行数"
    return 1
  fi
  : > "$OUT/cat_raw/${name}.json"   # 清空再写，避免脏数据
  local step=50 start end
  for ((start=0; start<total; start+=step)); do
    end=$((start+step))
    local js
    js="(() => { const trs=Array.from(document.querySelectorAll('tr')).filter(tr=>tr.querySelectorAll('td').length>=8); const out=[]; for (let i=$start; i<Math.min($end, trs.length); i++) { const tds=trs[i].querySelectorAll('td'); out.push(Array.from(tds).slice(0,8).map(td=>td.innerText.trim().replace(/\\n/g,' '))); } return JSON.stringify(out); })()"
    agent-browser eval "$js" >> "$OUT/cat_raw/${name}.json" 2>/dev/null
  done
  # 校验是否真的写进去了
  if [ ! -s "$OUT/cat_raw/${name}.json" ]; then
    echo "  [校验失败 $name] 文件为空，稍后重试"
    return 1
  fi
  return 0
}

for i in "${!CATS[@]}"; do
  cat="${CATS[$i]}"
  # 已落盘且非空 → 跳过
  if [ -s "$OUT/cat_raw/${cat}.json" ] && [ "$(wc -c < "$OUT/cat_raw/${cat}.json")" -gt 50 ]; then
    echo "[$((i+1))/9] $cat 已存在，跳过"
    continue
  fi
  echo "[$((i+1))/9] $cat 开始抓取"
  agent-browser eval "location.reload(); 'reloading'" > /dev/null 2>&1
  agent-browser wait --load networkidle > /dev/null 2>&1
  sleep 1.5
  # 取消全选
  agent-browser eval "(() => { const cb = [...document.querySelectorAll('.n-checkbox')].find(c => { const l = c.querySelector('.n-checkbox__label'); return l && l.textContent.trim()==='全选'; }); if (cb) cb.click(); return 'unselect-all'; })()" > /dev/null 2>&1
  sleep 1.5
  # 勾选目标分类
  agent-browser eval "(() => { const cb = [...document.querySelectorAll('.n-checkbox')].find(c => { const l = c.querySelector('.n-checkbox__label'); return l && l.textContent.trim()==='$cat'; }); if (cb) cb.click(); return 'checked'; })()" > /dev/null 2>&1
  sleep 2.5
  ok=1
  grab_table "$cat" || ok=0
  if [ "$ok" -eq 0 ]; then
    # 重试一次：再 reload + 勾选 + 抓
    echo "  [$cat] 首次失败，整轮重试一次..."
    agent-browser eval "location.reload(); 'reloading'" > /dev/null 2>&1
    agent-browser wait --load networkidle > /dev/null 2>&1
    sleep 1.5
    agent-browser eval "(() => { const cb = [...document.querySelectorAll('.n-checkbox')].find(c => { const l = c.querySelector('.n-checkbox__label'); return l && l.textContent.trim()==='全选'; }); if (cb) cb.click(); })()" > /dev/null 2>&1
    sleep 1.5
    agent-browser eval "(() => { const cb = [...document.querySelectorAll('.n-checkbox')].find(c => { const l = c.querySelector('.n-checkbox__label'); return l && l.textContent.trim()==='$cat'; }); if (cb) cb.click(); })()" > /dev/null 2>&1
    sleep 2.5
    grab_table "$cat"
  fi
  sleep 0.3
done
echo "完成。文件在 $OUT/cat_raw/"
echo "--- 各分类行数 ---"
for c in "${CATS[@]}"; do
  if [ -s "$OUT/cat_raw/${c}.json" ]; then
    echo "$c: $(wc -c < "$OUT/cat_raw/${c}.json") bytes"
  else
    echo "$c: 缺失"
  fi
done
