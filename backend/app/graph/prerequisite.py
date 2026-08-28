"""前置依赖关系推断。

在 (:Skill)-[:PREREQUISITE_OF {rule, confidence, source, active, locked}]->(:Skill)
上维护边。active/locked 是显式状态，不用 NULL 表示「当前有效」。

推断规则（启发式，可被人工覆写）：
1. hierarchy：父技能点是子技能点的前置（先掌握更基础的父节点）。
2. cooccurrence_asymmetry：同一时间片内，若 P(B|A)≥0.8 且 P(A|B)≤0.5
   且共同出现的岗位数≥3，则 B 是 A 的前置（A 出现时 B 几乎总在，反之不然）。
3. seniority_distribution：名称像初级岗位的出现占比明显高于对方、
   且对方在高级岗位上更常见的技能点，视为前置。

人工覆写把 locked=true：推断不再改这条边；active=false 表示明确否定该前置。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import networkx as nx

from app.graph.periods import parse_period
from app.graph.session import CypherExecutor

HIERARCHY_QUERY = """
MATCH (p:Skill)-[:PARENT_OF]->(c:Skill)
WHERE ($ontology_version IS NULL OR p.ontology_version = $ontology_version)
  AND ($ontology_version IS NULL OR c.ontology_version = $ontology_version)
RETURN p.id AS src, c.id AS dst
"""

SKILL_ROLE_COUNTS = """
MATCH (r:Role)-[req:REQUIRES]->(s:Skill)
WHERE req.period = $period AND req.ontology_version = $ontology_version
RETURN s.id AS skill_id, count(DISTINCT r) AS role_count
"""

PAIR_COUNTS = """
MATCH (r:Role)-[a:REQUIRES]->(sa:Skill)
MATCH (r)-[b:REQUIRES]->(sb:Skill)
WHERE a.period = $period AND b.period = $period
  AND a.ontology_version = $ontology_version
  AND b.ontology_version = $ontology_version
  AND sa.id < sb.id
RETURN sa.id AS skill_a, sb.id AS skill_b, count(DISTINCT r) AS both_count
"""

SENIORITY_ROWS = """
MATCH (r:Role)-[req:REQUIRES]->(s:Skill)
WHERE req.period = $period AND req.ontology_version = $ontology_version
RETURN s.id AS skill_id, r.id AS role_id, r.name AS role_name
"""

UPSERT_PREREQ = """
MATCH (a:Skill {id: $src})
MATCH (b:Skill {id: $dst})
MERGE (a)-[p:PREREQUISITE_OF]->(b)
FOREACH (_ IN CASE WHEN coalesce(p.locked, false) = false THEN [1] ELSE [] END |
    SET p.rule = $rule,
        p.confidence = $confidence,
        p.source = 'inferred',
        p.active = true,
        p.locked = false
)
RETURN a.id AS src, b.id AS dst, p.locked AS locked, p.active AS active
"""

OVERRIDE_PREREQ = """
MATCH (a:Skill {id: $src})
MATCH (b:Skill {id: $dst})
MERGE (a)-[p:PREREQUISITE_OF]->(b)
SET p.active = $active,
    p.locked = true,
    p.source = 'manual',
    p.rule = 'manual',
    p.confidence = 1.0
