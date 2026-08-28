"""面向前端的图谱查询。只返回 id、名称、状态、权重等图属性，不含原始文本。"""

from __future__ import annotations

from typing import Any

from app.graph.periods import parse_period
from app.graph.session import CypherExecutor

MAX_GRAPH_NODES = 2000

TIER_WEIGHT_RANGE = {
    "high": (0.7, 1.01),
    "medium": (0.3, 0.7),
    "low": (0.0, 0.3),
}

PANORAMA = """
MATCH (r:Role)-[req:REQUIRES]->(s:Skill)
WHERE req.period = $period
  AND req.ontology_version = $ontology_version
  AND req.weight >= $min_weight
  AND req.weight < $max_weight
  AND ($family_id IS NULL OR r.family_id = $family_id)
  AND ($published_only = false OR r.state = $published_state)
RETURN r.id AS role_id,
       r.name AS role_name,
       r.state AS role_state,
       r.family_id AS family_id,
       r.is_emerging AS is_emerging,
       s.id AS skill_id,
       s.name AS skill_name,
       req.weight AS weight,
       req.posting_count AS posting_count
ORDER BY req.weight DESC
LIMIT $rel_limit
"""

GET_SKILL = """
MATCH (s:Skill {id: $id})
OPTIONAL MATCH (parent:Skill)-[:PARENT_OF]->(s)
OPTIONAL MATCH (s)-[:IN_CLUSTER]->(k:SkillCluster)
RETURN s {.*} AS skill,
       parent.id AS parent_id,
       parent.name AS parent_name,
       k.id AS cluster_id,
       k.name AS cluster_name
"""

ROLE_COMPETENCY_PANORAMA = """
MATCH (r:Role {id: $role_id})
OPTIONAL MATCH (r)-[:HAS_COMPETENCY]->(c:Competency)
OPTIONAL MATCH (c)-[:COVERS]->(s:Skill)
OPTIONAL MATCH (r)-[req:REQUIRES]->(s)
WHERE req.ontology_version = $ontology_version
  AND ($period IS NULL OR req.period = $period)
RETURN r {.*} AS role,
       c {.*} AS competency,
       s {.*} AS skill,
       req.weight AS weight,
       req.period AS req_period
"""

ROLE_SKILLS_FALLBACK = """
MATCH (r:Role {id: $role_id})-[req:REQUIRES]->(s:Skill)
WHERE req.ontology_version = $ontology_version
  AND ($period IS NULL OR req.period = $period)
RETURN r {.*} AS role,
       s {.*} AS skill,
       req.weight AS weight,
       req.period AS req_period
"""

LATEST_PERIOD_FOR_ROLE = """
MATCH (:Role {id: $role_id})-[req:REQUIRES]->(:Skill)
WHERE req.ontology_version = $ontology_version
RETURN req.period AS period
ORDER BY req.period DESC
LIMIT 1
"""

LATEST_PERIOD_FOR_SKILL = """
MATCH (:Role)-[req:REQUIRES]->(:Skill {id: $skill_id})
WHERE req.ontology_version = $ontology_version
RETURN req.period AS period
ORDER BY req.period DESC
LIMIT 1
"""

COOCCUR_ONE_HOP = """
MATCH (src:Skill {id: $skill_id})
MATCH (r:Role)-[req_src:REQUIRES]->(src)
WHERE req_src.period = $period AND req_src.ontology_version = $ontology_version
MATCH (r)-[req_n:REQUIRES]->(n:Skill)
WHERE n.id <> src.id
  AND req_n.period = $period
  AND req_n.ontology_version = $ontology_version
WITH src, n, count(DISTINCT r) AS shared_roles, max(req_n.weight) AS weight
RETURN src.id AS src_id,
       src.name AS src_name,
       n.id AS neighbor_id,
       n.name AS neighbor_name,
       shared_roles,
       weight
ORDER BY shared_roles DESC, neighbor_id
LIMIT $limit
"""

COOCCUR_TWO_HOP = """
MATCH (src:Skill {id: $skill_id})
MATCH (r1:Role)-[a:REQUIRES]->(src)
WHERE a.period = $period AND a.ontology_version = $ontology_version
MATCH (r1)-[b:REQUIRES]->(mid:Skill)
WHERE mid.id <> src.id
  AND b.period = $period
  AND b.ontology_version = $ontology_version
WITH src, mid, count(DISTINCT r1) AS hop1
MATCH (r2:Role)-[c:REQUIRES]->(mid)
WHERE c.period = $period AND c.ontology_version = $ontology_version
MATCH (r2)-[d:REQUIRES]->(far:Skill)
WHERE far.id <> src.id AND far.id <> mid.id
  AND d.period = $period
  AND d.ontology_version = $ontology_version
WITH src, mid, hop1, far, count(DISTINCT r2) AS hop2
RETURN src.id AS src_id,
       src.name AS src_name,
       mid.id AS mid_id,
       mid.name AS mid_name,
       hop1,
       far.id AS far_id,
       far.name AS far_name,
       hop2
ORDER BY hop1 DESC, hop2 DESC
LIMIT $limit
"""

