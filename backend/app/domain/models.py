"""领域模型。

术语的权威定义在仓库根目录的 CONTEXT.md，本文件的类名与之一一对应：
Posting=职位, Snapshot=快照, Source=来源, Role=岗位, Competency=能力项,
Skill=技能点, Evidence=证据, CompetencyChange=能力变更, SkillProfile=技能画像。

这里只放数据形状，不放行为。跨模块的行为契约在 ports.py。
"""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class EvidenceGrade(StrEnum):
    """证据等级。"""

    MULTI_SOURCE = "multi_source"
    SINGLE_SOURCE = "single_source"
    WEAK = "weak"


class PublishState(StrEnum):
    """一条结论在发布流程中的状态。UNVERIFIED 即 CONTEXT.md 里的"待确认"。"""

    UNVERIFIED = "unverified"
    HELD = "held"
    PUBLISHED = "published"
    REJECTED = "rejected"


class Necessity(StrEnum):
    REQUIRED = "required"
    BONUS = "bonus"


class ChangeKind(StrEnum):
    ADDED = "added"
    REMOVED = "removed"
    MODIFIED = "modified"


class MatchTier(StrEnum):
    """匹配档位。评测时系统输出与专家标注同档即算正确。"""

    STRONG = "strong"
    ADEQUATE = "adequate"
    GAPPED = "gapped"
    MISMATCH = "mismatch"


class GapKind(StrEnum):
    MISSING = "missing"
    INSUFFICIENT = "insufficient"
    SURPLUS = "surplus"


class TextSpan(BaseModel):
    """一个片段在文档规范化文本中的字符区间，以及可选的版面坐标。

    坐标一律由确定性的字符串匹配回填，大模型不得输出坐标（见 ADR 0003）。
    """

    doc_id: str
    start: int
    end: int
    page_index: int | None = None
    bbox: tuple[float, float, float, float] | None = None


class Source(BaseModel):
    id: str
    name: str
    license: str
    requires_login: bool = False
    is_leading_indicator: bool = False


class Snapshot(BaseModel):
    """一经写入不再修改。分析层只读快照，不读网络。"""

    id: str
    source_id: str
    fetched_at: datetime
    url: str | None = None
    content_hash: str
    payload: dict


class Posting(BaseModel):
    id: str
    source_id: str
    snapshot_id: str
    title: str
    company: str | None = None
    city: str | None = None
    published_at: date | None = None
    updated_at: date | None = None
    description: str | None = None
    occupation_code: str | None = None
    salary_min: int | None = None
    salary_max: int | None = None
    duplicate_of: str | None = None
    boilerplate_spans: list[tuple[int, int]] = Field(default_factory=list)

    @property
    def is_duplicate(self) -> bool:
        return self.duplicate_of is not None


class Evidence(BaseModel):
    id: str
    source_id: str
    span: TextSpan
    quote: str
    fetched_at: datetime
    extractor: str
    confidence: float
    posting_id: str | None = None


class Skill(BaseModel):
    """技能点：最细粒度、可被单独验证的能力单元。"""

    id: str
    name: str
    aliases: list[str] = Field(default_factory=list)
    parent_id: str | None = None
    cluster_id: str | None = None
    ontology_version: str
    external_ids: dict[str, str] = Field(default_factory=dict)


class SkillCluster(BaseModel):
    id: str
    name: str
    skill_ids: list[str] = Field(default_factory=list)
    ontology_version: str


class Competency(BaseModel):
    """能力项：岗位要求中的一条能力陈述，是技能点之上的聚合层。"""

    id: str
    role_id: str
    statement: str
    skill_ids: list[str] = Field(default_factory=list)
    necessity: Necessity = Necessity.REQUIRED
    importance: float = 0.0
    evidence_ids: list[str] = Field(default_factory=list)
    grade: EvidenceGrade = EvidenceGrade.WEAK
    state: PublishState = PublishState.UNVERIFIED


class Role(BaseModel):
    """岗位。occupation_code 为空即表示国家标准职业目录中无对应条目。"""

    id: str
    name: str
    family_id: str | None = None
    responsibilities: list[str] = Field(default_factory=list)
    scenarios: list[str] = Field(default_factory=list)
    occupation_code: str | None = None
    is_emerging: bool = False
    state: PublishState = PublishState.UNVERIFIED
    signal_strength: float | None = None
    evidence_ids: list[str] = Field(default_factory=list)
    created_at: datetime | None = None
    updated_at: datetime | None = None


class RoleFamily(BaseModel):
    id: str
    name: str
    role_ids: list[str] = Field(default_factory=list)


class CompetencyChange(BaseModel):
    """能力变更。occurred_on 是业务发生时间，recorded_at 是记录时间（见 ADR 0005）。"""

    id: str
    role_id: str
    competency_id: str
    kind: ChangeKind
    before: str | None = None
    after: str | None = None
    reason: str
    evidence_ids: list[str] = Field(default_factory=list)
    occurred_on: date
    recorded_at: datetime
    state: PublishState = PublishState.UNVERIFIED


class SkillObservation(BaseModel):
    """按时间片的技能重要度观测值，对应图中的分片加权边。

    posting_count / total_postings 这对分子分母同期的设计，是突增检测消除
    "职位总量增长导致伪突增"的前提。
    """

    role_id: str | None
    skill_id: str
    period: str
    weight: float
    posting_count: int
    total_postings: int
    ontology_version: str


class Burst(BaseModel):
    skill_id: str
    source_id: str
    start_period: str
    end_period: str
    level: int
    weight: float


class LeadLag(BaseModel):
    """技术信号突增时点与招聘需求突增时点之间的时间差。"""

    skill_id: str
    leading_source_id: str
    lagging_source_id: str
    lag_periods: int
    correlation: float
    p_value: float


class ProfileSkill(BaseModel):
    skill_id: str
    level: int = Field(ge=0, le=3)
    surface_form: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)


class SkillProfile(BaseModel):
    id: str
    user_id: str | None = None
    resume_doc_id: str | None = None
    skills: list[ProfileSkill] = Field(default_factory=list)
    created_at: datetime | None = None


class Gap(BaseModel):
    skill_id: str
    kind: GapKind
    required_importance: float
    held_level: int
    urgency: float


class MatchResult(BaseModel):
    profile_id: str
    role_id: str
    tier: MatchTier
    coverage: float
    gaps: list[Gap] = Field(default_factory=list)
    rationale: str = ""


class Resource(BaseModel):
    title: str
    url: str
    kind: str
    source: str
    checked_at: datetime | None = None


class LearningStep(BaseModel):
    skill_id: str
    order: int
    prerequisites: list[str] = Field(default_factory=list)
    reason: str = ""
    resources: list[Resource] = Field(default_factory=list)


class LearningPath(BaseModel):
    profile_id: str
    role_id: str
    steps: list[LearningStep] = Field(default_factory=list)


class ReviewVerdict(StrEnum):
    SUPPORTED = "supported"
    UNSUPPORTED = "unsupported"
    UNCERTAIN = "uncertain"


class ReviewOutcome(BaseModel):
    verdict: ReviewVerdict
    reason: str
    cited_evidence_ids: list[str] = Field(default_factory=list)
