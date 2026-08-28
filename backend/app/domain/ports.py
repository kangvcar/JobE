"""跨模块的行为契约。

并行开发的模块之间只通过这些协议交互，不直接互相 import 实现。
新增协议前先问一遍：真的有第二个实现吗？没有就别抽象。
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date
from typing import Protocol

from app.domain.models import (
    Competency,
    CompetencyChange,
    Evidence,
    LeadLag,
    Posting,
    ReviewOutcome,
    Role,
    Skill,
    SkillObservation,
    Snapshot,
    TextSpan,
)


class Collector(Protocol):
    """一个来源的采集适配器。只负责产出快照，不做任何解析。"""

    source_id: str

    def collect(self, since: date | None = None) -> Iterable[Snapshot]: ...


class SnapshotStore(Protocol):
    def save(self, snapshot: Snapshot) -> str: ...

    def exists(self, content_hash: str) -> bool: ...

    def iter_by_source(self, source_id: str) -> Iterable[Snapshot]: ...


class PostingStore(Protocol):
    def upsert(self, posting: Posting) -> str: ...

    def iter_for_period(self, period: str) -> Iterable[Posting]: ...

    def count_for_period(self, period: str) -> int: ...


class EvidenceStore(Protocol):
    def save(self, evidence: Evidence) -> str: ...

    def get_many(self, ids: list[str]) -> list[Evidence]: ...


class LLMClient(Protocol):
    """语义判断。不得用于产出位置坐标（见 ADR 0003）。"""

    async def complete_json(
        self, prompt: str, schema: dict, *, temperature: float = 0.0
    ) -> dict: ...

    async def complete_text(self, prompt: str, *, temperature: float = 0.0) -> str: ...


class Reviewer(Protocol):
    """AI 审核员：只判断结论是否被证据支持，不产生新结论。"""

    async def review(self, claim: str, evidence: list[Evidence]) -> ReviewOutcome: ...


class SpanLocator(Protocol):
    """把一段文本在文档中定位成字符区间与版面坐标。匹配不上必须返回 None。"""

    def locate(self, doc_id: str, quote: str, hint_start: int | None = None) -> TextSpan | None: ...


class GraphRepository(Protocol):
    def upsert_role(self, role: Role) -> str: ...

    def upsert_skill(self, skill: Skill) -> str: ...

    def upsert_competency(self, competency: Competency) -> str: ...

    def record_change(self, change: CompetencyChange) -> str: ...

    def put_observation(self, observation: SkillObservation) -> None: ...

    def get_role(self, role_id: str) -> Role | None: ...

    def role_skills(self, role_id: str, period: str | None = None) -> list[SkillObservation]: ...

    def snapshot_at(self, period: str) -> dict: ...

    def diff(self, period_a: str, period_b: str) -> list[CompetencyChange]: ...


class BurstDetector(Protocol):
    def detect(self, series: list[SkillObservation]) -> list: ...


class LeadLagAnalyzer(Protocol):
    def analyze(
        self, leading: list[SkillObservation], lagging: list[SkillObservation]
    ) -> LeadLag | None: ...
