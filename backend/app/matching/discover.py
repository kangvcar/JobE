"""反向推荐：给定技能画像，按连续分值排出最匹配的岗位。"""

from __future__ import annotations

from app.domain.models import SkillProfile
from app.matching.protocols import RoleRequirementSource
from app.matching.tier import compute_metrics, decide_tier, judge_skills, ranking_score
from app.matching.types import RoleRecommendation


def recommend_roles(
    profile: SkillProfile,
    source: RoleRequirementSource,
    *,
    top_k: int = 5,
    period: str | None = None,
    exclude_role_id: str | None = None,
) -> list[RoleRecommendation]:
    """无技能要求的岗位不进入推荐，避免真空真把空岗位抬到高度匹配。"""
    ranked: list[RoleRecommendation] = []
    for role in source.list_published_roles():
        if exclude_role_id is not None and role.id == exclude_role_id:
            continue
        specs = source.role_skill_specs(role.id, period)
        if not specs:
            continue
        metrics = compute_metrics(judge_skills(profile, specs), specs)
        ranked.append(
            RoleRecommendation(
                role_id=role.id,
                role_name=role.name,
                tier=decide_tier(metrics),
                score=ranking_score(metrics),
                coverage=metrics.weighted_coverage,
            )
        )
    ranked.sort(key=lambda item: (-item.score, item.role_id))
    return ranked[: max(top_k, 0)]
