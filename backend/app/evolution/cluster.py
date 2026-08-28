"""技能共现图上的 Louvain 社区发现。

技能点已是结构化短标签（千级），且有明确共现边，不必上 BERTopic / HDBSCAN。
不用 leidenalg：GPL，且千级图上看不出 Leiden 对连通性的改进。
"""

from __future__ import annotations

from dataclasses import dataclass

import networkx as nx

from app.domain.models import SkillCluster

MIN_EDGE_WEIGHT = 0.0


@dataclass(frozen=True)
class Cooccurrence:
    source_id: str
    period: str
    skill_a: str
    skill_b: str
    weight: float = 1.0


def cluster_skills(
    edges: list[Cooccurrence] | list[tuple[str, str, float]],
    ontology_version: str,
    skill_ids: list[str] | None = None,
    *,
    resolution: float = 1.0,
    seed: int = 42,
) -> list[SkillCluster]:
    graph = build_cooccurrence_graph(edges, skill_ids)
    if graph.number_of_nodes() == 0:
        return []
    communities = nx.community.louvain_communities(
        graph, weight="weight", resolution=resolution, seed=seed
    )
    clusters: list[SkillCluster] = []
    for i, members in enumerate(sorted(communities, key=lambda c: (-len(c), sorted(c)))):
        ids = sorted(members)
        clusters.append(
            SkillCluster(
                id=f"cluster-{i}",
                name="-".join(ids[:3]),
                skill_ids=ids,
                ontology_version=ontology_version,
            )
        )
    return clusters


def build_cooccurrence_graph(
    edges: list[Cooccurrence] | list[tuple[str, str, float]],
    skill_ids: list[str] | None = None,
) -> nx.Graph:
    graph = nx.Graph()
    if skill_ids:
        graph.add_nodes_from(skill_ids)
    for edge in edges:
        if isinstance(edge, Cooccurrence):
            a, b, w = edge.skill_a, edge.skill_b, edge.weight
        else:
            a, b, w = edge
        if a == b or w <= MIN_EDGE_WEIGHT:
            continue
        if graph.has_edge(a, b):
            graph[a][b]["weight"] += w
        else:
            graph.add_edge(a, b, weight=w)
    return graph


def induced_density(graph: nx.Graph, skill_ids: set[str]) -> float:
    """簇内平均边权。无边时为 0，用作「新形成 / 密度突增」的分子分母。"""
    nodes = [n for n in skill_ids if n in graph]
    n = len(nodes)
    if n < 2:
        return 0.0
    weight = 0.0
    for i, a in enumerate(nodes):
        for b in nodes[i + 1 :]:
            data = graph.get_edge_data(a, b)
            if data:
                weight += float(data.get("weight", 1.0))
    possible = n * (n - 1) / 2
    return weight / possible
