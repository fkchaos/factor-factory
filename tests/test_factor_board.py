"""factor_board 看板生成器测试。"""
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.factor_board import (
    build_rows,
    collect_implementations,
    render_html,
)


def test_collect_implementations_finds_factor_classes():
    impls = collect_implementations()
    factors = [i for i in impls if i["kind"] == "factor"]
    names = {i["name"] for i in factors}
    # 7 个真实因子类都该被识别（鸭子类型，无显式基类）
    for expect in {
        "Momentum20Factor", "Reversal5Factor", "SizeFactor",
        "IvolFactor", "OvernightIntradayFactor",
        "OvernightGapFactor", "LimitUpSealFactor",
    }:
        assert expect in names, f"未识别因子类 {expect}"
    # 特征工厂作为单独 kind 出现
    assert any(i["kind"] == "feature_factory" for i in impls)
    # 不应把 interface.py 里的 Factor 协议本体算成因子
    assert not any(i["name"] == "Factor" for i in factors)


def test_build_rows_empty_registry_all_researching_or_idea():
    impls = collect_implementations()
    ideas = [
        {"idea_id": "iX-001", "source_type": "forum", "status": "hypothesized",
         "confidence_seed": "low", "raw_idea": "论坛灵感A", "hypothesis": "高X→未来收益低",
         "source_ref": "url"},
        {"idea_id": "iX-002", "source_type": "paper", "status": "in_pipeline",
         "confidence_seed": "high", "fcode": "f0003a", "raw_idea": "管线中B",
         "hypothesis": "Y高→未来收益高", "source_ref": "JF"},
        {"idea_id": "iX-003", "source_type": "paper", "status": "rejected",
         "confidence_seed": "high", "raw_idea": "被拒C", "reject_reason": "PBO过高",
         "hypothesis": "", "source_ref": ""},
    ]
    rows = build_rows(impls, ideas, registry=[])
    stages = {}
    for r in rows:
        stages.setdefault(r["stage"], 0)
        stages[r["stage"]] += 1
    # 已交付=0（无 registry）；研究中含 8 impls + 1 in_pipeline；灵感=1；拒绝=1
    assert stages.get("delivered", 0) == 0
    assert stages.get("researching", 0) == 8 + 1
    assert stages.get("idea", 0) == 1
    assert stages.get("rejected", 0) == 1
    # in_pipeline 的条目 code 应带上 fcode
    pipe = [r for r in rows if r["stage"] == "researching" and "f0003a" in r["code"]]
    assert pipe, "in_pipeline 条目应显示 fcode"


def test_build_rows_delivered_not_duplicated_in_researching():
    impls = collect_implementations()
    # 假设 Momentum20Factor 已交付（registry 里有 name 匹配）
    registry = [{"fcode": "f0009a", "name": "Momentum20Factor", "type": "single",
                "rationale": "经典动量", "delivered_at": "2026-08-10"}]
    rows = build_rows(impls, ideas=[], registry=registry)
    delivered = [r for r in rows if r["stage"] == "delivered"]
    researching = [r for r in rows if r["stage"] == "researching"]
    assert len(delivered) == 1
    # 已交付的 Momentum20Factor 不应再出现在研究中
    assert not any(r["title"] == "Momentum20Factor" for r in researching)


def test_render_html_contains_stages_and_legend(tmp_path):
    rows = build_rows(collect_implementations(), ideas=[], registry=[])
    out = render_html(rows, generated="2026-08-06 12:00", hs_n=1000)
    assert "<!doctype html>" in out
    for label in ("已交付", "研究中", "灵感池", "已拒绝"):
        assert label in out
    assert "生命周期" in out  # footer legend
    assert "1000/1572" in out  # hs1800 进度
