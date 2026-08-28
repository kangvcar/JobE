"""四档边界、技能级判定与连续分值。"""

from __future__ import annotations

from app.domain.models import GapKind, MatchTier, Necessity, ProfileSkill, SkillProfile
from app.matching.tier import (
    ADEQUATE_MIN_REQUIRED,
    GAPPED_MIN_REQUIRED,
    STRONG_MIN_REQUIRED,
    compute_metrics,
    decide_tier,
    judge_skills,
    ranking_score,
    template_rationale,
)

from .fakes import numbered_specs, profile_holding, spec


def _tier_of(specs, held_ids: list[str], *, level: int = 2) -> MatchTier:
    profile = profile_holding(held_ids, level=level)
    judgments = judge_skills(profile, specs)
    return decide_tier(compute_metrics(judgments, specs))


def test_strong_at_required_threshold():
    specs = numbered_specs(20)
    # 重要度并列时关键技能是 s00,s01,s02，必须持有
    held = [f"s{i:02d}" for i in range(17)]
    assert len(held) / 20 == STRONG_MIN_REQUIRED
    assert _tier_of(specs, held) is MatchTier.STRONG


def test_just_below_strong_required_is_adequate():
    specs = numbered_specs(20)
    held = [f"s{i:02d}" for i in range(16)]
    assert _tier_of(specs, held) is MatchTier.ADEQUATE


def test_adequate_at_required_threshold():
    specs = numbered_specs(20)
    held = [f"s{i:02d}" for i in range(12)]
    assert len(held) / 20 == ADEQUATE_MIN_REQUIRED
    assert _tier_of(specs, held) is MatchTier.ADEQUATE


def test_just_below_adequate_required_is_gapped():
    specs = numbered_specs(20)
    held = [f"s{i:02d}" for i in range(11)]
    assert _tier_of(specs, held) is MatchTier.GAPPED


def test_gapped_at_required_threshold():
    specs = numbered_specs(20)
    held = [f"s{i:02d}" for i in range(6)]
    assert len(held) / 20 == GAPPED_MIN_REQUIRED
    assert _tier_of(specs, held) is MatchTier.GAPPED


def test_just_below_gapped_is_mismatch():
    specs = numbered_specs(20)
    held = [f"s{i:02d}" for i in range(5)]
    assert _tier_of(specs, held) is MatchTier.MISMATCH


def test_strong_blocked_by_one_critical_missing():
    specs = numbered_specs(10)
    # 缺 s00（关键技能），仍持有 9/10
    held = [f"s{i:02d}" for i in range(1, 10)]
    assert _tier_of(specs, held) is MatchTier.ADEQUATE


def test_strong_holds_when_missing_is_not_critical():
    specs = numbered_specs(10)
    held = [f"s{i:02d}" for i in range(9)]  # 缺 s09
    assert _tier_of(specs, held) is MatchTier.STRONG


def test_adequate_blocked_by_two_critical_missing():
    specs = numbered_specs(10)
    held = [f"s{i:02d}" for i in range(2, 10)]  # 缺 s00,s01
    assert _tier_of(specs, held) is MatchTier.GAPPED


def test_weighted_coverage_just_below_strong():
    specs = [
        spec("s00", importance=8.0),
        spec("s01", importance=8.0),
        spec("s02", importance=8.0),
        spec("s03", importance=7.0),
        spec("s04", importance=7.0),
        spec("s05", importance=7.0),
        *[spec(f"s{i:02d}", importance=4.0) for i in range(6, 20)],
    ]
    held = ["s00", "s01", "s02", *[f"s{i:02d}" for i in range(6, 20)]]
    judgments = judge_skills(profile_holding(held), specs)
    metrics = compute_metrics(judgments, specs)
    assert metrics.required_coverage == STRONG_MIN_REQUIRED
    assert metrics.critical_missing == 0
    assert metrics.weighted_coverage < 0.80
    assert decide_tier(metrics) is MatchTier.ADEQUATE


def test_weighted_coverage_just_above_strong():
    specs = [
        spec("s00", importance=8.0),
        spec("s01", importance=8.0),
        spec("s02", importance=8.0),
        spec("s03", importance=6.0),
        spec("s04", importance=6.0),
        spec("s05", importance=6.0),
        *[spec(f"s{i:02d}", importance=4.0) for i in range(6, 20)],
    ]
    held = ["s00", "s01", "s02", *[f"s{i:02d}" for i in range(6, 20)]]
    assert _tier_of(specs, held) is MatchTier.STRONG


def test_skill_judgment_missing_insufficient_satisfied():
    specs = [
        spec("python", required_level=2),
        spec("torch", required_level=2),
        spec("sql", necessity=Necessity.BONUS, required_level=1),
    ]
    profile = SkillProfile(
        id="p1",
        skills=[
            ProfileSkill(skill_id="python", level=2),
            ProfileSkill(skill_id="torch", level=1),
        ],
    )
    judgments = {j.skill_id: j for j in judge_skills(profile, specs)}
    assert judgments["python"].satisfied is True
    assert judgments["python"].gap_kind is None
    assert judgments["torch"].satisfied is False
    assert judgments["torch"].gap_kind is GapKind.INSUFFICIENT
    assert judgments["sql"].gap_kind is GapKind.MISSING
    assert judgments["sql"].held_level == 0


def test_merge_duplicate_specs_required_wins():
    specs = [
        spec("python", importance=0.2, necessity=Necessity.BONUS, required_level=1),
        spec("python", importance=0.9, necessity=Necessity.REQUIRED, required_level=2),
    ]
    [j] = judge_skills(profile_holding(["python"], level=1), specs)
    assert j.necessity is Necessity.REQUIRED
    assert j.importance == 0.9
    assert j.required_level == 2
    assert j.gap_kind is GapKind.INSUFFICIENT


def test_duplicate_profile_skills_take_max_level():
    specs = [spec("python", required_level=2)]
    profile = SkillProfile(
        id="p1",
        skills=[
            ProfileSkill(skill_id="python", level=1),
            ProfileSkill(skill_id="python", level=3),
        ],
    )
    [j] = judge_skills(profile, specs)
    assert j.held_level == 3
    assert j.satisfied is True


def test_empty_specs_are_strong_with_full_coverage():
    metrics = compute_metrics(judge_skills(profile_holding(["x"]), []), [])
    assert metrics.required_coverage == 1.0
    assert metrics.weighted_coverage == 1.0
    assert decide_tier(metrics) is MatchTier.STRONG


def test_ranking_score_is_continuous_and_monotonic():
    specs = numbered_specs(10)
    scores = []
    for n in range(11):
        held = [f"s{i:02d}" for i in range(n)]
        metrics = compute_metrics(judge_skills(profile_holding(held), specs), specs)
        scores.append(ranking_score(metrics))
    assert all(0.0 <= s <= 1.0 for s in scores)
    assert scores == sorted(scores)
    assert len(set(scores)) == 11


def test_template_rationale_mentions_tier_label():
    specs = numbered_specs(20)
    held = [f"s{i:02d}" for i in range(17)]
    metrics = compute_metrics(judge_skills(profile_holding(held), specs), specs)
    text = template_rationale(MatchTier.STRONG, metrics, missing_n=3, insuff_n=0)
    assert "高度匹配" in text
    assert "必备技能覆盖率" in text
