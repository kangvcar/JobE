from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from app.domain.models import (
    ChangeKind,
    Competency,
    CompetencyChange,
    EvidenceGrade,
    Necessity,
    PublishState,
    Role,
    Skill,
    SkillObservation,
)
from app.graph.repository import (
    DIFF_PERIOD,
    GET_ROLE,
    PUT_OBSERVATION,
    PUT_OBSERVATIONS,
    RECORD_CHANGE,
    ROLE_SKILLS,
    SNAPSHOT_AT,
    UPSERT_COMPETENCY,
    UPSERT_ROLE,
    UPSERT_ROLES,
    UPSERT_SKILL,
    Neo4jGraphRepository,
    compute_competency_diff,
    role_from_props,
)
from tests.graph.fakes import FakeExecutor


def _repo(executor: FakeExecutor | None = None) -> tuple[Neo4jGraphRepository, FakeExecutor]:
    fake = executor or FakeExecutor()
    return Neo4jGraphRepository(fake, "v0"), fake


def test_upsert_role_is_merge_and_handles_null_family() -> None:
    repo, fake = _repo()
    role = Role(id="r1", name="后端工程师", state=PublishState.PUBLISHED)
    assert repo.upsert_role(role) == "r1"
    cypher, params, write = fake.last
    assert cypher == UPSERT_ROLE
    assert write is True
    assert params["id"] == "r1"
    assert params["family_id"] is None
    assert params["state"] == "published"
    assert "FOREACH" in cypher


def test_upsert_skill_and_competency_use_constants() -> None:
    repo, fake = _repo()
    repo.upsert_skill(
        Skill(id="s1", name="Python", ontology_version="v0", parent_id="s0", cluster_id="k1")
    )
    assert fake.calls[0][0] == UPSERT_SKILL
    assert fake.calls[0][1]["parent_id"] == "s0"
    repo.upsert_competency(
        Competency(
            id="c1",
            role_id="r1",
            statement="能独立交付后端服务",
            skill_ids=["s1", "s2"],
            necessity=Necessity.REQUIRED,
            grade=EvidenceGrade.MULTI_SOURCE,
            state=PublishState.PUBLISHED,
        )
    )
    assert fake.calls[1][0] == UPSERT_COMPETENCY
    assert fake.calls[1][1]["skill_ids"] == ["s1", "s2"]
    assert fake.calls[1][1]["grade"] == "multi_source"


def test_record_change_sets_explicit_superseded() -> None:
    repo, fake = _repo()
    change = CompetencyChange(
        id="ch1",
        role_id="r1",
        competency_id="c1",
        kind=ChangeKind.ADDED,
        after="Python",
        reason="新岗位要求",
        occurred_on=date(2026, 3, 31),
        recorded_at=datetime(2026, 4, 1, tzinfo=UTC),
        state=PublishState.PUBLISHED,
    )
    assert repo.record_change(change) == "ch1"
    cypher, params, write = fake.last
    assert cypher == RECORD_CHANGE
    assert write is True
    assert params["superseded"] is False
    assert params["occurred_on"] == "2026-03-31"


def test_put_observation_shards_by_period() -> None:
    repo, fake = _repo()
    repo.put_observation(
        SkillObservation(
            role_id="r1",
            skill_id="s1",
            period="2026Q1",
            weight=0.8,
            posting_count=12,
            total_postings=40,
            ontology_version="v0",
        )
    )
    cypher, params, write = fake.last
    assert cypher == PUT_OBSERVATION
    assert write is True
    assert params["period"] == "2026Q1"
    assert params["ontology_version"] == "v0"
    assert "REQUIRES {period: $period, ontology_version: $ontology_version}" in cypher


def test_put_observations_unwinds_rows() -> None:
    repo, fake = _repo()
    assert repo.put_observations([]) == 0
    obs = SkillObservation(
        role_id="r1",
        skill_id="s1",
        period="2026Q1",
        weight=0.8,
        posting_count=12,
        total_postings=40,
        ontology_version="v0",
    )
    assert repo.put_observations([obs]) == 1
    cypher, params, write = fake.last
    assert cypher == PUT_OBSERVATIONS
    assert write is True
    assert params["rows"][0]["role_id"] == "r1"
    assert "UNWIND $rows" in cypher