RETURN a.id AS src, b.id AS dst, p.active AS active, p.locked AS locked
"""

LIST_PREREQS = """
MATCH (a:Skill {id: $skill_id})-[p:PREREQUISITE_OF]->(b:Skill)
WHERE coalesce(p.active, true) = true
RETURN a.id AS src, b.id AS dst, p.rule AS rule, p.confidence AS confidence
"""

ASYMMETRY_HIGH = 0.8
ASYMMETRY_LOW = 0.5
MIN_COOCCUR_ROLES = 3
JUNIOR_MARKERS = ("初级", "实习", "助理", "junior", "intern", "assistant")
SENIOR_MARKERS = ("高级", "资深", "专家", "架构", "senior", "staff", "principal", "architect")


@dataclass(frozen=True)
class PrerequisiteCandidate:
    src: str
    dst: str
    rule: str
    confidence: float


def _role_band(name: str | None) -> str | None:
    text = (name or "").lower()
    junior = any(m.lower() in text for m in JUNIOR_MARKERS)
    senior = any(m.lower() in text for m in SENIOR_MARKERS)
    if junior and not senior:
        return "junior"
    if senior and not junior:
        return "senior"
    return None


def infer_from_hierarchy(pairs: list[tuple[str, str]]) -> list[PrerequisiteCandidate]:
    return [
        PrerequisiteCandidate(src=src, dst=dst, rule="hierarchy", confidence=0.9)
        for src, dst in pairs
        if src != dst
    ]


def infer_from_asymmetry(
    role_counts: dict[str, int],
    pair_counts: dict[tuple[str, str], int],
    *,
    high: float = ASYMMETRY_HIGH,
    low: float = ASYMMETRY_LOW,
    min_roles: int = MIN_COOCCUR_ROLES,
) -> list[PrerequisiteCandidate]:
    """P(B|A) 高且 P(A|B) 低 → B 是 A 的前置。"""
    out: list[PrerequisiteCandidate] = []
    for (skill_a, skill_b), both in pair_counts.items():
        if both < min_roles:
            continue
        count_a = role_counts.get(skill_a, 0)
        count_b = role_counts.get(skill_b, 0)
        if count_a <= 0 or count_b <= 0:
            continue
        p_b_given_a = both / count_a
        p_a_given_b = both / count_b
        if p_b_given_a >= high and p_a_given_b <= low:
            confidence = min(1.0, (p_b_given_a - p_a_given_b))
            out.append(
                PrerequisiteCandidate(
                    src=skill_b, dst=skill_a, rule="cooccurrence_asymmetry", confidence=confidence
                )
            )
        elif p_a_given_b >= high and p_b_given_a <= low:
            confidence = min(1.0, (p_a_given_b - p_b_given_a))
            out.append(
                PrerequisiteCandidate(
                    src=skill_a, dst=skill_b, rule="cooccurrence_asymmetry", confidence=confidence
                )
            )
    return out


def infer_from_seniority(
    rows: list[dict[str, Any]],
) -> list[PrerequisiteCandidate]:
    """初级岗位更常见、高级岗位更少见的技能点，作为对方的前置。"""
    stats: dict[str, dict[str, int]] = {}
    for row in rows:
        skill_id = row["skill_id"]
        band = _role_band(row.get("role_name"))
        bucket = stats.setdefault(skill_id, {"junior": 0, "senior": 0, "other": 0})
        if band == "junior":
            bucket["junior"] += 1
        elif band == "senior":
            bucket["senior"] += 1
        else:
            bucket["other"] += 1

    skills = list(stats)
    out: list[PrerequisiteCandidate] = []
    for i, skill_a in enumerate(skills):
        for skill_b in skills[i + 1 :]:
            a, b = stats[skill_a], stats[skill_b]
            a_total = a["junior"] + a["senior"]
            b_total = b["junior"] + b["senior"]
            if a_total < 2 or b_total < 2:
                continue
            a_junior_ratio = a["junior"] / a_total
            b_junior_ratio = b["junior"] / b_total
            a_senior_ratio = a["senior"] / a_total
            b_senior_ratio = b["senior"] / b_total
            if (
                a_junior_ratio >= 0.6
                and b_senior_ratio >= 0.6
                and a_junior_ratio - b_junior_ratio >= 0.3
            ):
                out.append(
                    PrerequisiteCandidate(
                        src=skill_a,
                        dst=skill_b,
                        rule="seniority_distribution",
                        confidence=min(0.8, a_junior_ratio - b_junior_ratio),
                    )
                )
            elif (
                b_junior_ratio >= 0.6
                and a_senior_ratio >= 0.6
                and b_junior_ratio - a_junior_ratio >= 0.3
            ):
                out.append(
                    PrerequisiteCandidate(
                        src=skill_b,
                        dst=skill_a,
                        rule="seniority_distribution",
                        confidence=min(0.8, b_junior_ratio - a_junior_ratio),
                    )
                )
    return out


RULE_PRIORITY = {
    "hierarchy": 0,
    "cooccurrence_asymmetry": 1,
    "seniority_distribution": 2,
}


def select_acyclic(
    candidates: list[PrerequisiteCandidate],
) -> list[PrerequisiteCandidate]:
    """按规则优先级写入，出现环则丢弃该候选。"""
    ordered = sorted(
        candidates,
        key=lambda c: (RULE_PRIORITY.get(c.rule, 9), -c.confidence, c.src, c.dst),
    )
    graph: nx.DiGraph = nx.DiGraph()
    accepted: list[PrerequisiteCandidate] = []
    seen: set[tuple[str, str]] = set()
    for cand in ordered:
        if cand.src == cand.dst:
            continue
        key = (cand.src, cand.dst)
        if key in seen or (cand.dst, cand.src) in seen:
            continue
        graph.add_edge(cand.src, cand.dst)
        if nx.is_directed_acyclic_graph(graph):
            seen.add(key)
            accepted.append(cand)
        else:
            graph.remove_edge(cand.src, cand.dst)
            if graph.out_degree(cand.src) == 0 and graph.in_degree(cand.src) == 0:
                graph.remove_node(cand.src)
            if graph.out_degree(cand.dst) == 0 and graph.in_degree(cand.dst) == 0:
                graph.remove_node(cand.dst)
    return accepted


class PrerequisiteInferrer:
    def __init__(self, executor: CypherExecutor, ontology_version: str) -> None:
        self._ex = executor
        self._ontology_version = ontology_version

    def infer(self, period: str) -> list[PrerequisiteCandidate]:
        parse_period(period)
        ov = self._ontology_version
        hierarchy_rows = self._ex.run(HIERARCHY_QUERY, {"ontology_version": ov})
        count_rows = self._ex.run(SKILL_ROLE_COUNTS, {"period": period, "ontology_version": ov})
        pair_rows = self._ex.run(PAIR_COUNTS, {"period": period, "ontology_version": ov})
        seniority_rows = self._ex.run(SENIORITY_ROWS, {"period": period, "ontology_version": ov})

        role_counts = {row["skill_id"]: int(row["role_count"]) for row in count_rows}
        pair_counts = {
            (row["skill_a"], row["skill_b"]): int(row["both_count"]) for row in pair_rows
        }
        candidates = [
            *infer_from_hierarchy([(row["src"], row["dst"]) for row in hierarchy_rows]),
            *infer_from_asymmetry(role_counts, pair_counts),
            *infer_from_seniority(seniority_rows),
        ]
        accepted = select_acyclic(candidates)
        for cand in accepted:
            self._ex.run(
                UPSERT_PREREQ,
                {
                    "src": cand.src,
                    "dst": cand.dst,
                    "rule": cand.rule,
                    "confidence": cand.confidence,
                },
                write=True,
            )
        return accepted

    def override(self, src_skill_id: str, dst_skill_id: str, *, active: bool) -> None:
        self._ex.run(
            OVERRIDE_PREREQ,
            {"src": src_skill_id, "dst": dst_skill_id, "active": active},
            write=True,
        )

    def prerequisites_of(self, skill_id: str) -> list[dict[str, Any]]:
        return self._ex.run(LIST_PREREQS, {"skill_id": skill_id})
