#!/bin/bash
# 迅投因子看板 · 按分类抓取脚本（2026-08-19）
# 用法：bash research/xuntou_factor_kanban/scrape_categories.sh
# 依赖：agent-browser 已在 PATH；页面已打开 https://xuntou.net/#/factorKanban?id=OBSLQu
set -u
OUT="research/xuntou_factor_kanban"
mkdir -p "$OUT/cat_raw"
rm -f "$OUT/cat_raw"/*.json

# 分类名（与页面 checkbox label 完全一致）
CATS=("基础科目及衍生类因子" "情绪类因子" "质量类因子" "成长类因子" "每股指标因子" "风险/风格类因子" "技术指标因子" "动量类因子" "财务类因子")

grab_table() {
  # $1 = 分类名；抓取当前表格全部行（8列）到 cat_raw/<idx>_<name>.json
  local name="$1"
  local total=""
  for try in 1 2 3; do
    total=$(agent-browser eval "(() => Array.from(document.querySelectorAll('tr')).filter(tr=>tr.querySelectorAll('td').length>=8).length)()" 2>/dev/null | tr -d '"')
    if [[ "$total" =~ ^[0-9]+$ ]] && [ "$total" -gt 0 ]; then break; fi
    echo "  [retry $try] 行数获取为空，等待 2s..."
    sleep 2
  done
  echo "  [$name] 行数=$total"
  local step=50 start end
  for ((start=0; start<total; start+=step)); do
    end=$((start+step))
    local js
    js="(() => { const trs=Array.from(document.querySelectorAll('tr')).filter(tr=>tr.querySelectorAll('td').length>=8); const out=[]; for (let i=$start; i<Math.min($end, trs.length); i++) { const tds=trs[i].querySelectorAll('td'); out.push(Array.from(tds).slice(0,8).map(td=>td.innerText.trim().replace(/\\n/g,' '))); } return JSON.stringify(out); })()"
    agent-browser eval "$js" >> "$OUT/cat_raw/${name}.json" 2>/dev/null
  done
}

for i in "${!CATS[@]}"; do
  cat="${CATS[$i]}"
  echo "[$((i+1))/9] $cat"
  # 0) 强制整页刷新（open 对同一 URL 不刷新，SPA hash 路由；reload 才重置为全勾）
  agent-browser eval "location.reload(); 'reloading'" > /dev/null 2>&1
  agent-browser wait --load networkidle > /dev/null 2>&1
  sleep 1.5
  # 1) 点"全选"外层 div → 全部取消（Naive UI：div.click 可靠，label 无效）
  agent-browser eval "(() => { const cb = [...document.querySelectorAll('.n-checkbox')].find(c => { const l = c.querySelector('.n-checkbox__label'); return l && l.textContent.trim()==='全选'; }); if (cb) cb.click(); return 'unselect-all'; })()" > /dev/null 2>&1
  sleep 1.5
  # 2) 勾选目标分类
  agent-browser eval "(() => { const cb = [...document.querySelectorAll('.n-checkbox')].find(c => { const l = c.querySelector('.n-checkbox__label'); return l && l.textContent.trim()==='$cat'; }); if (cb) cb.click(); return 'checked'; })()" > /dev/null 2>&1
  sleep 2.5
  # 3) 抓表
  grab_table "$cat"
  sleep 0.3
done
echo "完成。原始文件在 $OUT/cat_raw/"
