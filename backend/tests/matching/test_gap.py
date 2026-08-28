"""三类差距识别与紧迫度。"""

from __future__ import annotations

import pytest

from app.domain.models import GapKind, Necessity, ProfileSkill, SkillProfile
from app.matching.gap import analyze_gaps, compute_urgency, deficit

from .fakes import FakeBursts, profile_holding, spec


def test_identifies_missing_insufficient_surplus():
    specs = [
        spec("python", required_level=2, importance=0.8),
        spec("torch", required_level=2, importance=0.9),
        spec("k8s", necessity=Necessity.BONUS, required_level=1, importance=0.2),
    ]
    profile = SkillProfile(
        id="p1",
        skills=[
            ProfileSkill(skill_id="python", level=1),
            ProfileSkill(skill_id="excel", level=3),
        ],
    )
    gaps = {g.skill_id: g for g in analyze_gaps(profile, specs, FakeBursts())}
    assert gaps["torch"].kind is GapKind.MISSING
    assert gaps["python"].kind is GapKind.INSUFFICIENT
    assert gaps["k8s"].kind is GapKind.MISSING
    assert gaps["excel"].kind is GapKind.SURPLUS
    assert "python" in gaps and gaps["python"].held_level == 1


def test_satisfied_skill_is_not_a_gap():
    specs = [spec("python", required_level=2)]
    gaps = analyze_gaps(profile_holding(["python"], level=2), specs, FakeBursts())
    assert gaps == []


def test_missing_deficit_is_one():
    assert deficit(GapKind.MISSING, held_level=0, required_level=2) == 1.0


def test_insufficient_deficit_is_proportional():
    assert deficit(GapKind.INSUFFICIENT, held_level=1, required_level=2) == 0.5
    assert deficit(GapKind.INSUFFICIENT, held_level=0, required_level=3) == 1.0


def test_surplus_deficit_is_zero():
    assert deficit(GapKind.SURPLUS, held_level=3, required_level=0) == 0.0


def test_urgency_multiplies_importance_deficit_and_burst():
    # 0.8 * 1.0 * (1 + 0.5) = 1.2
    assert compute_urgency(
        importance=0.8,
        kind=GapKind.MISSING,
        held_level=0,
        required_level=2,
        burst_weight=0.5,
    ) == pytest.approx(1.2)


def test_urgency_without_burst_keeps_baseline():
    # 0.6 * 0.5 * 1.0 = 0.3
    assert (
        compute_urgency(
            importance=0.6,
            kind=GapKind.INSUFFICIENT,
            held_level=1,
            required_level=2,
            burst_weight=0.0,
        )
        == 0.3
    )


def test_surplus_urgency_is_zero_even_with_burst():
    assert (
        compute_urgency(
            importance=1.0,
            kind=GapKind.SURPLUS,
            held_level=3,
            required_level=0,
            burst_weight=2.0,
        )
        == 0.0
    )


def test_analyze_gaps_uses_burst_source():
    specs = [spec("torch", importance=0.5, required_level=2)]
    gaps = analyze_gaps(profile_holding([]), specs, FakeBursts({"torch": 1.0}))
    assert len(gaps) == 1
    assert gaps[0].urgency == 0.5 * 1.0 * 2.0


def test_negative_burst_is_floored():
    assert (
        compute_urgency(
            importance=1.0,
            kind=GapKind.MISSING,
            held_level=0,
            required_level=1,
            burst_weight=-0.3,
        )
        == 1.0
    )
