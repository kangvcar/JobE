"""匹配诊断门面。路由只依赖本模块；上游通过协议注入。"""

from __future__ import annotations

from app.domain.models import GapKind, LearningPath, SkillProfile
from app.domain.ports import LLMClient
from app.matching.discover import recommend_roles
from app.matching.gap import analyze_gaps
from app.matching.path import plan_learning_path
from app.matching.protocols import (
    BurstSource,
    LinkChecker,
    PrerequisiteSource,
    ResourceCache,
    ResourceCatalog,
    RoleRequirementSource,
)
from app.matching.resources import ResourceAttacher
from app.matching.tier import (
    compute_metrics,
    decide_tier,
    judge_skills,
    profile_levels,
    ranking_score,
    template_rationale,
)
from app.matching.types import Diagnosis, RoleRecommendation


class RoleNotFoundError(Exception):
    def __init__(self, role_id: str) -> None:
        self.role_id = role_id
        super().__init__(role_id)


class MatchingNotConfiguredError(Exception):
    """服务尚未注入。集成时调用 set_matching_service。"""


class MatchingService:
    def __init__(
        self,
        requirements: RoleRequirementSource,
        prerequisites: PrerequisiteSource,
        bursts: BurstSource,
        *,
        llm: LLMClient | None = None,
        attacher: ResourceAttacher | None = None,
        catalog: ResourceCatalog | None = None,
        cache: ResourceCache | None = None,
        checker: LinkChecker | None = None,
    ) -> None:
        self._requirements = requirements
        self._prerequisites = prerequisites
        self._bursts = bursts
        self._llm = llm
        if attacher is not None:
            self._attacher = attacher
        elif catalog is not None and cache is not None and checker is not None:
            self._attacher = ResourceAttacher(cache, catalog, checker, llm)
        else:
            self._attacher = None

    def _build(self, profile: SkillProfile, role_id: str, period: str | None) -> Diagnosis:
        if self._requirements.get_role(role_id) is None:
            raise RoleNotFoundError(role_id)
        specs = self._requirements.role_skill_specs(role_id, period)
        judgments = judge_skills(profile, specs)
        metrics = compute_metrics(judgments, specs)
        tier = decide_tier(metrics)
        gaps = analyze_gaps(profile, specs, self._bursts, role_id=role_id)
        missing_n = sum(1 for g in gaps if g.kind == GapKind.MISSING)
        insuff_n = sum(1 for g in gaps if g.kind == GapKind.INSUFFICIENT)
        better_fit: list[RoleRecommendation] = []
        if any(g.kind == GapKind.SURPLUS for g in gaps):
            better_fit = recommend_roles(
                profile,
                self._requirements,
                top_k=3,
                period=period,
                exclude_role_id=role_id,
            )
        return Diagnosis(
            profile_id=profile.id,
            role_id=role_id,
            tier=tier,
            coverage=metrics.weighted_coverage,
            score=ranking_score(metrics),
            gaps=gaps,
            judgments=judgments,
            rationale=template_rationale(tier, metrics, missing_n, insuff_n),
            better_fit_roles=better_fit,
        )

    async def diagnose(
        self,
        profile: SkillProfile,
        role_id: str,
        period: str | None = None,
    ) -> Diagnosis:
        diagnosis = self._build(profile, role_id, period)
        if self._llm is None:
            return diagnosis
        prompt = (
            "根据下列人岗匹配诊断，用中文写一段不超过 200 字的解释给求职者。"
            "档位已由规则判定，不要改口，只解释原因。\n"
            f"档位={diagnosis.tier} 覆盖率={diagnosis.coverage:.2f} "
            f"分值={diagnosis.score:.2f} 解释底稿={diagnosis.rationale}"
        )
        try:
            text = (await self._llm.complete_text(prompt, temperature=0.0)).strip()
        except Exception:
            return diagnosis
        if text:
            diagnosis.rationale = text
        return diagnosis

    async def learning_path(
        self,
        profile: SkillProfile,
        role_id: str,
        period: str | None = None,
    ) -> LearningPath:
        diagnosis = self._build(profile, role_id, period)
        levels = profile_levels(profile)
        spec_ids = {j.skill_id for j in diagnosis.judgments}
        satisfied = {j.skill_id for j in diagnosis.judgments if j.satisfied}
        # 画像中有、但不在岗位要求里的技能点，可作为前置已掌握
        for skill_id, level in levels.items():
            if skill_id not in spec_ids and level >= 1:
                satisfied.add(skill_id)
        path = plan_learning_path(
            profile_id=profile.id,
            role_id=role_id,
            gaps=diagnosis.gaps,
            prereq_source=self._prerequisites,
            satisfied=satisfied,
        )
        if self._attacher is None:
            return path
        for step in path.steps:
            name = self._requirements.skill_name(step.skill_id)
            step.resources = await self._attacher.attach(step.skill_id, name)
        return path

    def discover(
        self,
        profile: SkillProfile,
        *,
        top_k: int = 5,
        period: str | None = None,
    ) -> list[RoleRecommendation]:
        return recommend_roles(profile, self._requirements, top_k=top_k, period=period)


_service: MatchingService | None = None


def set_matching_service(service: MatchingService | None) -> None:
    global _service
    _service = service


def get_matching_service() -> MatchingService:
    if _service is None:
        raise MatchingNotConfiguredError
    return _service
