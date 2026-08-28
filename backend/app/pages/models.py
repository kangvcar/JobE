"""前端页面聚合的读模型。字段名与 frontend/src/api/types.ts 对齐。"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.domain.models import (
    Burst,
    Competency,
    CompetencyChange,
    Evidence,
    EvidenceGrade,
    LeadLag,
    LearningPath,
    MatchResult,
    Necessity,
    Role,
    RoleFamily,
    Skill,
    SkillCluster,
    SkillObservation,
    SkillProfile,
)

GraphView = Literal["stack", "level"]
SignalBand = Literal["weak", "medium", "strong"]
MoveDirection = Literal["rise", "fall", "flat"]
GraphNodeKind = Literal["skill", "role", "cluster", "level"]
GraphEdgeKind = Literal["requires", "member", "parent", "related"]
ReviewKind = Literal["emerging_publish", "required_removed", "signal_conflict", "user_report"]


class GraphNode(BaseModel):
    id: str
    kind: GraphNodeKind
    label: str
    parent: str | None = None
    stack: str | None = None
    level: str | None = None
    emerging: bool | None = None
    candidate: bool | None = None
    grade: EvidenceGrade | None = None


class GraphEdge(BaseModel):
    id: str
    source: str
    target: str
    kind: GraphEdgeKind
    necessity: Necessity | None = None


class GraphPayload(BaseModel):
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    clusters: list[SkillCluster] = Field(default_factory=list)
    families: list[RoleFamily] = Field(default_factory=list)
    period: str


class DocumentPage(BaseModel):
    page_index: int
    width: float = 1.0
    height: float = 1.0
    lines: list[dict] = Field(default_factory=list)


class SourceDocument(BaseModel):
    id: str
    kind: str
    title: str
    text: str
    pages: list[DocumentPage] = Field(default_factory=list)


class EvidenceDetail(Evidence):
    source_name: str
    skill_id: str | None = None
    role_id: str | None = None
    document: SourceDocument


class SkillMarketMove(BaseModel):
    skill_id: str
    direction: MoveDirection
    delta: float
    from_period: str
    to_period: str


class MeHome(BaseModel):
    period: str
    previous_period: str
    profile: SkillProfile | None = None
    role: Role | None = None
    match: MatchResult | None = None
    path: LearningPath | None = None
    rising: list[SkillMarketMove] = Field(default_factory=list)
    falling: list[SkillMarketMove] = Field(default_factory=list)
    required_skill_ids: list[str] = Field(default_factory=list)
    held_count: int = 0
    required_count: int = 0
    previous_required_count: int = 0


class DiagnoseResult(BaseModel):
    case_id: str
    person_name: str
    person_note: str
    profile: SkillProfile
    role: Role
    match: MatchResult
    path: LearningPath
    resume: SourceDocument


class CandidateCard(Role):
    evidence_count: int = 0
    signal_band: SignalBand = "weak"


class ReviewItem(BaseModel):
    id: str
    kind: ReviewKind
    title: str
    body: str
    role_id: str | None = None
    skill_id: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)
    ai_verdict: str | None = None
    created_at: str


class SkillDetail(BaseModel):
    skill: Skill
    cluster: SkillCluster | None = None
    grade: EvidenceGrade = EvidenceGrade.SINGLE_SOURCE
    evidence_ids: list[str] = Field(default_factory=list)
    observations: list[SkillObservation] = Field(default_factory=list)
    bursts: list[Burst] = Field(default_factory=list)
    lead_lag: LeadLag | None = None
    roles: list[Role] = Field(default_factory=list)


class RoleDetail(BaseModel):
    role: Role
    competencies: list[Competency] = Field(default_factory=list)
    changes: list[CompetencyChange] = Field(default_factory=list)
    skills: list[Skill] = Field(default_factory=list)


class MarketOverview(BaseModel):
    period: str
    emerging: list[Role] = Field(default_factory=list)
    candidates: list[CandidateCard] = Field(default_factory=list)
    changes: list[CompetencyChange] = Field(default_factory=list)
    bursts: list[Burst] = Field(default_factory=list)
    lead_lag: list[LeadLag] = Field(default_factory=list)
    trend_skill_ids: list[str] = Field(default_factory=list)
    observations: list[SkillObservation] = Field(default_factory=list)
