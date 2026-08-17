"""build_deliverable.py 纯函数单测（不触发 baostock）。

覆盖：
1. allocate_fcode：从空 registry 起号 f0001a；从已有最大号 +1；同 fcode 幂等 upsert。
2. render_manifest：YAML 字段渲染正确（list/bool/None/null）。
3. _upsert_registry：新建 + 更新同一 fcode 不重复。
"""
import pandas as pd
import pytest

from scripts.build_deliverable import allocate_fcode, render_manifest, _upsert_registry


def test_allocate_fcode_from_empty(tmp_path):
    reg = tmp_path / "_REGISTRY.csv"
    code = allocate_fcode(reg, "overnight_intraday", "single")
    assert code == "f0001a"
    # 再分配应 +1
    code2 = allocate_fcode(reg, "ivol", "single")
    assert code2 == "f0002a"
    # 文件两行
    import csv
    with open(reg, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 2
    assert rows[0]["fcode"] == "f0001a" and rows[1]["fcode"] == "f0002a"


def test_allocate_fcode_combo_components(tmp_path):
    reg = tmp_path / "_REGISTRY.csv"
    code = allocate_fcode(reg, "combo_v1", "combo", components=["f0001a", "f0002a"])
    assert code.startswith("f")
    import csv
    with open(reg, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert rows[0]["type"] == "combo"
    assert rows[0]["components"] == "f0001a,f0002a"


def test_allocate_fcode_always_increments(tmp_path):
    reg = tmp_path / "_REGISTRY.csv"
    code1 = allocate_fcode(reg, "overnight_intraday", "single")  # f0001a
    # 再次分配 = 新号码（max+1），即使同名也分配新号（fcode 是唯一键，name 非唯一）
    code2 = allocate_fcode(reg, "overnight_intraday", "single")
    assert code1 == "f0001a"
    assert code2 == "f0002a"
    import csv
    with open(reg, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 2


def test_render_manifest_scalars_and_lists():
    out = render_manifest(
        fcode="f0001a", factor="overnight_intraday", components=["f0001a"],
        pit_certified=True, supersedes=None, pools=["hs300", "hs800"],
    )
    assert "fcode: f0001a" in out
    assert "pit_certified: true" in out
    assert "supersedes: null" in out
    assert "pools: [hs300, hs800]" in out
    assert "components: [f0001a]" in out


def test_upsert_registry_create_and_update(tmp_path):
    reg = tmp_path / "_REGISTRY.csv"
    _upsert_registry(reg, {"fcode": "f0001a", "name": "x", "type": "single",
                           "components": "", "status": "current", "supersedes": "",
                           "created": "2026-08-05", "note": ""})
    _upsert_registry(reg, {"fcode": "f0001a", "name": "x", "type": "single",
                           "components": "", "status": "superseded", "supersedes": "",
                           "created": "2026-08-05", "note": "v2 取代"})
    import csv
    with open(reg, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 1
    assert rows[0]["status"] == "superseded"
