"""共现图 Louvain 技能簇。"""

from __future__ import annotations

from app.evolution.cluster import (
    Cooccurrence,
    build_cooccurrence_graph,
    cluster_skills,
    induced_density,
)


def _clique(skills: list[str], source: str, period: str, weight: float = 3.0) -> list[Cooccurrence]:
    edges: list[Cooccurrence] = []
    for i, a in enumerate(skills):
        for b in skills[i + 1 :]:
            edges.append(Cooccurrence(source, period, a, b, weight))
    return edges


def test_louvain_splits_two_cliques() -> None:
    a = ["java", "spring", "mysql", "redis"]
    b = ["llm", "rag", "agent", "eval"]
    edges = _clique(a, "boss", "2024Q1") + _clique(b, "boss", "2024Q1")
    # 很弱的桥，不应把两簇并起来
    edges.append(Cooccurrence("boss", "2024Q1", "java", "llm", 0.1))
    clusters = cluster_skills(edges, ontology_version="v0")
    assert len(clusters) >= 2
    member_sets = [set(c.skill_ids) for c in clusters]
    assert any(set(a).issubset(s) or set(a) == s for s in member_sets)
    assert any(set(b).issubset(s) or set(b) == s for s in member_sets)


def test_empty_graph() -> None:
    assert cluster_skills([], "v0") == []


def test_tuple_edges_and_skipped_loops() -> None:
    clusters = cluster_skills(
        [("a", "b", 2.0), ("b", "c", 2.0), ("a", "a", 9.0), ("c", "d", 0.0)],
        "v0",
    )
    assert clusters
    ids = {s for c in clusters for s in c.skill_ids}
    assert "a" in ids and "b" in ids


def test_induced_density_zero_without_edges() -> None:
    g = build_cooccurrence_graph([], skill_ids=["a", "b", "c"])
    assert induced_density(g, {"a", "b", "c"}) == 0.0