def test_upsert_roles_unwinds_rows() -> None:
    repo, fake = _repo()
    assert repo.upsert_roles([]) == 0
    assert repo.upsert_roles([Role(id="r1", name="后端", state=PublishState.PUBLISHED)]) == 1
    cypher, params, write = fake.last
    assert cypher == UPSERT_ROLES
    assert write is True
    assert params["rows"][0]["id"] == "r1"


def test_put_observation_requires_role_id_and_valid_period() -> None:
    repo, _ = _repo()
    with pytest.raises(ValueError, match="role_id"):
        repo.put_observation(
            SkillObservation(
                role_id=None,
                skill_id="s1",
                period="2026Q1",
                weight=0.1,
                posting_count=1,
                total_postings=1,
                ontology_version="v0",
            )
        )
    with pytest.raises(ValueError, match="YYYYQn"):
        repo.put_observation(
            SkillObservation(
                role_id="r1",
                skill_id="s1",
                period="2026H1",
                weight=0.1,
                posting_count=1,
                total_postings=1,
                ontology_version="v0",
            )
        )


def test_get_role_maps_and_returns_none() -> None:
    fake = FakeExecutor(
        [
            [
                {
                    "role": {
                        "id": "r1",
                        "name": "后端工程师",
                        "state": "published",
                        "is_emerging": True,
                        "signal_strength": 0.4,
                        "responsibilities": ["设计接口"],
                        "created_at": "2026-01-01T00:00:00+00:00",
                    }
                }
            ]
        ]
    )
    repo = Neo4jGraphRepository(fake, "v0")
    role = repo.get_role("r1")
    assert role is not None
    assert role.name == "后端工程师"
    assert role.state is PublishState.PUBLISHED
    assert role.is_emerging is True
    assert role.signal_strength == 0.4
    assert fake.last[0] == GET_ROLE

    fake.queue([])
    assert repo.get_role("missing") is None
    fake.queue([{"role": None}])
    assert repo.get_role("ghost") is None


def test_role_from_props_accepts_native_datetime() -> None:
    class _NeoDateTime:
        def to_native(self) -> datetime:
            return datetime(2026, 2, 1, tzinfo=UTC)

    role = role_from_props(
        {
            "id": "r2",
            "updated_at": _NeoDateTime(),
            "created_at": datetime(2026, 1, 1, tzinfo=UTC),
        }
    )
    assert role.updated_at == datetime(2026, 2, 1, tzinfo=UTC)
    assert role.created_at == datetime(2026, 1, 1, tzinfo=UTC)
    assert role.state is PublishState.UNVERIFIED
    assert role.evidence_ids == []


def test_role_skills_filters_ontology_version() -> None:
    fake = FakeExecutor(
        [
            [
                {
                    "role_id": "r1",
                    "skill_id": "s1",
                    "period": "2026Q1",
                    "weight": 0.5,
                    "posting_count": 3,
                    "total_postings": 10,
                    "ontology_version": "v0",
                }
            ]
        ]
    )
    repo = Neo4jGraphRepository(fake, "v0")
    rows = repo.role_skills("r1", "2026Q1")
    assert len(rows) == 1
    assert rows[0].skill_id == "s1"
    cypher, params, write = fake.last
    assert cypher == ROLE_SKILLS
    assert write is False
    assert params["ontology_version"] == "v0"
    assert params["period"] == "2026Q1"

    with pytest.raises(ValueError):
        repo.role_skills("r1", "bad")


def test_snapshot_at_groups_roles_and_requirements() -> None:
    fake = FakeExecutor(
        [
            [
                {
                    "role": {"id": "r1", "name": "后端", "state": "published"},
                    "skill": {"id": "s1", "name": "Python", "ontology_version": "v0"},
                    "weight": 0.9,
                    "posting_count": 8,
                    "total_postings": 10,
                }
            ]
        ]
    )
    repo = Neo4jGraphRepository(fake, "v0")
    snap = repo.snapshot_at("2026Q1")
    assert snap["period"] == "2026Q1"
    assert snap["ontology_version"] == "v0"
    assert snap["roles"][0]["id"] == "r1"
    assert snap["skills"][0]["name"] == "Python"
    assert snap["requirements"][0]["weight"] == 0.9
    assert fake.last[0] == SNAPSHOT_AT
    assert fake.last[1]["ontology_version"] == "v0"