COMPARE_ROLES = """
MATCH (r:Role)
WHERE r.id IN $role_ids
OPTIONAL MATCH (r)-[req:REQUIRES]->(s:Skill)
WHERE req.period = $period AND req.ontology_version = $ontology_version
OPTIONAL MATCH (r)-[:HAS_COMPETENCY]->(c:Competency)-[:COVERS]->(s)
RETURN r.id AS role_id,
       r.name AS role_name,
       r.state AS role_state,
       s.id AS skill_id,
       s.name AS skill_name,
       req.weight AS weight,
       c.id AS competency_id,
       c.statement AS statement,
       c.necessity AS necessity,
       c.grade AS grade
"""


def cytoscape_graph(nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> dict[str, Any]:
    """Cytoscape.js 元素结构。"""
    return {
        "nodes": [{"data": node} for node in nodes],
        "edges": [{"data": edge} for edge in edges],
    }


def cap_graph(
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    limit: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    limit = min(max(limit, 1), MAX_GRAPH_NODES)
    if len(nodes) <= limit:
        return nodes, edges
    kept_ids = {node["id"] for node in nodes[:limit]}
    return nodes[:limit], [
        edge for edge in edges if edge["source"] in kept_ids and edge["target"] in kept_ids
    ]


class GraphQueryService:
    def __init__(self, executor: CypherExecutor, ontology_version: str) -> None:
        self._ex = executor
        self._ontology_version = ontology_version

    def _latest_period(self, cypher: str, params: dict[str, Any]) -> str | None:
        rows = self._ex.run(cypher, params)
        if not rows:
            return None
        return rows[0].get("period")

    def panorama(
        self,
        period: str,
        *,
        family_id: str | None = None,
        importance_tier: str | None = None,
        min_weight: float = 0.0,
        limit: int = MAX_GRAPH_NODES,
        published_only: bool = True,
    ) -> dict[str, Any]:
        parse_period(period)
        max_weight = 1.01
        if importance_tier is not None:
            if importance_tier not in TIER_WEIGHT_RANGE:
                raise ValueError(f"重要度层级必须是 high/medium/low，收到：{importance_tier}")
            min_weight, max_weight = TIER_WEIGHT_RANGE[importance_tier]
        rel_limit = min(max(limit, 1), MAX_GRAPH_NODES)
        rows = self._ex.run(
            PANORAMA,
            {
                "period": period,
                "ontology_version": self._ontology_version,
                "min_weight": min_weight,
                "max_weight": max_weight,
                "family_id": family_id,
                "published_only": published_only,
                "published_state": "published",
                "rel_limit": rel_limit,
            },
        )
        nodes: dict[str, dict[str, Any]] = {}
        edges: list[dict[str, Any]] = []
        for row in rows:
            role_cid = f"role:{row['role_id']}"
            skill_cid = f"skill:{row['skill_id']}"
            nodes.setdefault(
                role_cid,
                {
                    "id": role_cid,
                    "label": row.get("role_name") or row["role_id"],
                    "type": "role",
                    "role_id": row["role_id"],
                    "state": row.get("role_state"),
                    "family_id": row.get("family_id"),
                    "is_emerging": bool(row.get("is_emerging") or False),
                },
            )
            nodes.setdefault(
                skill_cid,
                {
                    "id": skill_cid,
                    "label": row.get("skill_name") or row["skill_id"],
                    "type": "skill",
                    "skill_id": row["skill_id"],
                },
            )
            edges.append(
                {
                    "id": f"requires:{row['role_id']}:{row['skill_id']}:{period}",
                    "source": role_cid,
                    "target": skill_cid,
                    "type": "requires",
                    "weight": float(row["weight"]),
                    "posting_count": int(row["posting_count"]),
                }
            )
        capped_nodes, capped_edges = cap_graph(list(nodes.values()), edges, rel_limit)
        graph = cytoscape_graph(capped_nodes, capped_edges)
        graph["period"] = period
        graph["ontology_version"] = self._ontology_version
        graph["family_id"] = family_id
        graph["importance_tier"] = importance_tier
        return graph

    def role_panorama(self, role_id: str, period: str | None = None) -> dict[str, Any] | None:
        if period is not None:
            parse_period(period)
        else:
            period = self._latest_period(
                LATEST_PERIOD_FOR_ROLE,
                {"role_id": role_id, "ontology_version": self._ontology_version},
            )
        rows = self._ex.run(
            ROLE_COMPETENCY_PANORAMA,
            {
                "role_id": role_id,
                "period": period,
                "ontology_version": self._ontology_version,
            },
        )
        if not rows:
            return None
        role_props = rows[0].get("role")
        if not role_props:
            return None

        competencies: dict[str, dict[str, Any]] = {}
        for row in rows:
            comp = row.get("competency")
            if not comp:
                continue
            cid = comp["id"]
            item = competencies.setdefault(
                cid,
                {
                    "id": cid,
                    "statement": comp.get("statement") or "",
                    "necessity": comp.get("necessity"),
                    "importance": float(comp.get("importance") or 0.0),
                    "grade": comp.get("grade"),
                    "state": comp.get("state"),
                    "skills": [],
                },
            )
            skill = row.get("skill")
            if not skill:
                continue
            skill_entry = {
                "id": skill["id"],
                "name": skill.get("name") or "",
                "weight": float(row["weight"]) if row.get("weight") is not None else None,
                "period": row.get("req_period"),
            }
            if skill_entry not in item["skills"]:
                item["skills"].append(skill_entry)

        if not competencies:
            # 尚无能力项时，仍按 REQUIRES 展开技能点，避免详情页空白
            fallback = self._ex.run(
                ROLE_SKILLS_FALLBACK,
                {
                    "role_id": role_id,
                    "period": period,
                    "ontology_version": self._ontology_version,
                },
            )
            uncovered: list[dict[str, Any]] = []
            for row in fallback:
                skill = row.get("skill")
                if not skill:
                    continue
                uncovered.append(
                    {
                        "id": skill["id"],
                        "name": skill.get("name") or "",
                        "weight": float(row["weight"]) if row.get("weight") is not None else None,
                        "period": row.get("req_period"),
                    }
                )
            if uncovered:
                competencies["uncovered"] = {
                    "id": "uncovered",
                    "statement": "",
                    "necessity": None,
                    "importance": 0.0,
                    "grade": None,
                    "state": None,
                    "skills": uncovered,
                }

        return {
            "role": {
                "id": role_props["id"],
                "name": role_props.get("name") or "",
                "state": role_props.get("state"),
                "family_id": role_props.get("family_id"),
                "is_emerging": bool(role_props.get("is_emerging") or False),
                "occupation_code": role_props.get("occupation_code"),
            },
            "period": period,
            "ontology_version": self._ontology_version,
            "competencies": list(competencies.values()),
        }

    def skill_detail(self, skill_id: str) -> dict[str, Any] | None:
        rows = self._ex.run(GET_SKILL, {"id": skill_id})
        if not rows or not rows[0].get("skill"):
            return None
        skill = rows[0]["skill"]
        return {
            "id": skill["id"],
            "name": skill.get("name") or "",
            "ontology_version": skill.get("ontology_version"),
            "parent_id": rows[0].get("parent_id") or skill.get("parent_id"),
            "parent_name": rows[0].get("parent_name"),
            "cluster_id": rows[0].get("cluster_id") or skill.get("cluster_id"),
            "cluster_name": rows[0].get("cluster_name"),
            "state": skill.get("state"),
        }

    def skill_cooccurrence(
        self,
        skill_id: str,
        *,
        hops: int = 1,
        period: str | None = None,
        limit: int = 200,
    ) -> dict[str, Any]:
        if hops not in (1, 2):
            raise ValueError("共现子图只支持 1 或 2 跳")
        if period is not None:
            parse_period(period)
        else:
            period = self._latest_period(
                LATEST_PERIOD_FOR_SKILL,
                {"skill_id": skill_id, "ontology_version": self._ontology_version},
            )
        detail = self.skill_detail(skill_id)
        if detail is None:
            return {
                "skill": None,
                "period": period,
                "hops": hops,
                "graph": cytoscape_graph([], []),
            }
        if period is None:
            return {
                "skill": detail,
                "period": None,
                "hops": hops,
                "graph": cytoscape_graph(
                    [
                        {
                            "id": f"skill:{skill_id}",
                            "label": detail["name"],
                            "type": "skill",
                            "skill_id": skill_id,
                        }
                    ],
                    [],
                ),
            }

        cap = min(max(limit, 1), MAX_GRAPH_NODES)
        nodes: dict[str, dict[str, Any]] = {
            f"skill:{skill_id}": {
                "id": f"skill:{skill_id}",
                "label": detail["name"],
                "type": "skill",
                "skill_id": skill_id,
            }
        }
        edges: list[dict[str, Any]] = []

        if hops == 1:
            rows = self._ex.run(
                COOCCUR_ONE_HOP,
                {
                    "skill_id": skill_id,
                    "period": period,
                    "ontology_version": self._ontology_version,
                    "limit": cap,
                },
            )
            for row in rows:
                nid = f"skill:{row['neighbor_id']}"
                nodes.setdefault(
                    nid,
                    {
                        "id": nid,
                        "label": row.get("neighbor_name") or row["neighbor_id"],
                        "type": "skill",
                        "skill_id": row["neighbor_id"],
                    },
                )
                edges.append(
                    {
                        "id": f"cooccur:{skill_id}:{row['neighbor_id']}:{period}",
                        "source": f"skill:{skill_id}",
                        "target": nid,
                        "type": "co_occurs",
                        "shared_roles": int(row["shared_roles"]),
                        "weight": float(row["weight"]) if row.get("weight") is not None else None,
                    }
                )
        else:
            rows = self._ex.run(
                COOCCUR_TWO_HOP,
                {
                    "skill_id": skill_id,
                    "period": period,
                    "ontology_version": self._ontology_version,
                    "limit": cap,
                },
            )
            for row in rows:
                mid_id = f"skill:{row['mid_id']}"
                far_id = f"skill:{row['far_id']}"
                nodes.setdefault(
                    mid_id,
                    {
                        "id": mid_id,
                        "label": row.get("mid_name") or row["mid_id"],
                        "type": "skill",
                        "skill_id": row["mid_id"],
                    },
                )
                nodes.setdefault(
                    far_id,
                    {
                        "id": far_id,
                        "label": row.get("far_name") or row["far_id"],
                        "type": "skill",
                        "skill_id": row["far_id"],
                    },
                )
                hop1_edge = {
                    "id": f"cooccur:{skill_id}:{row['mid_id']}:{period}",
                    "source": f"skill:{skill_id}",
                    "target": mid_id,
                    "type": "co_occurs",
                    "hops": 1,
                    "shared_roles": int(row["hop1"]),
                }
                hop2_edge = {
                    "id": f"cooccur:{row['mid_id']}:{row['far_id']}:{period}",
                    "source": mid_id,
                    "target": far_id,
                    "type": "co_occurs",
                    "hops": 2,
                    "shared_roles": int(row["hop2"]),
                }
                if hop1_edge not in edges:
                    edges.append(hop1_edge)
                if hop2_edge not in edges:
                    edges.append(hop2_edge)

        capped_nodes, capped_edges = cap_graph(list(nodes.values()), edges, cap)
        return {
            "skill": detail,
            "period": period,
            "hops": hops,
            "ontology_version": self._ontology_version,
            "graph": cytoscape_graph(capped_nodes, capped_edges),
        }

    def compare_roles(self, role_id_a: str, role_id_b: str, period: str) -> dict[str, Any]:
        parse_period(period)
        rows = self._ex.run(
            COMPARE_ROLES,
            {
                "role_ids": [role_id_a, role_id_b],
                "period": period,
                "ontology_version": self._ontology_version,
            },
        )
        roles: dict[str, dict[str, Any]] = {}
        skills: dict[str, dict[str, dict[str, Any]]] = {role_id_a: {}, role_id_b: {}}
        for row in rows:
            rid = row["role_id"]
            roles[rid] = {
                "id": rid,
                "name": row.get("role_name") or rid,
                "state": row.get("role_state"),
            }
            if not row.get("skill_id"):
                continue
            skills.setdefault(rid, {})[row["skill_id"]] = {
                "skill_id": row["skill_id"],
                "name": row.get("skill_name") or row["skill_id"],
                "weight": float(row["weight"]) if row.get("weight") is not None else 0.0,
                "competency_id": row.get("competency_id"),
                "statement": row.get("statement"),
                "necessity": row.get("necessity"),
                "grade": row.get("grade"),
            }

        set_a = skills.get(role_id_a, {})
        set_b = skills.get(role_id_b, {})
        only_a = [set_a[k] for k in sorted(set(set_a) - set(set_b))]
        only_b = [set_b[k] for k in sorted(set(set_b) - set(set_a))]
        both = []
        for skill_id in sorted(set(set_a) & set(set_b)):
            both.append(
                {
                    "skill_id": skill_id,
                    "name": set_a[skill_id]["name"],
                    "weight_a": set_a[skill_id]["weight"],
                    "weight_b": set_b[skill_id]["weight"],
                    "delta": round(set_b[skill_id]["weight"] - set_a[skill_id]["weight"], 6),
                }
            )
        return {
            "period": period,
            "ontology_version": self._ontology_version,
            "role_a": roles.get(role_id_a) or {"id": role_id_a, "name": role_id_a, "state": None},
            "role_b": roles.get(role_id_b) or {"id": role_id_b, "name": role_id_b, "state": None},
            "only_a": only_a,
            "only_b": only_b,
            "both": both,
        }
