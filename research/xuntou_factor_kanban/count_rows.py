#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""健壮解析迅投分类原始 json：兼容 裸数组拼接 与 agent-browser 返回的 引号字符串 两种格式。
用法：python3 count_rows.py <file>            -> 打印行数
      python3 count_rows.py <file> --dump      -> 打印解析后的 list（调试用）
"""
import json, sys

def load_rows(txt):
    txt = txt.strip()
    if not txt:
        return []
    # 情形A：整段是 JSON 字符串（以 " 开头），先解一层引号得到内部文本
    if txt[0] == '"':
        try:
            inner = json.loads(txt)
            if isinstance(inner, str):
                txt = inner.strip()
        except Exception:
            pass
    # 情形B/C：裸数组，可能多段拼接 [..][..]
    wrapped = '[' + txt.replace('][', '],[') + ']'
    try:
        data = json.loads(wrapped)
    except Exception:
        # 兜底：逐段 raw_decode
        data = []
        dec = json.JSONDecoder()
        i, n = 0, len(txt)
        while i < n:
            while i < n and txt[i] in ' \t\r\n':
                i += 1
            if i >= n:
                break
            try:
                o, e = dec.raw_decode(txt, i)
                data.append(o)
                i = e
            except Exception:
                nx = txt.find('[', i + 1)
                if nx == -1:
                    break
                i = nx
    # 归一：若外层只包了一个“行数组”，展开
    if len(data) == 1 and isinstance(data[0], list) and data[0] and isinstance(data[0][0], list):
        data = data[0]
    return data

if __name__ == '__main__':
    fp = sys.argv[1]
    dump = '--dump' in sys.argv
    txt = open(fp, encoding='utf-8').read()
    rows = load_rows(txt)
    if dump:
        print(json.dumps(rows, ensure_ascii=False)[:2000])
    else:
        print(len(rows))
