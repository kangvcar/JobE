"""匹配档位判定。纯规则，确定性可复算；大模型不得调用本模块来"决定"档位。"""

from __future__ import annotations

from dataclasses import dataclass

from app.domain.models import GapKind, MatchTier, Necessity, SkillProfile
from app.matching.types import RoleSkillSpec, SkillJudgment

# ---------------------------------------------------------------------------
# 档位阈值。判定从高到低命中即停。覆盖率均为 [0, 1]。
# 取值依据：把"专家能一眼区分的四档"对齐到可复算的覆盖率切分，
# 并单独卡住关键技能，避免"总体覆盖高但核心技能全缺"被抬到高度匹配。
# ---------------------------------------------------------------------------

# 关键技能：按重要度取前 N 个（并列时 skill_id 升序，保证可复算）
CRITICAL_TOP_N = 3

# 高度匹配：必备几乎齐、加权覆盖高、关键技能一条都不能缺
STRONG_MIN_REQUIRED = 0.85  # 必备技能满足比例下限
STRONG_MIN_WEIGHTED = 0.80  # 按重要度加权覆盖下限
STRONG_MAX_CRITICAL_MISSING = 0  # 允许缺失的关键技能条数

# 基本匹配：主体能力具备，允许 1 条关键技能缺口
ADEQUATE_MIN_REQUIRED = 0.60
ADEQUATE_MIN_WEIGHTED = 0.50
ADEQUATE_MAX_CRITICAL_MISSING = 1

# 有明显差距：仍有可识别重叠；两线同时低于此则判不匹配
# 使用 OR：必备或加权任一达到 30%，说明不是完全对不上
GAPPED_MIN_REQUIRED = 0.30
GAPPED_MIN_WEIGHTED = 0.30

# 反向推荐用的连续分值权重。和必须加总为 1，输出在 [0, 1]
SCORE_REQUIRED_WEIGHT = 0.50
SCORE_PARTIAL_WEIGHT = 0.40
SCORE_CRITICAL_WEIGHT = 0.10


@dataclass(frozen=True)
class CoverageMetrics:
    required_total: int
    required_satisfied: int
    bonus_total: int
    bonus_satisfied: int
    required_coverage: float
    bonus_coverage: float
    weighted_coverage: float
    partial_weighted: float
    critical_ids: tuple[str, ...]
    critical_missing: int


def profile_levels(profile: SkillProfile) -> dict[str, int]:
    """同一技能点多次出现时取最高水平。"""
    levels: dict[str, int] = {}
    for item in profile.skills:
        levels[item.skill_id] = max(levels.get(item.skill_id, 0), item.level)
    return levels


def merge_specs(specs: list[RoleSkillSpec]) -> list[RoleSkillSpec]:
    """同一技能点多条要求：必备优先，重要度与要求水平取 max。保序。"""
    merged: dict[str, RoleSkillSpec] = {}
    for spec in specs:
        existing = merged.get(spec.skill_id)
        if existing is None:
            merged[spec.skill_id] = spec
            continue
        necessity = (
            Necessity.REQUIRED
            if Necessity.REQUIRED in (existing.necessity, spec.necessity)
            else Necessity.BONUS
        )
        merged[spec.skill_id] = RoleSkillSpec(
            skill_id=spec.skill_id,
            necessity=necessity,
            importance=max(existing.importance, spec.importance),
            required_level=max(existing.required_level, spec.required_level),
        )
    return list(merged.values())


def _ratio(numerator: int, denominator: int) -> float:
    """无条目时视为全覆盖（空岗位要求的真空真）。"""
    if denominator == 0:
        return 1.0
    return numerator / denominator


def _level_ratio(held: int, required: int) -> float:
    if required <= 0:
        return 1.0
    return min(held / required, 1.0)


def judge_skills(profile: SkillProfile, specs: list[RoleSkillSpec]) -> list[SkillJudgment]:
    """对岗位要求的每一条技能点做原子判定。"""
    levels = profile_levels(profile)
    judgments: list[SkillJudgment] = []
    for spec in merge_specs(specs):
        held = levels.get(spec.skill_id, 0)
        present = spec.skill_id in levels
        satisfied = held >= spec.required_level
        gap_kind: GapKind | None
        if satisfied:
            gap_kind = None
        elif not present:
            gap_kind = GapKind.MISSING
        else:
            gap_kind = GapKind.INSUFFICIENT
        judgments.append(
            SkillJudgment(
                skill_id=spec.skill_id,
                necessity=spec.necessity,
                importance=spec.importance,
                required_level=spec.required_level,
                held_level=held,
                satisfied=satisfied,
                gap_kind=gap_kind,
            )
        )
    return judgments


