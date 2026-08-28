"""Neo4j 实现的 GraphRepository。

写入一律 MERGE，按时间片分片存 REQUIRES，不用 NULL 结束时间表示「当前有效」。
能力变更用 occurred_on / recorded_at 双时态，并用 superseded 显式标记是否被修正覆盖。
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from typing import Any

from app.domain.models import (
    ChangeKind,
    Competency,
    CompetencyChange,
    PublishState,
    Role,
    Skill,
    SkillObservation,
)
from app.graph.periods import parse_period, period_end
from app.graph.session import CypherExecutor

UPSERT_ROLE = """
MERGE (r:Role {id: $id})
SET r.name = $name,
    r.family_id = $family_id,
    r.occupation_code = $occupation_code,
    r.is_emerging = $is_emerging,
    r.state = $state,
    r.signal_strength = $signal_strength,
    r.created_at = $created_at,
    r.updated_at = $updated_at,
    r.responsibilities = $responsibilities,
    r.scenarios = $scenarios
WITH r
OPTIONAL MATCH (r)-[old:IN_FAMILY]->(:RoleFamily)
DELETE old
WITH r
FOREACH (_ IN CASE WHEN $family_id IS NULL THEN [] ELSE [1] END |
    MERGE (f:RoleFamily {id: $family_id})
    ON CREATE SET f.name = $family_id
    MERGE (r)-[:IN_FAMILY]->(f)
)
RETURN r.id AS id
"""

UPSERT_SKILL = """
MERGE (s:Skill {id: $id})
SET s.name = $name,
    s.ontology_version = $ontology_version,
    s.parent_id = $parent_id,
    s.cluster_id = $cluster_id
WITH s
OPTIONAL MATCH (old_parent:Skill)-[old:PARENT_OF]->(s)
WHERE $parent_id IS NULL OR old_parent.id <> $parent_id
DELETE old
WITH s
FOREACH (_ IN CASE WHEN $parent_id IS NULL THEN [] ELSE [1] END |
    MERGE (p:Skill {id: $parent_id})
    ON CREATE SET p.ontology_version = $ontology_version
    MERGE (p)-[:PARENT_OF]->(s)
)
WITH s
OPTIONAL MATCH (s)-[oldc:IN_CLUSTER]->(:SkillCluster)
DELETE oldc
WITH s
FOREACH (_ IN CASE WHEN $cluster_id IS NULL THEN [] ELSE [1] END |
    MERGE (k:SkillCluster {id: $cluster_id})
    ON CREATE SET k.name = $cluster_id, k.ontology_version = $ontology_version
    MERGE (s)-[:IN_CLUSTER]->(k)
)
RETURN s.id AS id
"""

UPSERT_COMPETENCY = """
MERGE (c:Competency {id: $id})
SET c.role_id = $role_id,
    c.statement = $statement,
    c.necessity = $necessity,
    c.importance = $importance,
    c.grade = $grade,
    c.state = $state
WITH c
OPTIONAL MATCH (c)-[old_cov:COVERS]->(:Skill)
DELETE old_cov
WITH c
FOREACH (sid IN $skill_ids |
    MERGE (sk:Skill {id: sid})
    MERGE (c)-[:COVERS]->(sk)
)
WITH c
OPTIONAL MATCH (old_r:Role)-[old_hc:HAS_COMPETENCY]->(c)
WHERE old_r.id <> $role_id
DELETE old_hc
WITH c
MERGE (r:Role {id: $role_id})
MERGE (r)-[:HAS_COMPETENCY]->(c)
RETURN c.id AS id
"""

RECORD_CHANGE = """
MERGE (ch:CompetencyChange {id: $id})
SET ch.role_id = $role_id,
    ch.competency_id = $competency_id,
    ch.kind = $kind,
    ch.before = $before,
    ch.after = $after,
    ch.reason = $reason,
    ch.occurred_on = $occurred_on,
    ch.recorded_at = $recorded_at,
    ch.state = $state,
    ch.superseded = $superseded
