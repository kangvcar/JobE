"""把各模块的原语组合成前端一屏能用的形状。"""

from __future__ import annotations

from collections import defaultdict
from datetime import date

from app.config import get_settings
from app.domain.models import (
    EvidenceGrade,
    PublishState,
    Role,
    Skill,
    SkillCluster,
    SkillObservation,
)
from app.domain.normalization import period_from_date
from app.evolution.burst import KleinbergBurstDetector
from app.graph.repository import Neo4jGraphRepository
from app.pages.models import (
    CandidateCard,
    DocumentPage,
    EvidenceDetail,
    GraphEdge,
    GraphNode,
    GraphPayload,
    GraphView,
    MarketOverview,
    MeHome,
    RoleDetail,
    SkillDetail,
    SkillMarketMove,
    SourceDocument,
)
from app.pipeline.ingest import load_clusters, load_ontology_skills
from app.storage.documents import PgDocumentStore
from app.storage.evidence import PgEvidenceStore
from app.storage.observations import ObservationStore

LEVEL_FOUNDATION = "level.foundation"
LEVEL_METHOD = "level.method"
LEVEL_LABELS = {
    LEVEL_FOUNDATION: "基础层",
    LEVEL_METHOD: "方法层",
}


def previous_period(period: str) -> str:
    year = int(period[:4])
    q = int(period[-1])
    if q == 1:
        return f"{year - 1}Q4"
    return f"{year}Q{q - 1}"


def _source_name(source_id: str) -> str:
    return {"moka": "Moka 公开招聘", "mohrss": "中国公共招聘网", "liepin": "猎聘"}.get(
        source_id, source_id
    )


def _skill_id_from_extractor(extractor: str) -> str | None:
    if extractor.startswith("ac:"):
        return extractor[3:]
    return None


def _lines_from_text(text: str) -> list[dict]:
    lines = []
    y = 0.04
    for i, raw in enumerate(text.splitlines() or [text]):
        lines.append({"text": raw, "x": 0.06, "y": min(0.96, y + i * 0.035), "width": 0.88})
    return lines[:80]


