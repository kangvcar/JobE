"""服务门面：诊断含技能级判定、LLM 只写 rationale、路径挂资源。"""

from __future__ import annotations

import pytest

from app.domain.models import GapKind, MatchTier, ProfileSkill, Role, SkillProfile
from app.matching.protocols import ResourceCandidate
from app.matching.resources import InMemoryResourceCache, ResourceAttacher
from app.matching.service import MatchingService, RoleNotFoundError

from .fakes import (
    FakeBursts,
    FakeCatalog,
    FakeChecker,
    FakeLLM,
    FakePrereqs,
    FakeRequirements,
    numbered_specs,
    profile_holding,
    spec,
)


def _svc(**kwargs) -> MatchingService:
    roles = kwargs.pop("roles", {"r1": Role(id="r1", name="机器学习工程师")})
    specs = kwargs.pop("specs", {"r1": numbered_specs(10)})
    prereqs = kwargs.pop("prereqs", FakePrereqs())
    bursts = kwargs.pop("bursts", FakeBursts())
    return MatchingService(
        FakeRequirements(roles=roles, specs=specs),
        prereqs,
        bursts,
        **kwargs,
    )


async def test_diagnose_includes_judgments_and_does_not_call_llm_for_tier():
    llm = FakeLLM(text="大模型写的解释")
    svc = _svc(llm=llm)
    held = [f"s{i:02d}" for i in range(9)]
    diagnosis = await svc.diagnose(profile_holding(held), "r1")
    assert diagnosis.tier is MatchTier.STRONG
    assert len(diagnosis.judgments) == 10
    assert diagnosis.judgments[-1].gap_kind is GapKind.MISSING
    assert diagnosis.to_match_result().tier is MatchTier.STRONG
    assert llm.text_calls == 1
    assert llm.json_calls == 0
    assert diagnosis.rationale == "大模型写的解释"


async def test_diagnose_falls_back_when_llm_fails():
    svc = _svc(llm=FakeLLM(text_error=RuntimeError("down")))
    diagnosis = await svc.diagnose(profile_holding([f"s{i:02d}" for i in range(9)]), "r1")
    assert "高度匹配" in diagnosis.rationale


async def test_unknown_role_raises():
    svc = _svc()
    with pytest.raises(RoleNotFoundError):
        await svc.diagnose(profile_holding([]), "nope")


async def test_surplus_fills_better_fit_roles():
    roles = {
        "ml": Role(id="ml", name="机器学习"),
        "data": Role(id="data", name="数据工程"),
    }
    specs = {
        "ml": [spec("python"), spec("torch")],
        "data": [spec("python"), spec("sql")],
    }
    svc = _svc(roles=roles, specs=specs)
    profile = SkillProfile(
        id="p1",
        skills=[
            ProfileSkill(skill_id="python", level=2),
            ProfileSkill(skill_id="sql", level=2),
        ],
    )
    diagnosis = await svc.diagnose(profile, "ml")
    assert any(g.kind is GapKind.SURPLUS and g.skill_id == "sql" for g in diagnosis.gaps)
    assert diagnosis.better_fit_roles[0].role_id == "data"


async def test_learning_path_attaches_resources():
    live = ResourceCandidate(
        title="PyTorch 文档",
        url="https://pytorch.example/docs",
        kind="docs",
        source="pytorch.org",
    )
    attacher = ResourceAttacher(
        InMemoryResourceCache(),
        FakeCatalog({"s09": [live]}),
        FakeChecker(),
    )
    svc = _svc(attacher=attacher)
    path = await svc.learning_path(profile_holding([f"s{i:02d}" for i in range(9)]), "r1")
    assert path.steps[0].skill_id == "s09"
    assert path.steps[0].resources[0].url == live.url


def test_discover_delegates():
    svc = _svc()
    items = svc.discover(profile_holding([f"s{i:02d}" for i in range(10)]), top_k=1)
    assert items[0].role_id == "r1"
    assert items[0].tier is MatchTier.STRONG
