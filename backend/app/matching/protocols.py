"""本模块对上游的最小读取协议。

ports.py 里的 GraphRepository / BurstDetector 尚不足以支撑诊断
（缺必备/加分、要求水平、PREREQUISITE_OF、突增按技能点查询），
因此在这里补协议。实现方见交付报告中的签名清单；测试用 fixture 顶上。
不要 import app.graph 或 app.evolution 的实现。
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Protocol

from app.domain.models import Resource, Role
from app.matching.types import RoleSkillSpec


class RoleRequirementSource(Protocol):
    """岗位技能要求与岗位目录。由图谱仓储适配。"""

    def get_role(self, role_id: str) -> Role | None: ...

    def role_skill_specs(self, role_id: str, period: str | None = None) -> list[RoleSkillSpec]: ...

    def list_published_roles(self) -> list[Role]: ...

    def skill_name(self, skill_id: str) -> str: ...


class PrerequisiteSource(Protocol):
    """技能点前置依赖。对应图中 (:Skill)-[:PREREQUISITE_OF]->(:Skill) 的反向查询。

    返回 {skill_id: [前置技能点 id, ...]}，只需要被询问的那些键。
    """

    def prerequisites_of(self, skill_ids: Iterable[str]) -> dict[str, list[str]]: ...


class BurstSource(Protocol):
    """技能点突增趋势。由演化模块适配。无突增时返回 0。"""

    def burst_weight(self, skill_id: str, *, role_id: str | None = None) -> float: ...


class ResourceCache(Protocol):
    """按技能点缓存已核验的学习资源。未命中返回 None。"""

    def get(self, skill_id: str) -> list[Resource] | None: ...

    def put(self, skill_id: str, resources: list[Resource]) -> None: ...


class ResourceCatalog(Protocol):
    """公开检索的候选资源。不要自建课程库；URL 必须来自检索结果。"""

    def candidates(self, skill_id: str, skill_name: str) -> list[ResourceCandidate]: ...


class LinkChecker(Protocol):
    """URL 可达性。实现侧用 HEAD，单元测试打桩，禁止真实联网。"""

    def is_reachable(self, url: str) -> bool: ...


@dataclass(frozen=True, slots=True)
class ResourceCandidate:
    """检索命中的一条候选。LLM 只能从中挑选，不得发明 URL。"""

    title: str
    url: str
    kind: str
    source: str