def critical_skill_ids(specs: list[RoleSkillSpec], n: int = CRITICAL_TOP_N) -> tuple[str, ...]:
    ranked = sorted(merge_specs(specs), key=lambda s: (-s.importance, s.skill_id))
    return tuple(s.skill_id for s in ranked[:n])


def compute_metrics(judgments: list[SkillJudgment], specs: list[RoleSkillSpec]) -> CoverageMetrics:
    required = [j for j in judgments if j.necessity == Necessity.REQUIRED]
    bonus = [j for j in judgments if j.necessity == Necessity.BONUS]
    required_ok = sum(1 for j in required if j.satisfied)
    bonus_ok = sum(1 for j in bonus if j.satisfied)

    total_importance = sum(j.importance for j in judgments)
    if total_importance > 0:
        weighted = sum(j.importance for j in judgments if j.satisfied) / total_importance
        partial = (
            sum(j.importance * _level_ratio(j.held_level, j.required_level) for j in judgments)
            / total_importance
        )
    else:
        weighted = 1.0
        partial = 1.0

    crit_ids = critical_skill_ids(specs)
    by_id = {j.skill_id: j for j in judgments}
    # "缺失"按术语：画像完全没有，不含水平不足
    crit_missing = sum(
        1 for sid in crit_ids if by_id.get(sid) is not None and by_id[sid].held_level == 0
    )

    return CoverageMetrics(
        required_total=len(required),
        required_satisfied=required_ok,
        bonus_total=len(bonus),
        bonus_satisfied=bonus_ok,
        required_coverage=_ratio(required_ok, len(required)),
        bonus_coverage=_ratio(bonus_ok, len(bonus)),
        weighted_coverage=weighted,
        partial_weighted=partial,
        critical_ids=crit_ids,
        critical_missing=crit_missing,
    )


def decide_tier(metrics: CoverageMetrics) -> MatchTier:
    """规则打分。不要把本函数的输入交给大模型来改档。"""
    if (
        metrics.required_coverage >= STRONG_MIN_REQUIRED
        and metrics.weighted_coverage >= STRONG_MIN_WEIGHTED
        and metrics.critical_missing <= STRONG_MAX_CRITICAL_MISSING
    ):
        return MatchTier.STRONG
    if (
        metrics.required_coverage >= ADEQUATE_MIN_REQUIRED
        and metrics.weighted_coverage >= ADEQUATE_MIN_WEIGHTED
        and metrics.critical_missing <= ADEQUATE_MAX_CRITICAL_MISSING
    ):
        return MatchTier.ADEQUATE
    if (
        metrics.required_coverage >= GAPPED_MIN_REQUIRED
        or metrics.weighted_coverage >= GAPPED_MIN_WEIGHTED
    ):
        return MatchTier.GAPPED
    return MatchTier.MISMATCH


def ranking_score(metrics: CoverageMetrics) -> float:
    """连续分值，供反向推荐排序与 NDCG@5 / Spearman。"""
    denom = max(len(metrics.critical_ids), 1)
    critical_ok = 1.0 - metrics.critical_missing / denom
    return (
        SCORE_REQUIRED_WEIGHT * metrics.required_coverage
        + SCORE_PARTIAL_WEIGHT * metrics.partial_weighted
        + SCORE_CRITICAL_WEIGHT * critical_ok
    )


_TIER_LABEL = {
    MatchTier.STRONG: "高度匹配",
    MatchTier.ADEQUATE: "基本匹配",
    MatchTier.GAPPED: "有明显差距",
    MatchTier.MISMATCH: "不匹配",
}


def template_rationale(
    tier: MatchTier, metrics: CoverageMetrics, missing_n: int, insuff_n: int
) -> str:
    """确定性解释。大模型不可用时的兜底，也是档位可复算的旁证。"""
    parts = [
        f"判定为「{_TIER_LABEL[tier]}」。",
        f"必备技能覆盖率 {metrics.required_coverage:.0%}，",
        f"加权覆盖率 {metrics.weighted_coverage:.0%}。",
    ]
    if metrics.critical_missing:
        parts.append(f"关键技能缺失 {metrics.critical_missing} 项。")
    if missing_n:
        parts.append(f"完全缺失 {missing_n} 项。")
    if insuff_n:
        parts.append(f"水平不足 {insuff_n} 项。")
    return "".join(parts)