WITH ch
MERGE (r:Role {id: $role_id})
MERGE (r)-[:HAS_CHANGE]->(ch)
WITH ch
FOREACH (_ IN CASE WHEN $competency_id IS NULL THEN [] ELSE [1] END |
    MERGE (c:Competency {id: $competency_id})
    MERGE (ch)-[:FOR_COMPETENCY]->(c)
)
RETURN ch.id AS id
"""

PUT_OBSERVATION = """
MERGE (r:Role {id: $role_id})
MERGE (s:Skill {id: $skill_id})
ON CREATE SET s.ontology_version = $ontology_version, s.name = $skill_id
MERGE (r)-[req:REQUIRES {period: $period, ontology_version: $ontology_version}]->(s)
SET req.weight = $weight,
    req.posting_count = $posting_count,
    req.total_postings = $total_postings
RETURN r.id AS role_id, s.id AS skill_id, req.period AS period
"""

GET_ROLE = """
MATCH (r:Role {id: $id})
RETURN r {.*} AS role
"""

LIST_ROLES = """
MATCH (r:Role)
RETURN r {.*} AS role
ORDER BY r.name
"""

LATEST_PERIOD = """
MATCH ()-[req:REQUIRES]->()
WHERE req.ontology_version = $ontology_version
RETURN req.period AS period
ORDER BY req.period DESC
LIMIT 1
"""

ROLE_SKILLS = """
MATCH (r:Role {id: $role_id})-[req:REQUIRES]->(s:Skill)
WHERE req.ontology_version = $ontology_version
  AND ($period IS NULL OR req.period = $period)
RETURN $role_id AS role_id,
       s.id AS skill_id,
       req.period AS period,
       req.weight AS weight,
       req.posting_count AS posting_count,
       req.total_postings AS total_postings,
       req.ontology_version AS ontology_version
ORDER BY req.period, s.id
"""

SNAPSHOT_AT = """
MATCH (r:Role)-[req:REQUIRES]->(s:Skill)
WHERE req.period = $period AND req.ontology_version = $ontology_version
RETURN r {.*} AS role,
       s {.*} AS skill,
       req.weight AS weight,
       req.posting_count AS posting_count,
       req.total_postings AS total_postings
"""

DIFF_PERIOD = """
MATCH (r:Role)-[req:REQUIRES]->(s:Skill)
WHERE req.period = $period AND req.ontology_version = $ontology_version
OPTIONAL MATCH (c:Competency)-[:COVERS]->(s)
WHERE (r)-[:HAS_COMPETENCY]->(c)
RETURN r.id AS role_id,
       s.id AS skill_id,
       req.weight AS weight,
       c.id AS competency_id,
       c.statement AS statement
