"""差距分析。三类差距的识别与紧迫度计算。

urgency = 重要度 × 缺失程度 × (1 + 突增权重)
无突增时乘数为 1，避免把重要缺口的紧迫度打成 0。
"""

from __future__ import annotations

from app.domain.models import Gap, GapKind, SkillProfile
from app.matching.protocols import BurstSource
from app.matching.tier import merge_specs, profile_levels
from app.matching.types import RoleSkillSpec

# 突增乘数的基线。burst_weight=0 时 urgency 退化为 重要度 × 缺失程度
BURST_BASELINE = 1.0


def deficit(kind: GapKind, held_level: int, required_level: int) -> float:
    """缺失程度，取值 [0, 1]。冗余对学习无紧迫度。"""
    if kind == GapKind.MISSING:
        return 1.0
    if kind == GapKind.SURPLUS:
        return 0.0
    if required_level <= 0:
        return 0.0
    drop = required_level - held_level
    if drop <= 0:
        return 0.0
    return min(drop / required_level, 1.0)


def compute_urgency(
    *,
    importance: float,
    kind: GapKind,
    held_level: int,
    required_level: int,
    burst_weight: float,
) -> float:
    burst = max(burst_weight, 0.0)
    value = importance * deficit(kind, held_level, required_level) * (BURST_BASELINE + burst)
    return max(value, 0.0)


def analyze_gaps(
    profile: SkillProfile,
    specs: list[RoleSkillSpec],
    bursts: BurstSource,
    *,
    role_id: str | None = None,
) -> list[Gap]:
    """产出缺失 / 不足 / 冗余。技能级判定的差集视角。"""
    specs = merge_specs(specs)
    levels = profile_levels(profile)
    spec_ids = {s.skill_id for s in specs}
    gaps: list[Gap] = []

    for spec in specs:
        held = levels.get(spec.skill_id, 0)
        present = spec.skill_id in levels
        if present and held >= spec.required_level:
            continue
        kind = GapKind.MISSING if not present else GapKind.INSUFFICIENT
        burst = bursts.burst_weight(spec.skill_id, role_id=role_id)
        gaps.append(
            Gap(
                skill_id=spec.skill_id,
                kind=kind,
                required_importance=spec.importance,
                held_level=held,
                urgency=compute_urgency(
                    importance=spec.importance,
                    kind=kind,
                    held_level=held,
                    required_level=spec.required_level,
                    burst_weight=burst,
                ),
            )
        )

    for skill_id, held in levels.items():
        if skill_id in spec_ids:
            continue
        gaps.append(
            Gap(
                skill_id=skill_id,
                kind=GapKind.SURPLUS,
                required_importance=0.0,
                held_level=held,
                urgency=0.0,
            )
        )

    return gaps
