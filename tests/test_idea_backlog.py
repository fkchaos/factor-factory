"""idea_backlog 轻量测试：存储 / 漏斗 / 复盘，不依赖 baostock。"""
import os
import tempfile
from datetime import date

import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from idea_backlog import (  # noqa: E402
    add_idea, load_backlog, funnel_check, promote, to_pipeline,
    set_hit, review_stats, allocate_idea_id, SOURCE_TYPES,
)


@pytest.fixture
def path():
    with tempfile.TemporaryDirectory() as d:
        yield os.path.join(d, "research", "idea_backlog.csv")


def test_add_paper_with_hypothesis_hypothesized(path):
    r = add_idea(path, "paper", "动量与反转学术经典", hypothesis="X 高→未来收益高",
                 rationale="JF 1993", source_ref="Jegadeesh 1993")
    assert r["status"] == "hypothesized"
    assert r["confidence_seed"] == "high"
    assert r["idea_id"].startswith("i")


def test_add_forum_without_hypothesis_stays_backlog(path):
    r = add_idea(path, "forum", "股吧说 XX 必涨")
    assert r["status"] == "backlog"
    assert r["confidence_seed"] == "low"  # 论坛强制 low


def test_forum_with_hypothesis_can_hypothesize(path):
    r = add_idea(path, "forum", "论坛观察到连板股次日易分歧",
                 hypothesis="连板数高→次日收益低", rationale="游资盘感")
    assert r["status"] == "hypothesized"
    assert r["confidence_seed"] == "low"


def test_funnel_blocks_no_hypothesis(path):
    r = add_idea(path, "observation", "看盘觉得某现象怪")
    ok, reason = funnel_check(r)
    assert ok is False
    assert "假设" in reason


def test_funnel_passes_with_hypothesis(path):
    r = add_idea(path, "paper", "动量", hypothesis="X 高→收益高")
    ok, reason = funnel_check(r)
    assert ok is True


def test_promote_backlog_to_hypothesized(path):
    r0 = add_idea(path, "observation", "看盘异动")
    assert r0["status"] == "backlog"
    r1 = promote(path, r0["idea_id"], "异动后3日收益偏高")
    assert r1["status"] == "hypothesized"
    assert r1["hypothesis"]


def test_to_pipeline_requires_funnel(path):
    r0 = add_idea(path, "observation", "看盘异动")
    with pytest.raises(ValueError):  # 没假设，漏斗挡住
        to_pipeline(path, r0["idea_id"], linked_fcode="f0009a")


def test_to_pipeline_ok(path):
    r0 = add_idea(path, "paper", "动量", hypothesis="X 高→收益高")
    r1 = to_pipeline(path, r0["idea_id"], linked_fcode="f0009a")
    assert r1["status"] == "in_pipeline"
    assert r1["linked_fcode"] == "f0009a"


def test_review_stats_hit_rate(path):
    a = add_idea(path, "paper", "m1", hypothesis="X→收益高")
    b = add_idea(path, "forum", "f1", hypothesis="Y→收益低")
    c = add_idea(path, "forum", "f2", hypothesis="Z→收益高")
    set_hit(path, a["idea_id"], "hit")
    set_hit(path, b["idea_id"], "miss")
    set_hit(path, c["idea_id"], "hit")
    stats = review_stats(path)
    assert stats["paper"]["n"] == 1 and stats["paper"]["hit_rate"] == 1.0
    assert stats["forum"]["n"] == 2 and stats["forum"]["hit_rate"] == 0.5


def test_allocate_idea_id_sequence(path):
    d = date(2026, 8, 5)
    i1 = allocate_idea_id(path, d)
    add_idea(path, "paper", "p1", hypothesis="h", today=d)
    i2 = allocate_idea_id(path, d)
    assert i1 == "i20260805-001"
    assert i2 == "i20260805-002"


def test_source_type_validation(path):
    with pytest.raises(ValueError):
        add_idea(path, "not_a_source", "x", hypothesis="h")