def test_compute_competency_diff_three_kinds() -> None:
    rows_a = [
        {
            "role_id": "r1",
            "skill_id": "py",
            "weight": 0.9,
            "competency_id": "c1",
            "statement": "后端语言",
        },
        {
            "role_id": "r1",
            "skill_id": "dj",
            "weight": 0.4,
            "competency_id": "c1",
            "statement": "后端语言",
        },
        {
            "role_id": "r1",
            "skill_id": "redis",
            "weight": 0.3,
            "competency_id": "c2",
            "statement": "缓存",
        },
    ]
    rows_b = [
        {
            "role_id": "r1",
            "skill_id": "py",
            "weight": 0.9,
            "competency_id": "c1",
            "statement": "后端语言",
        },
        {
            "role_id": "r1",
            "skill_id": "dj",
            "weight": 0.8,
            "competency_id": "c1",
            "statement": "后端语言",
        },
        {
            "role_id": "r1",
            "skill_id": "k8s",
            "weight": 0.6,
            "competency_id": "c3",
            "statement": "容器编排",
        },
    ]
    stamp = datetime(2026, 7, 1, tzinfo=UTC)
    changes = compute_competency_diff(rows_a, rows_b, "2026Q1", "2026Q2", recorded_at=stamp)
    kinds = {c.competency_id: c.kind for c in changes}
    assert kinds["c1"] is ChangeKind.MODIFIED
    assert kinds["c2"] is ChangeKind.REMOVED
    assert kinds["c3"] is ChangeKind.ADDED
    added = next(c for c in changes if c.kind is ChangeKind.ADDED)
    assert added.before is None
    assert added.after is not None
    removed = next(c for c in changes if c.kind is ChangeKind.REMOVED)
    assert removed.after is None
    modified = next(c for c in changes if c.kind is ChangeKind.MODIFIED)
    assert "0.4" in (modified.before or "")
    assert "0.8" in (modified.after or "")
    assert all(c.occurred_on == date(2026, 6, 30) for c in changes)


def test_compute_competency_diff_skips_identical_and_uses_skill_fallback() -> None:
    rows = [
        {"role_id": "r1", "skill_id": "py", "weight": 0.5, "competency_id": None, "statement": None}
    ]
    assert compute_competency_diff(rows, rows, "2026Q1", "2026Q2") == []
    later = [
        {"role_id": "r1", "skill_id": "go", "weight": 0.7, "competency_id": None, "statement": None}
    ]
    changes = compute_competency_diff(rows, later, "2026Q1", "2026Q2")
    assert {c.kind for c in changes} == {ChangeKind.ADDED, ChangeKind.REMOVED}
    assert {c.competency_id for c in changes} == {"skill:py", "skill:go"}


def test_diff_runs_two_period_queries() -> None:
    fake = FakeExecutor(
        [
            [
                {
                    "role_id": "r1",
                    "skill_id": "py",
                    "weight": 0.2,
                    "competency_id": "c1",
                    "statement": "x",
                }
            ],
            [
                {
                    "role_id": "r1",
                    "skill_id": "py",
                    "weight": 0.9,
                    "competency_id": "c1",
                    "statement": "x",
                }
            ],
        ]
    )
    repo = Neo4jGraphRepository(fake, "v0")
    changes = repo.diff("2026Q1", "2026Q2")
    assert len(changes) == 1
    assert changes[0].kind is ChangeKind.MODIFIED
    assert fake.calls[0][0] == DIFF_PERIOD
    assert fake.calls[1][0] == DIFF_PERIOD
    assert fake.calls[0][1] == {"period": "2026Q1", "ontology_version": "v0"}
    assert fake.calls[1][1] == {"period": "2026Q2", "ontology_version": "v0"}