class PageService:
    def __init__(
        self,
        repo: Neo4jGraphRepository,
        observations: ObservationStore,
        evidence: PgEvidenceStore,
        documents: PgDocumentStore,
    ) -> None:
        self._repo = repo
        self._obs = observations
        self._evidence = evidence
        self._documents = documents
        self._skills = load_ontology_skills()
        self._cluster_names = load_clusters()

    def current_period(self) -> str:
        return self._repo.latest_period() or period_from_date(date.today()) or "2026Q3"

    def list_roles(self) -> list[Role]:
        return self._repo.list_roles()

    def me_home(self, profile_id: str | None, role_id: str | None) -> MeHome:
        period = self.current_period()
        prev = previous_period(period)
        roles = self.list_roles()
        role = next((r for r in roles if r.id == role_id), None) if role_id else None
        if role is None:
            role = roles[0] if roles else None
        required: list[SkillObservation] = []
        if role is not None:
            required = [
                o for o in self._repo.role_skills(role.id, period) if o.period == period
            ] or self._repo.role_skills(role.id)
        required_ids = [o.skill_id for o in required]
        rising, falling = self._moves_for_role(role.id, period, prev) if role else ([], [])
        return MeHome(
            period=period,
            previous_period=prev,
            profile=None,
            role=role,
            match=None,
            path=None,
            rising=rising,
            falling=falling,
            required_skill_ids=required_ids,
            held_count=0,
            required_count=len(required_ids),
            previous_required_count=len(required_ids),
        )

    def _moves_for_role(
        self, role_id: str, period: str, prev: str
    ) -> tuple[list[SkillMarketMove], list[SkillMarketMove]]:
        now = {o.skill_id: o.weight for o in self._repo.role_skills(role_id, period)}
        was = {o.skill_id: o.weight for o in self._repo.role_skills(role_id, prev)}
        rising: list[SkillMarketMove] = []
        falling: list[SkillMarketMove] = []
        for sid, weight in now.items():
            delta = weight - was.get(sid, 0.0)
            move = SkillMarketMove(
                skill_id=sid,
                delta=round(delta, 4),
                from_period=prev,
                to_period=period,
                direction="rise" if delta > 0.02 else "fall" if delta < -0.02 else "flat",
            )
            if move.direction == "rise":
                rising.append(move)
            elif move.direction == "fall":
                falling.append(move)
        rising.sort(key=lambda m: m.delta, reverse=True)
        falling.sort(key=lambda m: m.delta)
        return rising[:8], falling[:8]

    def graph_overview(self, view: GraphView) -> GraphPayload:
        period = self.current_period()
        snap = self._repo.snapshot_at(period)
        nodes: list[GraphNode] = []
        edges: list[GraphEdge] = []
        clusters: list[SkillCluster] = []
        used_clusters: dict[str, list[str]] = defaultdict(list)

        if view == "stack":
            for skill in snap["skills"]:
                cid = skill.get("cluster_id")
                if cid:
                    used_clusters[cid].append(skill["id"])
            for cid, sids in used_clusters.items():
                nodes.append(
                    GraphNode(
                        id=cid,
                        kind="cluster",
                        label=self._cluster_names.get(cid, cid),
                        stack=cid,
                    )
                )
                clusters.append(
                    SkillCluster(
                        id=cid,
                        name=self._cluster_names.get(cid, cid),
                        skill_ids=sids,
                        ontology_version=get_settings().ontology_version,
                    )
                )
        else:
            nodes.append(
                GraphNode(
                    id=LEVEL_FOUNDATION,
                    kind="level",
                    label=LEVEL_LABELS[LEVEL_FOUNDATION],
                    level=LEVEL_FOUNDATION,
                )
            )
            nodes.append(
                GraphNode(
                    id=LEVEL_METHOD,
                    kind="level",
                    label=LEVEL_LABELS[LEVEL_METHOD],
                    level=LEVEL_METHOD,
                )
            )

        present_ids = {s["id"] for s in snap["skills"]} | set(used_clusters) | {
            LEVEL_FOUNDATION,
            LEVEL_METHOD,
        }
        for skill in snap["skills"]:
            cid = skill.get("cluster_id")
            parent = (
                cid
                if view == "stack"
                else (LEVEL_METHOD if skill.get("parent_id") else LEVEL_FOUNDATION)
            )
            nodes.append(
                GraphNode(
                    id=skill["id"],
                    kind="skill",
                    label=skill.get("name") or skill["id"],
                    parent=parent,
                    stack=cid,
                    level=LEVEL_METHOD if skill.get("parent_id") else LEVEL_FOUNDATION,
                    grade=EvidenceGrade.SINGLE_SOURCE,
                )
            )
            if parent:
                edges.append(
                    GraphEdge(
                        id=f"member:{skill['id']}", source=parent, target=skill["id"], kind="member"
                    )
                )
            if view == "stack" and skill.get("parent_id") and skill["parent_id"] in present_ids:
                edges.append(
                    GraphEdge(
                        id=f"parent:{skill['id']}",
                        source=skill["parent_id"],
                        target=skill["id"],
                        kind="parent",
                    )
                )

        for role in snap["roles"]:
            nodes.append(
                GraphNode(
                    id=role["id"],
                    kind="role",
                    label=role.get("name") or role["id"],
                    emerging=bool(role.get("is_emerging"))
                    and role.get("state") == PublishState.PUBLISHED.value,
                    candidate=role.get("state") == PublishState.UNVERIFIED.value,
                )
            )
        for req in snap["requirements"]:
            edges.append(
                GraphEdge(
                    id=f"requires:{req['role_id']}:{req['skill_id']}",
                    source=req["role_id"],
                    target=req["skill_id"],
                    kind="requires",
                )
            )
        return GraphPayload(nodes=nodes, edges=edges, clusters=clusters, families=[], period=period)

    def role_detail(self, role_id: str) -> RoleDetail | None:
        role = self._repo.get_role(role_id)
        if role is None:
            return None
        period = self.current_period()
        obs = self._repo.role_skills(role_id, period) or self._repo.role_skills(role_id)
        skills = []
        for o in obs:
            skill = self._skills.get(o.skill_id) or Skill(
                id=o.skill_id, name=o.skill_id, ontology_version=o.ontology_version
            )
            skills.append(skill)
        prev = previous_period(period)
        try:
            changes = self._repo.diff(prev, period)
            changes = [c for c in changes if c.role_id == role_id]
        except ValueError:
            changes = []
        return RoleDetail(role=role, competencies=[], changes=changes, skills=skills)

    def skill_detail(self, skill_id: str) -> SkillDetail | None:
        skill = self._skills.get(skill_id)
        period = self.current_period()
        snap = self._repo.snapshot_at(period)
        mentioned = any(s["id"] == skill_id for s in snap["skills"])
        if skill is None and not mentioned:
            return None
        if skill is None:
            hit = next(s for s in snap["skills"] if s["id"] == skill_id)
            skill = Skill(
                id=skill_id,
                name=hit.get("name") or skill_id,
                ontology_version=hit.get("ontology_version") or get_settings().ontology_version,
                cluster_id=hit.get("cluster_id"),
                parent_id=hit.get("parent_id"),
            )
        cluster = None
        if skill.cluster_id:
            cluster = SkillCluster(
                id=skill.cluster_id,
                name=self._cluster_names.get(skill.cluster_id, skill.cluster_id),
                skill_ids=[skill_id],
                ontology_version=skill.ontology_version,
            )
        series = list(self._obs.iter_for_skill(skill_id))
        bursts = KleinbergBurstDetector().detect(series) if series else []
        role_ids = {req["role_id"] for req in snap["requirements"] if req["skill_id"] == skill_id}
        roles = [self._repo.get_role(rid) for rid in role_ids]
        return SkillDetail(
            skill=skill,
            cluster=cluster,
            observations=series,
            bursts=bursts,
            roles=[r for r in roles if r is not None],
        )

    def market(self) -> MarketOverview:
        period = self.current_period()
        roles = self.list_roles()
        emerging = [r for r in roles if r.is_emerging]
        candidates = [
            CandidateCard(
                **r.model_dump(),
                evidence_count=len(r.evidence_ids),
                signal_band="strong"
                if (r.signal_strength or 0) >= 0.65
                else "medium"
                if (r.signal_strength or 0) >= 0.4
                else "weak",
            )
            for r in roles
            if r.state == PublishState.UNVERIFIED
        ]
        obs = [o for o in self._obs.iter_for_period(period)]
        by_skill: dict[str, list[SkillObservation]] = defaultdict(list)
        for o in self._obs.iter_all():
            by_skill[o.skill_id].append(o)
        bursts = []
        detector = KleinbergBurstDetector()
        for series in by_skill.values():
            bursts.extend(detector.detect(series))
        prev = previous_period(period)
        try:
            changes = self._repo.diff(prev, period)
        except ValueError:
            changes = []
        trend = sorted(
            {o.skill_id for o in obs},
            key=lambda sid: -sum(x.weight for x in obs if x.skill_id == sid),
        )[:12]
        return MarketOverview(
            period=period,
            emerging=emerging,
            candidates=candidates,
            changes=changes,
            bursts=bursts[:40],
            lead_lag=[],
            trend_skill_ids=trend,
            observations=obs,
        )

    def candidates(self) -> list[CandidateCard]:
        return self.market().candidates

    def evidence_detail(self, evidence_id: str) -> EvidenceDetail | None:
        ev = self._evidence.get(evidence_id)
        if ev is None:
            return None
        doc_row = self._documents.get(ev.span.doc_id) if ev.span.doc_id else None
        text = doc_row["canonical_text"] if doc_row else ev.quote
        title = ev.span.doc_id or evidence_id
        skill_id = _skill_id_from_extractor(ev.extractor)
        return EvidenceDetail(
            **ev.model_dump(),
            source_name=_source_name(ev.source_id),
            skill_id=skill_id,
            role_id=None,
            document=SourceDocument(
                id=ev.span.doc_id or evidence_id,
                kind=doc_row["kind"] if doc_row else "posting",
                title=title,
                text=text,
                pages=[DocumentPage(page_index=0, lines=_lines_from_text(text))],
            ),
        )

    def evidence_batch(self, ids: list[str]) -> list[EvidenceDetail]:
        out = []
        for eid in ids:
            item = self.evidence_detail(eid)
            if item is not None:
                out.append(item)
        return out
