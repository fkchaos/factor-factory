#!/usr/bin/env python3
# 稳健抓取迅投因子看板分类数据：每次只 toggle 一个 checkbox，重新查询、Python 外层循环收敛到"仅勾目标分类"。
import subprocess, json, time, os, sys, shlex

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "cat_raw")
os.makedirs(RAW, exist_ok=True)

def _resolve_ab():
    try:
        r = subprocess.run(["bash", "-c", "command -v agent-browser"],
                           capture_output=True, text=True, timeout=20)
        p = r.stdout.strip()
        if p:
            return p
    except Exception:
        pass
    return "/c/Users/jiaby1/.workbuddy/binaries/node/versions/22.22.2/agent-browser"

AB = _resolve_ab()

def ab(args, timeout=90):
    cmd = shlex.quote(AB) + " " + " ".join(shlex.quote(a) for a in args)
    rr = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True, timeout=timeout)
    return rr.stdout.strip()

CATS = ["基础科目及衍生类因子", "情绪类因子", "质量类因子", "成长类因子",
        "每股指标因子", "风险/风格类因子", "技术指标因子", "动量类因子", "财务类因子"]

CHECKBOX_JS = "(() => { const all=[...document.querySelectorAll('.n-checkbox')]; const trs=Array.from(document.querySelectorAll('tr')).filter(tr=>tr.querySelectorAll('td').length>=8); return JSON.stringify({rows: trs.length, checked: all.filter(c=>c.className.includes('--checked')).map(c=>c.querySelector('.n-checkbox__label')?.textContent.trim())}); })()"

def get_state():
    try:
        obj = json.loads(ab(["eval", CHECKBOX_JS]))
        if isinstance(obj, str):
            obj = json.loads(obj)
        if isinstance(obj, dict):
            return obj
    except Exception:
        pass
    return {"rows": -1, "checked": []}

def click_one_non_target(target):
    js = f"""(() => {{ const t={json.dumps(target)}; const cbs=[...document.querySelectorAll('.n-checkbox')]; const v=cbs.find(c=>{{const l=c.querySelector('.n-checkbox__label')?.textContent.trim(); return l!=='全选'&&l!==t&&c.className.includes('--checked');}}); if(v){{v.click(); return 'clicked:'+(v.querySelector('.n-checkbox__label')?.textContent.trim());}} return 'none'; }})()"""
    ab(["eval", js])

def restore(target):
    js = f"""(() => {{ const t={json.dumps(target)}; const c=[...document.querySelectorAll('.n-checkbox')].find(c=>c.querySelector('.n-checkbox__label')?.textContent.trim()===t); if(c && !c.className.includes('--checked')) c.click(); return 'restore'; }})()"""
    ab(["eval", js])

def parse_eval(out):
    out = out.strip()
    if not out:
        return []
    try:
        obj = json.loads(out)
    except Exception:
        return parse_concat(out)
    if isinstance(obj, str):
        try:
            obj = json.loads(obj)
        except Exception:
            return []
    return obj if isinstance(obj, list) else []

def parse_concat(txt):
    rows = []; dec = json.JSONDecoder(); i = 0; n = len(txt)
    while i < n:
        while i < n and txt[i] in " \t\r\n":
            i += 1
        if i >= n:
            break
        try:
            o, e = dec.raw_decode(txt, i); rows.append(o); i = e
        except json.JSONDecodeError:
            j = txt.find("[", i + 1)
            if j == -1:
                break
            i = j
    return rows

def grab_table():
    all_rows = []
    for start in range(0, 400, 50):
        js = f"""(() => {{ const trs=[...document.querySelectorAll('tr')].filter(tr=>tr.querySelectorAll('td').length>=8); const s=trs.slice({start},{start+50}); return JSON.stringify(s.map(tr=>[...tr.querySelectorAll('td')].map(td=>td.textContent.trim()))); }})()"""
        chunk = parse_eval(ab(["eval", js]))
        if not chunk:
            break
        all_rows.extend(chunk)
        if len(chunk) < 50:
            break
    return all_rows

def sanitize(name):
    return name.replace("/", "_")

def scrape(cat):
    ab(["eval", "location.reload(); 'r'"])
    ab(["wait", "--load", "networkidle"])
    time.sleep(2)
    for _ in range(15):
        st = get_state()
        if cat not in st.get("checked", []):
            restore(cat); time.sleep(1.5); continue
        non = [c for c in st["checked"] if c not in (cat, "全选")]
        if not non:
            break
        click_one_non_target(cat); time.sleep(1.5)
    st = get_state()
    rows = st.get("rows", -1)
    if cat not in st.get("checked", []) or rows <= 0 or rows >= 380:
        print(f"[FAIL] {cat}: rows={rows} checked={st.get('checked')}")
        return False
    data = grab_table()
    if data and len(data) != rows:
        print(f"[WARN] {cat}: 表格行数={rows} 抓取={len(data)}，以抓取为准")
    fn = os.path.join(RAW, sanitize(cat) + ".json")
    with open(fn, "w", encoding="utf-8") as f:
        for row in data:
            f.write(json.dumps(row, ensure_ascii=False))
    print(f"[OK] {cat}: 抓取 {len(data)} 行 -> {os.path.basename(fn)}")
    return True

if __name__ == "__main__":
    targets = [a for a in sys.argv[1:] if a in CATS]
    if not targets:
        targets = CATS
    for t in targets:
        scrape(t)
