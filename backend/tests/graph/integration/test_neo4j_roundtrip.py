"""需要真实 Neo4j。默认跳过；RUN_NEO4J_INTEGRATION=1 时运行。"""

from __future__ import annotations

import os

import pytest

from app.config import get_settings
from app.domain.models import (
    ChangeKind,
    Competency,
    EvidenceGrade,
    Necessity,
    PublishState,
    Role,
    Skill,
    SkillObservation,
)
from app.graph.migrate import apply_schema
from app.graph.repository import Neo4jGraphRepository
from app.graph.session import Neo4jExecutor, create_driver

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("RUN_NEO4J_INTEGRATION") != "1",
        reason="默认跳过：设置 RUN_NEO4J_INTEGRATION=1 后连接真实 Neo4j 运行",
    ),
]

PREFIX = "jobe_it_"


@pytest.fixture(scope="module")
def executor() -> Neo4jExecutor:
    driver = create_driver()
    try:
        driver.verify_connectivity()
    except Exception as exc:  # noqa: BLE001 — 连不上就跳过，不让单测红
        driver.close()
        pytest.skip(f"Neo4j 不可用：{exc}")
    ex = Neo4jExecutor(driver)
    apply_schema(ex)
    yield ex
    ex.run(
        "MATCH (n) WHERE n.id STARTS WITH $prefix DETACH DELETE n",
        {"prefix": PREFIX},
        write=True,
    )
    driver.close()


@pytest.fixture
def repo(executor: Neo4jExecutor) -> Neo4jGraphRepository:
    executor.run(
        "MATCH (n) WHERE n.id STARTS WITH $prefix DETACH DELETE n",
        {"prefix": PREFIX},
        write=True,
    )
    return Neo4jGraphRepository(executor, get_settings().ontology_version)


def _role(role_id: str, name: str) -> Role:
    return Role(id=role_id, name=name, state=PublishState.PUBLISHED, family_id="backend")


def _skill(skill_id: str, name: str, parent_id: str | None = None) -> Skill:
    return Skill(
        id=skill_id,
        name=name,
        ontology_version="v0",
        parent_id=parent_id,
    )


def _obs(role_id: str, skill_id: str, period: str, weight: float) -> SkillObservation:
    return SkillObservation(
        role_id=role_id,
        skill_id=skill_id,
        period=period,
        weight=weight,
        posting_count=5,
        total_postings=10,
        ontology_version="v0",
    )


def test_idempotent_merge_does_not_duplicate_nodes(
    repo: Neo4jGraphRepository, executor: Neo4jExecutor
) -> None:
    role = _role(f"{PREFIX}role_dup", "重复写入岗")
    skill = _skill(f"{PREFIX}skill_dup", "Python")
    repo.upsert_role(role)
    repo.upsert_role(role)
    repo.upsert_skill(skill)
    repo.upsert_skill(skill)
    repo.put_observation(_obs(role.id, skill.id, "2026Q1", 0.4))
    repo.put_observation(_obs(role.id, skill.id, "2026Q1", 0.9))

    nodes = executor.run(
        "MATCH (n) WHERE n.id IN $ids RETURN labels(n)[0] AS label, count(*) AS n",
        {"ids": [role.id, skill.id]},
    )
    counts = {row["label"]: int(row["n"]) for row in nodes}
    assert counts["Role"] == 1
    assert counts["Skill"] == 1

    rels = executor.run(
        """
        MATCH (:Role {id: $rid})-[req:REQUIRES]->(:Skill {id: $sid})
        WHERE req.period = $period
        RETURN count(req) AS n, max(req.weight) AS weight
        """,
        {"rid": role.id, "sid": skill.id, "period": "2026Q1"},
    )
    assert rels[0]["n"] == 1
    assert rels[0]["weight"] == pytest.approx(0.9)

    loaded = repo.get_role(role.id)
    assert loaded is not None
    assert loaded.name == "重复写入岗"


