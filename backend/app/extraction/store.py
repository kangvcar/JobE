"""抽取层内存仓储。PG 实现就位后替换本模块，方法签名保持不变。"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol

from app.domain.models import Evidence, PublishState, SkillProfile, TextSpan
from app.extraction.layout import CharIndex, ParsedDocument


def utcnow() -> datetime:
    return datetime.now(UTC)


def new_id() -> str:
    return uuid.uuid4().hex


@dataclass
class DocumentRecord:
    id: str
    kind: str
    canonical_text: str
    char_index: CharIndex


@dataclass
class ClaimRecord:
    id: str
    kind: str
    text: str
    evidence_ids: list[str]
    state: PublishState = PublishState.UNVERIFIED
    payload: dict[str, Any] = field(default_factory=dict)
    doc_id: str | None = None


@dataclass
class AliasDecision:
    surface_form: str
    skill_id: str | None
    decided_by: str
    confidence: float
    decided_at: datetime = field(default_factory=utcnow)


class DocumentStore(Protocol):
    def save(self, doc: DocumentRecord) -> str: ...

    def get(self, doc_id: str) -> DocumentRecord | None: ...


class AliasDecisionStore(Protocol):
    def get(self, surface_form: str) -> AliasDecision | None: ...

    def put(self, decision: AliasDecision) -> None: ...


class MemoryExtractionStore:
    """文档 / 证据 / 待确认 / 别名裁决 / 技能画像。"""

    def __init__(self) -> None:
        self.documents: dict[str, DocumentRecord] = {}
        self.evidence: dict[str, Evidence] = {}
        self.claims: dict[str, ClaimRecord] = {}
        self.aliases: dict[str, AliasDecision] = {}
        self.profiles: dict[str, SkillProfile] = {}

    def save(self, doc: DocumentRecord) -> str:
        self.documents[doc.id] = doc
        return doc.id

    def get(self, doc_id: str) -> DocumentRecord | None:
        return self.documents.get(doc_id)

    def save_parsed(
        self, parsed: ParsedDocument, *, kind: str, doc_id: str | None = None
    ) -> DocumentRecord:
        rec = DocumentRecord(
            id=doc_id or new_id(),
            kind=kind,
            canonical_text=parsed.canonical_text,
            char_index=parsed.char_index,
        )
        self.save(rec)
        return rec

    def save_plain(self, text: str, *, kind: str, doc_id: str | None = None) -> DocumentRecord:
        from app.extraction.layout import parse_plain_text

        return self.save_parsed(parse_plain_text(text), kind=kind, doc_id=doc_id)

    def save_evidence(self, evidence: Evidence) -> str:
        self.evidence[evidence.id] = evidence
        return evidence.id

    def get_many(self, ids: list[str]) -> list[Evidence]:
        return [self.evidence[i] for i in ids if i in self.evidence]

    def put_claim(self, claim: ClaimRecord) -> str:
        self.claims[claim.id] = claim
        return claim.id

    def unverified(self) -> list[ClaimRecord]:
        return [c for c in self.claims.values() if c.state == PublishState.UNVERIFIED]

    def decide(
        self, claim_id: str, state: PublishState, *, payload: dict | None = None
    ) -> ClaimRecord:
        claim = self.claims[claim_id]
        claim.state = state
        if payload:
            claim.payload.update(payload)
        return claim

    def get_alias(self, surface_form: str) -> AliasDecision | None:
        return self.aliases.get(_alias_key(surface_form))

    def put_alias(self, decision: AliasDecision) -> None:
        self.aliases[_alias_key(decision.surface_form)] = decision

    def save_profile(self, profile: SkillProfile) -> str:
        self.profiles[profile.id] = profile
        return profile.id


def _alias_key(surface: str) -> str:
    return surface.strip()


def make_evidence(
    *,
    source_id: str,
    span: TextSpan,
    quote: str,
    extractor: str,
    confidence: float,
    posting_id: str | None = None,
) -> Evidence:
    return Evidence(
        id=new_id(),
        source_id=source_id,
        span=span,
        quote=quote,
        fetched_at=utcnow(),
        extractor=extractor,
        confidence=confidence,
        posting_id=posting_id,
    )
