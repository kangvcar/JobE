from __future__ import annotations

from app.graph.prerequisite import (
    HIERARCHY_QUERY,
    OVERRIDE_PREREQ,
    PAIR_COUNTS,
    SENIORITY_ROWS,
    SKILL_ROLE_COUNTS,
    UPSERT_PREREQ,
    PrerequisiteCandidate,
    PrerequisiteInferrer,
    infer_from_asymmetry,
    infer_from_hierarchy,
    infer_from_seniority,
    select_acyclic,
)
from tests.graph.fakes import FakeExecutor


def test_hierarchy_rule() -> None:
    out = infer_from_hierarchy([("cs", "algo"), ("algo", "algo")])
    assert out == [PrerequisiteCandidate(src="cs", dst="algo", rule="hierarchy", confidence=0.9)]


def test_asymmetry_rule() -> None:
    # git 几乎总是随 github-actions 出现，反过来不成立 → git 是前置
    role_counts = {"actions": 10, "git": 50}
    pair_counts = {("actions", "git"): 10}
    out = infer_from_asymmetry(role_counts, pair_counts)
    assert len(out) == 1
    assert out[0].src == "git"
    assert out[0].dst == "actions"
    assert out[0].rule == "cooccurrence_asymmetry"

    too_small = infer_from_asymmetry(role_counts, {("actions", "git"): 2})
    assert too_small == []


def test_seniority_rule() -> None:
    rows = [
        {"skill_id": "html", "role_id": "j1", "role_name": "初级前端"},
        {"skill_id": "html", "role_id": "j2", "role_name": "实习前端"},
        {"skill_id": "html", "role_id": "j3", "role_name": "初级工程师"},
        {"skill_id": "react", "role_id": "s1", "role_name": "高级前端"},
        {"skill_id": "react", "role_id": "s2", "role_name": "资深前端"},
        {"skill_id": "react", "role_id": "s3", "role_name": "前端架构师"},
    ]
    out = infer_from_seniority(rows)
    assert len(out) == 1
    assert out[0].src == "html"
    assert out[0].dst == "react"
    assert out[0].rule == "seniority_distribution"


def test_select_acyclic_drops_cycle_and_reverse() -> None:
    cands = [
        PrerequisiteCandidate("a", "b", "hierarchy", 0.9),
        PrerequisiteCandidate("b", "c", "cooccurrence_asymmetry", 0.7),
        PrerequisiteCandidate("c", "a", "seniority_distribution", 0.6),
        PrerequisiteCandidate("b", "a", "seniority_distribution", 0.5),
    ]
    accepted = select_acyclic(cands)
    pairs = {(c.src, c.dst) for c in accepted}
    assert ("a", "b") in pairs
    assert ("b", "c") in pairs
    assert ("c", "a") not in pairs
    assert ("b", "a") not in pairs


def test_inferrer_writes_edges_and_override() -> None:
    fake = FakeExecutor(
        [
            [{"src": "parent", "dst": "child"}],
            [{"skill_id": "actions", "role_count": 10}, {"skill_id": "git", "role_count": 40}],
            [{"skill_a": "actions", "skill_b": "git", "both_count": 10}],
            [
                {"skill_id": "html", "role_id": "j1", "role_name": "初级前端"},
                {"skill_id": "html", "role_id": "j2", "role_name": "实习前端"},
                {"skill_id": "react", "role_id": "s1", "role_name": "高级前端"},
                {"skill_id": "react", "role_id": "s2", "role_name": "资深前端"},
            ],
        ]
    )
    inferrer = PrerequisiteInferrer(fake, "v0")
    accepted = inferrer.infer("2026Q1")
    assert accepted
    assert fake.calls[0][0] == HIERARCHY_QUERY
    assert fake.calls[1][0] == SKILL_ROLE_COUNTS
    assert fake.calls[2][0] == PAIR_COUNTS
    assert fake.calls[3][0] == SENIORITY_ROWS
    writes = [c for c in fake.calls if c[2]]
    assert writes
    assert all(c[0] == UPSERT_PREREQ for c in writes)
    assert all(c[1]["src"] != c[1]["dst"] for c in writes)

    inferrer.override("html", "react", active=False)
    assert fake.last[0] == OVERRIDE_PREREQ
    assert fake.last[1]["active"] is False

    fake.queue([{"src": "html", "dst": "react", "rule": "manual", "confidence": 1.0}])
    listed = inferrer.prerequisites_of("html")
    assert listed[0]["dst"] == "react"
