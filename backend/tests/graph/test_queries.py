from __future__ import annotations

import pytest

from app.graph.queries import (
    COMPARE_ROLES,
    COOCCUR_ONE_HOP,
    COOCCUR_TWO_HOP,
    GET_SKILL,
    LATEST_PERIOD_FOR_ROLE,
    MAX_GRAPH_NODES,
    PANORAMA,
    ROLE_COMPETENCY_PANORAMA,
    ROLE_SKILLS_FALLBACK,
    GraphQueryService,
    cap_graph,
    cytoscape_graph,
)
from tests.graph.fakes import FakeExecutor


def test_cytoscape_and_cap() -> None:
    graph = cytoscape_graph(
        [{"id": "a", "label": "A"}],
        [{"id": "e", "source": "a", "target": "a"}],
    )
    assert graph["nodes"][0]["data"]["id"] == "a"
    nodes = [{"id": f"n{i}"} for i in range(5)]
    edges = [{"id": "e", "source": "n0", "target": "n9"}]
    kept_nodes, kept_edges = cap_graph(nodes, edges, 2)
    assert len(kept_nodes) == 2
    assert kept_edges == []


def test_panorama_cytoscape_and_filters() -> None:
    fake = FakeExecutor(
        [
            [
                {
                    "role_id": "r1",
                    "role_name": "后端工程师",
                    "role_state": "published",
                    "family_id": "backend",
                    "is_emerging": False,
                    "skill_id": "s1",
                    "skill_name": "Python",
                    "weight": 0.85,
                    "posting_count": 10,
                }
            ]
        ]
    )
    svc = GraphQueryService(fake, "v0")
    graph = svc.panorama(
        "2026Q1", family_id="backend", importance_tier="high", published_only=True, limit=100
    )
    assert graph["nodes"][0]["data"]["type"] in {"role", "skill"}
    ids = {n["data"]["id"] for n in graph["nodes"]}
    assert ids == {"role:r1", "skill:s1"}
    assert graph["edges"][0]["data"]["type"] == "requires"
    assert graph["edges"][0]["data"]["weight"] == 0.85
    cypher, params, write = fake.last
    assert cypher == PANORAMA
    assert write is False
    assert params["min_weight"] == 0.7
    assert params["family_id"] == "backend"
    assert params["rel_limit"] == 100
    assert params["ontology_version"] == "v0"


def test_panorama_rejects_bad_tier_and_period() -> None:
    svc = GraphQueryService(FakeExecutor(), "v0")
    with pytest.raises(ValueError, match="重要度层级"):
        svc.panorama("2026Q1", importance_tier="extreme")
    with pytest.raises(ValueError, match="YYYYQn"):
        svc.panorama("2026q1")


def test_role_panorama_two_level() -> None:
    fake = FakeExecutor(
        [
            [
                {
                    "role": {
                        "id": "r1",
                        "name": "后端工程师",
                        "state": "published",
                        "family_id": "backend",
                        "is_emerging": False,
                    },
                    "competency": {
                        "id": "c1",
                        "statement": "能独立交付后端服务",
                        "necessity": "required",
                        "importance": 0.9,
                        "grade": "multi_source",
                        "state": "published",
                    },
                    "skill": {"id": "s1", "name": "Python"},
                    "weight": 0.8,
                    "req_period": "2026Q1",
                }
            ]
        ]
    )
    svc = GraphQueryService(fake, "v0")
    payload = svc.role_panorama("r1", "2026Q1")
    assert payload is not None
    assert payload["role"]["id"] == "r1"
    assert payload["competencies"][0]["grade"] == "multi_source"
    assert payload["competencies"][0]["skills"][0]["name"] == "Python"
    assert fake.last[0] == ROLE_COMPETENCY_PANORAMA
    assert fake.last[1]["ontology_version"] == "v0"


def test_role_panorama_fallback_and_latest_period() -> None:
    fake = FakeExecutor(
        [
            [{"period": "2026Q2"}],
            [
                {
                    "role": {"id": "r1", "name": "后端"},
                    "competency": None,
                    "skill": None,
                    "weight": None,
                    "req_period": None,
                }
            ],
            [
                {
                    "role": {"id": "r1", "name": "后端"},
                    "skill": {"id": "s1", "name": "Go"},
                    "weight": 0.4,
                    "req_period": "2026Q2",
                }
            ],
        ]
    )
    svc = GraphQueryService(fake, "v0")
    payload = svc.role_panorama("r1")
    assert payload is not None
    assert payload["period"] == "2026Q2"
    assert payload["competencies"][0]["id"] == "uncovered"
    assert fake.calls[0][0] == LATEST_PERIOD_FOR_ROLE
    assert fake.calls[2][0] == ROLE_SKILLS_FALLBACK


