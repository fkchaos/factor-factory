#!/bin/bash
# 迅投因子看板 · 稳健续抓（按目标分类精确勾选，不依赖"全选"）
# 关键修复：
#   1) "全选"点击无效 -> 改为逐个分类按其当前 --checked 状态切换，使最终仅目标分类勾选
#   2) 文件名 sanitize（/ : \ -> _）
#   3) 校验用 count_rows.py（兼容 裸数组 / 引号字符串 两种格式），路径用脚本所在目录
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
RAW="$HERE/cat_raw"
mkdir -p "$RAW"

CATS=("基础科目及衍生类因子" "情绪类因子" "质量类因子" "成长类因子" "每股指标因子" "风险/风格类因子" "技术指标因子" "动量类因子" "财务类因子")
safe() { echo "$1" | tr '/:\\' '___'; }

read_total() {
  agent-browser eval "(() => Array.from(document.querySelectorAll('tr')).filter(tr=>tr.querySelectorAll('td').length>=8).length)()" 2>/dev/null | tr -d '"'
}

# 设置过滤器：使最终仅 target 分类被勾选；返回 0 表示成功（恰好 target 勾选）
set_filter() {
  local cat="$1"
  agent-browser eval "location.reload(); 'r'" >/dev/null 2>&1
  agent-browser wait --load networkidle >/dev/null 2>&1
  sleep 1.5
  # 逐个分类按其当前 --checked 状态切换，使仅 target 勾选
  agent-browser eval "(() => { const cbs=[...document.querySelectorAll('.n-checkbox')]; const target='$cat'; for (const c of cbs){ const l=c.querySelector('.n-checkbox__label')?.textContent.trim(); if(!l||l==='全选') continue; const checked=c.className.includes('--checked'); const want=(l===target); if(checked!==want) c.click(); } return 'set'; })()" >/dev/null 2>&1
  sleep 2.8
  # 校验：9 个分类中恰好 target 被勾选
  local res
  res=$(agent-browser eval "(() => { const cbs=[...document.querySelectorAll('.n-checkbox')]; const st={}; for(const c of cbs){const l=c.querySelector('.n-checkbox__label')?.textContent.trim(); if(!l||l==='全选')continue; st[l]=c.className.includes('--checked');} const on=Object.entries(st).filter(([k,v])=>v).map(([k])=>k); return JSON.stringify({on, ok:(on.length===1 && on[0]==='$cat')}); })()" 2>/dev/null)
  echo "$res"
}

grab() {
  local safe="$1" total="$2"
  : > "$RAW/${safe}.json"
  local step=50 start end js
  for ((start=0; start<total; start+=step)); do
    end=$((start+step))
    js="(() => { const trs=Array.from(document.querySelectorAll('tr')).filter(tr=>tr.querySelectorAll('td').length>=8); const out=[]; for(let i=$start;i<Math.min($end,trs.length);i++){const tds=trs[i].querySelectorAll('td'); out.push(Array.from(tds).slice(0,8).map(td=>td.innerText.trim().replace(/\\n/g,' ')));} return JSON.stringify(out); })()"
    agent-browser eval "$js" >> "$RAW/${safe}.json" 2>/dev/null
  done
}

for i in "${!CATS[@]}"; do
  cat="${CATS[$i]}"; s=$(safe "$cat"); f="$RAW/${s}.json"
  # 已落盘且校验通过（能解析出≥1行）→ 跳过
  if [ -s "$f" ]; then
    n=$(python3 "$HERE/count_rows.py" "$f" 2>/dev/null)
    if [[ "$n" =~ ^[0-9]+$ ]] && [ "$n" -gt 0 ]; then
      echo "[$((i+1))/9] $cat 已存在且有效（${n}行），跳过"; continue
    fi
  fi
  echo "[$((i+1))/9] $cat 开始抓取"
  ok=0
  for attempt in 1 2 3; do
    res=$(set_filter "$cat")
    if echo "$res" | grep -q '"ok":true'; then
      total=$(read_total)
      echo "  过滤成功 total=$total (尝试 $attempt)"
      grab "$s" "$total"
      nv=$(python3 "$HERE/count_rows.py" "$f" 2>/dev/null)
      if [[ "$nv" =~ ^[0-9]+$ ]] && [ "$nv" -ge 1 ]; then ok=1; break; else echo "  抓取校验失败($nv)，重试..."; fi
    else
      echo "  过滤校验未通过 res=$res (尝试 $attempt)"
    fi
  done
  if [ "$ok" -eq 0 ]; then echo "  ❌ $cat 抓取失败"; fi
done

echo "=== 完成，各分类行数 ==="
for c in "${CATS[@]}"; do s=$(safe "$c"); f="$RAW/${s}.json"; if [ -s "$f" ]; then echo "$c: $(python3 "$HERE/count_rows.py" "$f" 2>/dev/null)行"; else echo "$c: 缺失"; fi; done
