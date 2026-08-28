"""匹配模块的视图对象。不替代 domain.models，只补齐诊断所需的字段。"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.domain.models import (
    Gap,
    GapKind,
    MatchResult,
    MatchTier,
    Necessity,
)


class RoleSkillSpec(BaseModel):
    """岗位对单个技能点的要求。图谱模块应组装此视图后交给本模块。

    required_level 与 ProfileSkill.level 同一标尺（0–3）。图谱若暂无水平字段，
    约定必备默认 2、加分默认 1。
    """

    skill_id: str
    necessity: Necessity = Necessity.REQUIRED
    importance: float = 0.0
    required_level: int = Field(default=2, ge=0, le=3)


class SkillJudgment(BaseModel):
    """该技能点是否满足岗位要求的原子判断。评测分解指标。"""

    skill_id: str
    necessity: Necessity
    importance: float
    required_level: int
    held_level: int
    satisfied: bool
    gap_kind: GapKind | None = None


class RoleRecommendation(BaseModel):
    """反向推荐的一条岗位。score 是可排序连续分值，供 NDCG / Spearman 使用。"""

    role_id: str
    role_name: str
    tier: MatchTier
    score: float
    coverage: float


class Diagnosis(BaseModel):
    """诊断结果。比 MatchResult 多技能级判定与连续分值，供前端可视化。"""

    profile_id: str
    role_id: str
    tier: MatchTier
    coverage: float
    score: float
    gaps: list[Gap] = Field(default_factory=list)
    judgments: list[SkillJudgment] = Field(default_factory=list)
    rationale: str = ""
    better_fit_roles: list[RoleRecommendation] = Field(default_factory=list)

    def to_match_result(self) -> MatchResult:
        return MatchResult(
            profile_id=self.profile_id,
            role_id=self.role_id,
            tier=self.tier,
            coverage=self.coverage,
            gaps=self.gaps,
            rationale=self.rationale,
        )