def test_role_panorama_missing() -> None:
    svc = GraphQueryService(FakeExecutor([[]]), "v0")
    assert svc.role_panorama("nope", "2026Q1") is None


def test_skill_cooccurrence_one_and_two_hop() -> None:
    skill_row = {
        "skill": {"id": "s1", "name": "Python", "ontology_version": "v0"},
        "parent_id": None,
        "parent_name": None,
        "cluster_id": "k1",
        "cluster_name": "backend",
    }
    fake = FakeExecutor(
        [
            [skill_row],
            [
                {
                    "src_id": "s1",
                    "src_name": "Python",
                    "neighbor_id": "s2",
                    "neighbor_name": "Django",
                    "shared_roles": 4,
                    "weight": 0.6,
                }
            ],
        ]
    )
    svc = GraphQueryService(fake, "v0")
    one = svc.skill_cooccurrence("s1", hops=1, period="2026Q1")
    assert one["skill"]["name"] == "Python"
    assert one["graph"]["edges"][0]["data"]["type"] == "co_occurs"
    assert fake.calls[0][0] == GET_SKILL
    assert fake.calls[1][0] == COOCCUR_ONE_HOP

    fake2 = FakeExecutor(
        [
            [skill_row],
            [
                {
                    "src_id": "s1",
                    "src_name": "Python",
                    "mid_id": "s2",
                    "mid_name": "Django",
                    "hop1": 3,
                    "far_id": "s3",
                    "far_name": "Celery",
                    "hop2": 2,
                }
            ],
        ]
    )
    two = GraphQueryService(fake2, "v0").skill_cooccurrence("s1", hops=2, period="2026Q1")
    types = {n["data"]["skill_id"] for n in two["graph"]["nodes"]}
    assert types == {"s1", "s2", "s3"}
    assert fake2.calls[1][0] == COOCCUR_TWO_HOP


def test_skill_cooccurrence_missing_and_no_period() -> None:
    svc = GraphQueryService(FakeExecutor([[], []]), "v0")
    missing = svc.skill_cooccurrence("nope", hops=1, period="2026Q1")
    assert missing["skill"] is None

    fake = FakeExecutor(
        [
            [],
            [
                {
                    "skill": {"id": "s1", "name": "Python"},
                    "parent_id": None,
                    "parent_name": None,
                    "cluster_id": None,
                    "cluster_name": None,
                }
            ],
        ]
    )
    empty = GraphQueryService(fake, "v0").skill_cooccurrence("s1", hops=1)
    assert empty["period"] is None
    assert empty["graph"]["nodes"][0]["data"]["id"] == "skill:s1"

    with pytest.raises(ValueError, match="1 或 2"):
        GraphQueryService(FakeExecutor(), "v0").skill_cooccurrence("s1", hops=3, period="2026Q1")


def test_compare_roles() -> None:
    fake = FakeExecutor(
        [
            [
                {
                    "role_id": "ra",
                    "role_name": "后端",
                    "role_state": "published",
                    "skill_id": "py",
                    "skill_name": "Python",
                    "weight": 0.9,
                    "competency_id": "c1",
                    "statement": "语言",
                    "necessity": "required",
                    "grade": "multi_source",
                },
                {
                    "role_id": "ra",
                    "role_name": "后端",
                    "role_state": "published",
                    "skill_id": "dj",
                    "skill_name": "Django",
                    "weight": 0.5,
                    "competency_id": "c1",
                    "statement": "语言",
                    "necessity": "required",
                    "grade": "multi_source",
                },
                {
                    "role_id": "rb",
                    "role_name": "数据",
                    "role_state": "published",
                    "skill_id": "py",
                    "skill_name": "Python",
                    "weight": 0.7,
                    "competency_id": "c2",
                    "statement": "语言",
                    "necessity": "required",
                    "grade": "single_source",
                },
                {
                    "role_id": "rb",
                    "role_name": "数据",
                    "role_state": "published",
                    "skill_id": "sql",
                    "skill_name": "SQL",
                    "weight": 0.8,
                    "competency_id": "c3",
                    "statement": "数据",
                    "necessity": "required",
                    "grade": "weak",
                },
            ]
        ]
    )
    result = GraphQueryService(fake, "v0").compare_roles("ra", "rb", "2026Q1")
    assert result["only_a"][0]["skill_id"] == "dj"
    assert result["only_b"][0]["skill_id"] == "sql"
    assert result["both"][0]["skill_id"] == "py"
    assert result["both"][0]["delta"] == pytest.approx(-0.2)
    assert fake.last[0] == COMPARE_ROLES
    assert fake.last[1]["role_ids"] == ["ra", "rb"]


def test_node_cap_constant() -> None:
    assert MAX_GRAPH_NODES == 2000