"""


def _iso(value: datetime | date | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return value.isoformat()


def _as_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    to_native = getattr(value, "to_native", None)
    if callable(to_native):
        native = to_native()
        if isinstance(native, datetime):
            return native
        if isinstance(native, date):
            return datetime(native.year, native.month, native.day, tzinfo=UTC)
    if isinstance(value, str):
        return datetime.fromisoformat(value)
    return None


def role_from_props(props: dict[str, Any]) -> Role:
    state_raw = props.get("state") or PublishState.UNVERIFIED.value
    signal = props.get("signal_strength")
    return Role(
        id=props["id"],
        name=props.get("name") or "",
        family_id=props.get("family_id"),
        responsibilities=list(props.get("responsibilities") or []),
        scenarios=list(props.get("scenarios") or []),
        occupation_code=props.get("occupation_code"),
        is_emerging=bool(props.get("is_emerging") or False),
        state=PublishState(state_raw),
        signal_strength=float(signal) if signal is not None else None,
        evidence_ids=[],
        created_at=_as_datetime(props.get("created_at")),
        updated_at=_as_datetime(props.get("updated_at")),
    )


def observation_from_row(row: dict[str, Any]) -> SkillObservation:
    return SkillObservation(
        role_id=row.get("role_id"),
        skill_id=row["skill_id"],
        period=row["period"],
        weight=float(row["weight"]),
        posting_count=int(row["posting_count"]),
        total_postings=int(row["total_postings"]),
        ontology_version=row["ontology_version"],
    )


def _skill_payload(weights: dict[str, float]) -> str:
    ordered = {k: round(float(v), 6) for k, v in sorted(weights.items())}
    return json.dumps({"skills": ordered}, ensure_ascii=False)


def _group_period_rows(
    rows: list[dict[str, Any]],
) -> dict[tuple[str, str], dict[str, Any]]:
    """(role_id, competency_id) → {weights, statement}。无能力项时用 skill:<id> 兜底。"""
    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        role_id = row["role_id"]
        skill_id = row["skill_id"]
        competency_id = row.get("competency_id") or f"skill:{skill_id}"
        key = (role_id, competency_id)
        bucket = grouped.setdefault(key, {"weights": {}, "statement": row.get("statement")})
        bucket["weights"][skill_id] = float(row["weight"])
        if row.get("statement"):
            bucket["statement"] = row["statement"]
    return grouped


def compute_competency_diff(
    rows_a: list[dict[str, Any]],
    rows_b: list[dict[str, Any]],
    period_a: str,
    period_b: str,
    *,
    recorded_at: datetime | None = None,
) -> list[CompetencyChange]:
    """比较两个时间片的能力项观测，产出新增 / 删除 / 修改。

    判定：
    - 新增：B 期有该能力项覆盖的技能点，A 期没有
    - 删除：A 期有、B 期没有
    - 修改：两期都有，但技能点集合或重要度不同
    同一本体版本由调用方在查询时过滤，本函数不再混版本。
    """
    parse_period(period_a)
    parse_period(period_b)
    grouped_a = _group_period_rows(rows_a)
    grouped_b = _group_period_rows(rows_b)
    occurred_on = period_end(period_b)
    stamp = recorded_at or datetime.now(UTC)
    changes: list[CompetencyChange] = []

    all_keys = sorted(set(grouped_a) | set(grouped_b))
    for role_id, competency_id in all_keys:
        a = grouped_a.get((role_id, competency_id))
        b = grouped_b.get((role_id, competency_id))
        if a is None and b is not None:
            kind = ChangeKind.ADDED
            before = None
            after = _skill_payload(b["weights"])
            reason = f"时间片 {period_b} 相对 {period_a} 新增该能力项"
        elif a is not None and b is None:
            kind = ChangeKind.REMOVED
            before = _skill_payload(a["weights"])
            after = None
            reason = f"时间片 {period_b} 相对 {period_a} 不再要求该能力项"
        else:
            assert a is not None and b is not None
            if a["weights"] == b["weights"]:
                continue
            kind = ChangeKind.MODIFIED
            before = _skill_payload(a["weights"])
            after = _skill_payload(b["weights"])
            reason = f"时间片 {period_b} 相对 {period_a} 该能力项的技能点或重要度发生变化"

        changes.append(
            CompetencyChange(
                id=f"{role_id}:{competency_id}:{period_a}:{period_b}:{kind.value}",
                role_id=role_id,
                competency_id=competency_id,
                kind=kind,
                before=before,
                after=after,
                reason=reason,
                evidence_ids=[],
                occurred_on=occurred_on,
                recorded_at=stamp,
                state=PublishState.PUBLISHED,
            )
        )
    return changes


class Neo4jGraphRepository:
    """GraphRepository 的 Neo4j 实现。ontology_version 在构造时注入，不出现在端口签名里。"""

    def __init__(self, executor: CypherExecutor, ontology_version: str) -> None:
        self._ex = executor
        self._ontology_version = ontology_version

    def upsert_role(self, role: Role) -> str:
        self._ex.run(
            UPSERT_ROLE,
            {
                "id": role.id,
                "name": role.name,
                "family_id": role.family_id,
                "occupation_code": role.occupation_code,
                "is_emerging": role.is_emerging,
                "state": role.state.value,
                "signal_strength": role.signal_strength,
                "created_at": _iso(role.created_at),
                "updated_at": _iso(role.updated_at),
                "responsibilities": list(role.responsibilities),
                "scenarios": list(role.scenarios),
            },
            write=True,
        )
        return role.id

    def upsert_skill(self, skill: Skill) -> str:
        self._ex.run(
            UPSERT_SKILL,
            {
                "id": skill.id,
                "name": skill.name,
                "ontology_version": skill.ontology_version,
                "parent_id": skill.parent_id,
                "cluster_id": skill.cluster_id,
            },
            write=True,
        )
        return skill.id

    def upsert_competency(self, competency: Competency) -> str:
        self._ex.run(
            UPSERT_COMPETENCY,
            {
                "id": competency.id,
                "role_id": competency.role_id,
                "statement": competency.statement,
                "necessity": competency.necessity.value,
                "importance": competency.importance,
                "grade": competency.grade.value,
                "state": competency.state.value,
                "skill_ids": list(competency.skill_ids),
            },
            write=True,
        )
        return competency.id

    def record_change(self, change: CompetencyChange) -> str:
        # superseded 显式布尔，避免用结束时间为 NULL 表示「当前有效」
        self._ex.run(
            RECORD_CHANGE,
            {
                "id": change.id,
                "role_id": change.role_id,
                "competency_id": change.competency_id,
                "kind": change.kind.value,
                "before": change.before,
                "after": change.after,
                "reason": change.reason,
                "occurred_on": _iso(change.occurred_on),
                "recorded_at": _iso(change.recorded_at),
                "state": change.state.value,
                "superseded": False,
            },
            write=True,
        )
        return change.id

    def put_observation(self, observation: SkillObservation) -> None:
        if observation.role_id is None:
            raise ValueError("put_observation 需要 role_id 才能写入 Role-REQUIRES-Skill 分片边")
        parse_period(observation.period)
        self._ex.run(
            PUT_OBSERVATION,
            {
                "role_id": observation.role_id,
                "skill_id": observation.skill_id,
                "period": observation.period,
                "ontology_version": observation.ontology_version,
                "weight": observation.weight,
                "posting_count": observation.posting_count,
                "total_postings": observation.total_postings,
            },
            write=True,
        )

    def get_role(self, role_id: str) -> Role | None:
        rows = self._ex.run(GET_ROLE, {"id": role_id})
        if not rows or rows[0].get("role") is None:
            return None
        return role_from_props(rows[0]["role"])

    def list_roles(self) -> list[Role]:
        rows = self._ex.run(LIST_ROLES)
        return [role_from_props(row["role"]) for row in rows if row.get("role")]

    def latest_period(self) -> str | None:
        rows = self._ex.run(LATEST_PERIOD, {"ontology_version": self._ontology_version})
        if not rows:
            return None
        period = rows[0].get("period")
        return str(period) if period else None

    def role_skills(self, role_id: str, period: str | None = None) -> list[SkillObservation]:
        if period is not None:
            parse_period(period)
        rows = self._ex.run(
            ROLE_SKILLS,
            {
                "role_id": role_id,
                "period": period,
                "ontology_version": self._ontology_version,
            },
        )
        return [observation_from_row(row) for row in rows]

    def snapshot_at(self, period: str) -> dict[str, Any]:
        parse_period(period)
        rows = self._ex.run(
            SNAPSHOT_AT,
            {"period": period, "ontology_version": self._ontology_version},
        )
        roles: dict[str, dict[str, Any]] = {}
        skills: dict[str, dict[str, Any]] = {}
        requirements: list[dict[str, Any]] = []
        for row in rows:
            role = role_from_props(row["role"])
            skill_props = row["skill"] or {}
            skill_id = skill_props["id"]
            roles[role.id] = {
                "id": role.id,
                "name": role.name,
                "state": role.state.value,
                "family_id": role.family_id,
                "is_emerging": role.is_emerging,
            }
            skills[skill_id] = {
                "id": skill_id,
                "name": skill_props.get("name") or "",
                "ontology_version": skill_props.get("ontology_version") or self._ontology_version,
                "cluster_id": skill_props.get("cluster_id"),
                "parent_id": skill_props.get("parent_id"),
            }
            requirements.append(
                {
                    "role_id": role.id,
                    "skill_id": skill_id,
                    "weight": float(row["weight"]),
                    "posting_count": int(row["posting_count"]),
                    "total_postings": int(row["total_postings"]),
                }
            )
        return {
            "period": period,
            "ontology_version": self._ontology_version,
            "roles": sorted(roles.values(), key=lambda item: item["id"]),
            "skills": sorted(skills.values(), key=lambda item: item["id"]),
            "requirements": requirements,
        }

    def diff(self, period_a: str, period_b: str) -> list[CompetencyChange]:
        parse_period(period_a)
        parse_period(period_b)
        params_a = {"period": period_a, "ontology_version": self._ontology_version}
        params_b = {"period": period_b, "ontology_version": self._ontology_version}
        rows_a = self._ex.run(DIFF_PERIOD, params_a)
        rows_b = self._ex.run(DIFF_PERIOD, params_b)
        return compute_competency_diff(rows_a, rows_b, period_a, period_b)
