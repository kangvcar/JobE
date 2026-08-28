"""学习路径排序。先满足 PREREQUISITE_OF 约束，再在可学前集里按紧迫度排。

依赖图成环时：对强连通分量做缩点，SCC 之间仍拓扑排；SCC 内部按紧迫度降级，
并在 reason 中标明。不得死循环。
"""

from __future__ import annotations

import networkx as nx

from app.domain.models import Gap, GapKind, LearningPath, LearningStep
from app.matching.protocols import PrerequisiteSource


def _closure(
    seeds: list[str],
    source: PrerequisiteSource,
    satisfied: set[str],
) -> tuple[set[str], dict[str, list[str]]]:
    """把未掌握的前置技能点纳入 to_learn，并取回完整前置表。"""
    to_learn = set(seeds)
    prereq_map: dict[str, list[str]] = {}
    frontier = list(seeds)
    seen: set[str] = set()
    while frontier:
        batch = [s for s in frontier if s not in seen]
        frontier = []
        if not batch:
            continue
        seen.update(batch)
        fetched = source.prerequisites_of(batch)
        for skill_id in batch:
            pres = list(dict.fromkeys(fetched.get(skill_id, [])))
            prereq_map[skill_id] = pres
            for pre in pres:
                if pre in satisfied:
                    continue
                if pre not in to_learn:
                    to_learn.add(pre)
                    frontier.append(pre)
    return to_learn, prereq_map


def _inherit_urgency(
    to_learn: set[str],
    prereq_map: dict[str, list[str]],
    urgency: dict[str, float],
) -> dict[str, float]:
    """未单独计过紧迫度的前置，继承其后续技能点的紧迫度，以便与其它可学节点比较。"""
    values = {s: urgency.get(s, 0.0) for s in to_learn}
    changed = True
    while changed:
        changed = False
        for skill_id, pres in prereq_map.items():
            child = values.get(skill_id, 0.0)
            for pre in pres:
                if pre not in values:
                    continue
                if values[pre] < child:
                    values[pre] = child
                    changed = True
    return values


def _weighted_order(
    to_learn: set[str],
    prereq_map: dict[str, list[str]],
    urgency: dict[str, float],
) -> list[tuple[str, bool]]:
    """带权拓扑排序。(skill_id, in_cycle)。

    缩点后的 SCC 图是 DAG，用 lexicographical_topological_sort 在可学前
    按 (-urgency, id) 取下一项。成环的 SCC 内部按紧迫度降级，跨 SCC 的
    依赖边仍遵守，避免把环外后继提前弹出。
    """
    graph = nx.DiGraph()
    graph.add_nodes_from(to_learn)
    for skill_id, pres in prereq_map.items():
        if skill_id not in to_learn:
            continue
        for pre in pres:
            if pre != skill_id and pre in to_learn:
                graph.add_edge(pre, skill_id)

    if graph.number_of_nodes() == 0:
        return []

    condensed = nx.condensation(graph)
    members = {i: set(condensed.nodes[i]["members"]) for i in condensed.nodes}

    def scc_key(scc_id: int) -> tuple[float, str]:
        scc = members[scc_id]
        return (-max(urgency.get(n, 0.0) for n in scc), min(scc))

    result: list[tuple[str, bool]] = []
    for scc_id in nx.lexicographical_topological_sort(condensed, key=scc_key):
        scc = members[scc_id]
        subgraph = graph.subgraph(scc)
        cyclic = not nx.is_directed_acyclic_graph(subgraph)
        if cyclic:
            inner = sorted(scc, key=lambda n: (-urgency.get(n, 0.0), n))
        else:
            inner = list(
                nx.lexicographical_topological_sort(
                    subgraph, key=lambda n: (-urgency.get(n, 0.0), n)
                )
            )
        result.extend((node, cyclic) for node in inner)
    return result


def _reason(
    *,
    cyclic: bool,
    implicit: bool,
    blocking: list[str],
    urgency: float,
) -> str:
    parts: list[str] = []
    if cyclic:
        parts.append("依赖图存在环，已按紧迫度降级插入，不再等待循环依赖")
    if implicit:
        parts.append("作为后续技能点的前置被纳入路径")
    if blocking:
        parts.append(f"前置 {', '.join(blocking)} 已排在更前")
    elif not cyclic:
        parts.append("当前可学（前置已掌握或不存在）")
    parts.append(f"紧迫度为 {urgency:.2f}")
    return "；".join(parts)


def plan_learning_path(
    *,
    profile_id: str,
    role_id: str,
    gaps: list[Gap],
    prereq_source: PrerequisiteSource,
    satisfied: set[str],
) -> LearningPath:
    """只把缺失与不足排进路径。冗余不学。"""
    seeds = [g.skill_id for g in gaps if g.kind != GapKind.SURPLUS]
    explicit = set(seeds)
    urgency = {g.skill_id: g.urgency for g in gaps if g.kind != GapKind.SURPLUS}
    to_learn, prereq_map = _closure(seeds, prereq_source, satisfied)
    urgency = _inherit_urgency(to_learn, prereq_map, urgency)
    ordered = _weighted_order(to_learn, prereq_map, urgency)

    index = {skill_id: i for i, (skill_id, _) in enumerate(ordered)}
    steps: list[LearningStep] = []
    for order, (skill_id, cyclic) in enumerate(ordered, start=1):
        pres = [p for p in prereq_map.get(skill_id, []) if p != skill_id]
        blocking = [p for p in pres if p in index and index[p] < index[skill_id]]
        steps.append(
            LearningStep(
                skill_id=skill_id,
                order=order,
                prerequisites=pres,
                reason=_reason(
                    cyclic=cyclic,
                    implicit=skill_id not in explicit,
                    blocking=blocking,
                    urgency=urgency.get(skill_id, 0.0),
                ),
            )
        )
    return LearningPath(profile_id=profile_id, role_id=role_id, steps=steps)
