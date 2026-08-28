"""测试替身与工厂。不连库、不联网、不调真实大模型。"""

from __future__ import annotations

from app.domain.models import Necessity, ProfileSkill, Role, SkillProfile
from app.matching.protocols import ResourceCandidate
from app.matching.types import RoleSkillSpec


def spec(
    skill_id: str,
    *,
    importance: float = 1.0,
    necessity: Necessity = Necessity.REQUIRED,
    required_level: int = 1,
) -> RoleSkillSpec:
    return RoleSkillSpec(
        skill_id=skill_id,
        necessity=necessity,
        importance=importance,
        required_level=required_level,
    )


def numbered_specs(
    n: int,
    *,
    importance: float = 1.0,
    necessity: Necessity = Necessity.REQUIRED,
    required_level: int = 1,
) -> list[RoleSkillSpec]:
    return [
        spec(f"s{i:02d}", importance=importance, necessity=necessity, required_level=required_level)
        for i in range(n)
    ]


def profile_holding(
    skill_ids: list[str], *, level: int = 2, profile_id: str = "p1"
) -> SkillProfile:
    return SkillProfile(
        id=profile_id,
        skills=[ProfileSkill(skill_id=sid, level=level) for sid in skill_ids],
    )


class FakeRequirements:
    def __init__(
        self,
        roles: dict[str, Role] | None = None,
        specs: dict[str, list[RoleSkillSpec]] | None = None,
        names: dict[str, str] | None = None,
    ) -> None:
        self.roles = roles or {}
        self.specs = specs or {}
        self.names = names or {}

    def get_role(self, role_id: str) -> Role | None:
        return self.roles.get(role_id)

    def role_skill_specs(self, role_id: str, period: str | None = None) -> list[RoleSkillSpec]:
        del period
        return list(self.specs.get(role_id, []))

    def list_published_roles(self) -> list[Role]:
        return list(self.roles.values())

    def skill_name(self, skill_id: str) -> str:
        return self.names.get(skill_id, skill_id)


class FakePrereqs:
    def __init__(self, edges: dict[str, list[str]] | None = None) -> None:
        self.edges = edges or {}

    def prerequisites_of(self, skill_ids) -> dict[str, list[str]]:
        return {s: list(self.edges.get(s, [])) for s in skill_ids}


class FakeBursts:
    def __init__(self, weights: dict[str, float] | None = None) -> None:
        self.weights = weights or {}

    def burst_weight(self, skill_id: str, *, role_id: str | None = None) -> float:
        del role_id
        return self.weights.get(skill_id, 0.0)


class FakeCatalog:
    def __init__(self, mapping: dict[str, list[ResourceCandidate]] | None = None) -> None:
        self.mapping = mapping or {}
        self.calls: list[str] = []

    def candidates(self, skill_id: str, skill_name: str) -> list[ResourceCandidate]:
        del skill_name
        self.calls.append(skill_id)
        return list(self.mapping.get(skill_id, []))


class FakeChecker:
    def __init__(self, dead: set[str] | None = None) -> None:
        self.dead = dead or set()
        self.checked: list[str] = []

    def is_reachable(self, url: str) -> bool:
        self.checked.append(url)
        return url not in self.dead


class FakeLLM:
    def __init__(
        self,
        json_payload: dict | None = None,
        text: str = "",
        json_error: Exception | None = None,
        text_error: Exception | None = None,
    ) -> None:
        self.json_payload = json_payload or {"picks": []}
        self.text = text
        self.json_error = json_error
        self.text_error = text_error
        self.json_calls = 0
        self.text_calls = 0

    async def complete_json(self, prompt: str, schema: dict, *, temperature: float = 0.0) -> dict:
        del prompt, schema, temperature
        self.json_calls += 1
        if self.json_error is not None:
            raise self.json_error
        return self.json_payload

    async def complete_text(self, prompt: str, *, temperature: float = 0.0) -> str:
        del prompt, temperature
        self.text_calls += 1
        if self.text_error is not None:
            raise self.text_error
        return self.text