def test_period_shards_do_not_overwrite_history(
    repo: Neo4jGraphRepository, executor: Neo4jExecutor
) -> None:
    role = _role(f"{PREFIX}role_hist", "分片岗")
    skill = _skill(f"{PREFIX}skill_hist", "Kubernetes")
    repo.upsert_role(role)
    repo.upsert_skill(skill)
    repo.put_observation(_obs(role.id, skill.id, "2026Q1", 0.2))
    repo.put_observation(_obs(role.id, skill.id, "2026Q2", 0.7))

    rels = executor.run(
        """
        MATCH (:Role {id: $rid})-[req:REQUIRES]->(:Skill {id: $sid})
        RETURN req.period AS period, req.weight AS weight
        ORDER BY period
        """,
        {"rid": role.id, "sid": skill.id},
    )
    assert [(row["period"], row["weight"]) for row in rels] == [
        ("2026Q1", 0.2),
        ("2026Q2", 0.7),
    ]
    q1 = repo.role_skills(role.id, "2026Q1")
    q2 = repo.role_skills(role.id, "2026Q2")
    assert q1[0].weight == pytest.approx(0.2)
    assert q2[0].weight == pytest.approx(0.7)
    snap = repo.snapshot_at("2026Q1")
    assert snap["requirements"][0]["weight"] == pytest.approx(0.2)


def test_diff_detects_added_removed_modified(
    repo: Neo4jGraphRepository,
) -> None:
    role = _role(f"{PREFIX}role_diff", "差异岗")
    py = _skill(f"{PREFIX}skill_py", "Python")
    dj = _skill(f"{PREFIX}skill_dj", "Django")
    redis = _skill(f"{PREFIX}skill_redis", "Redis")
    k8s = _skill(f"{PREFIX}skill_k8s", "Kubernetes")
    repo.upsert_role(role)
    for skill in (py, dj, redis, k8s):
        repo.upsert_skill(skill)

    c_lang = Competency(
        id=f"{PREFIX}comp_lang",
        role_id=role.id,
        statement="后端语言",
        skill_ids=[py.id, dj.id],
        necessity=Necessity.REQUIRED,
        grade=EvidenceGrade.MULTI_SOURCE,
        state=PublishState.PUBLISHED,
    )
    c_cache = Competency(
        id=f"{PREFIX}comp_cache",
        role_id=role.id,
        statement="缓存",
        skill_ids=[redis.id],
        necessity=Necessity.BONUS,
        grade=EvidenceGrade.SINGLE_SOURCE,
        state=PublishState.PUBLISHED,
    )
    c_orch = Competency(
        id=f"{PREFIX}comp_orch",
        role_id=role.id,
        statement="容器编排",
        skill_ids=[k8s.id],
        necessity=Necessity.REQUIRED,
        grade=EvidenceGrade.WEAK,
        state=PublishState.PUBLISHED,
    )
    repo.upsert_competency(c_lang)
    repo.upsert_competency(c_cache)
    repo.upsert_competency(c_orch)

    repo.put_observation(_obs(role.id, py.id, "2026Q1", 0.9))
    repo.put_observation(_obs(role.id, dj.id, "2026Q1", 0.4))
    repo.put_observation(_obs(role.id, redis.id, "2026Q1", 0.3))

    repo.put_observation(_obs(role.id, py.id, "2026Q2", 0.9))
    repo.put_observation(_obs(role.id, dj.id, "2026Q2", 0.8))
    repo.put_observation(_obs(role.id, k8s.id, "2026Q2", 0.6))

    changes = repo.diff("2026Q1", "2026Q2")
    by_comp = {c.competency_id: c.kind for c in changes}
    assert by_comp[c_lang.id] is ChangeKind.MODIFIED
    assert by_comp[c_cache.id] is ChangeKind.REMOVED
    assert by_comp[c_orch.id] is ChangeKind.ADDED
