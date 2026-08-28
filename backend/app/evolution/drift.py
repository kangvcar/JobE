"""既有岗位能力变更：相邻时间片技能重要度分布的 diff。

occurred_on 是业务发生时间（时间片起点），recorded_at 是记录时间（ADR 0005）。
跨本体版本的比较直接拒绝，否则会把编码变更当成能力变更。
"""

from __future__ import annotations

from datetime import date, datetime

from app.domain.models import ChangeKind, CompetencyChange, PublishState, SkillObservation
from app.evolution.periods import period_to_date, sorted_obs

# 相对变化超过 30% 视为 modified。低于此多为小样本计数抖动。
WEIGHT_CHANGE_RATIO = 0.30
# 重要度低于此视为「该时间片不存在」，避免 0.01→0.02 被当成新增。
ABS_WEIGHT_FLOOR = 0.05


def detect_competency_changes(
    role_id: str,
    before: list[SkillObservation],
    after: list[SkillObservation],
    *,
    recorded_at: datetime,
    occurred_on: date | None = None,
    evidence_by_skill: dict[str, list[str]] | None = None,
    competency_id_by_skill: dict[str, str] | None = None,
) -> list[CompetencyChange]:
    before_f = _filter_role(before, role_id)
    after_f = _filter_role(after, role_id)
    if not before_f or not after_f:
        return []
    versions = {o.ontology_version for o in before_f + after_f}
    if len(versions) != 1:
        return []
    before_w = _weights(before_f)
    after_w = _weights(after_f)
    after_period = sorted_obs(after_f)[-1].period
    when = occurred_on or period_to_date(after_period)
    evidence_by_skill = evidence_by_skill or {}
    competency_id_by_skill = competency_id_by_skill or {}
    changes: list[CompetencyChange] = []
    skills = set(before_w) | set(after_w)
    for skill_id in sorted(skills):
        w0 = before_w.get(skill_id, 0.0)
        w1 = after_w.get(skill_id, 0.0)
        present0 = w0 >= ABS_WEIGHT_FLOOR
        present1 = w1 >= ABS_WEIGHT_FLOOR
        if not present0 and present1:
            kind = ChangeKind.ADDED
            reason = (
                f"技能点 {skill_id} 在 {after_period} 首次达到显著重要度 "
                f"（{w1:.2f}），上一时间片不存在或低于噪声地板 {ABS_WEIGHT_FLOOR}"
            )
            before_txt, after_txt = None, f"{w1:.4f}"
        elif present0 and not present1:
            kind = ChangeKind.REMOVED
            reason = (
                f"技能点 {skill_id} 在 {after_period} 从岗位能力要求中消失（此前重要度 {w0:.2f}）"
            )
            before_txt, after_txt = f"{w0:.4f}", None
        elif present0 and present1 and _relative_change(w0, w1) >= WEIGHT_CHANGE_RATIO:
            kind = ChangeKind.MODIFIED
            pct = _relative_change(w0, w1)
            reason = f"技能点 {skill_id} 重要度由 {w0:.2f} 变为 {w1:.2f}（相对变化 {pct:.0%}）"
            before_txt, after_txt = f"{w0:.4f}", f"{w1:.4f}"
        else:
            continue
        evidence_ids = evidence_by_skill.get(skill_id, [])
        changes.append(
            CompetencyChange(
                id=f"chg-{role_id}-{skill_id}-{kind}-{after_period}",
                role_id=role_id,
                competency_id=competency_id_by_skill.get(skill_id, skill_id),
                kind=kind,
                before=before_txt,
                after=after_txt,
                reason=reason,
                evidence_ids=evidence_ids,
                occurred_on=when,
                recorded_at=recorded_at,
                state=PublishState.UNVERIFIED,
            )
        )
    return changes


def _filter_role(series: list[SkillObservation], role_id: str) -> list[SkillObservation]:
    matched = [o for o in series if o.role_id == role_id]
    return matched if matched else list(series)


def _weights(series: list[SkillObservation]) -> dict[str, float]:
    out: dict[str, float] = {}
    for obs in series:
        out[obs.skill_id] = obs.weight
    return out


def _relative_change(w0: float, w1: float) -> float:
    denom = max(abs(w0), 1e-9)
    return abs(w1 - w0) / denom
