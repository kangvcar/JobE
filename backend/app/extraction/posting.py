"""从职位描述抽取能力项与技能点。位置一律回定位，失败即丢弃。"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from app.domain.models import Competency, Evidence, Necessity, Posting, PublishState, TextSpan
from app.domain.ports import LLMClient, SpanLocator
from app.extraction.reviewer import grade_evidence
from app.extraction.store import (
    ClaimRecord,
    MemoryExtractionStore,
    make_evidence,
    new_id,
)

logger = logging.getLogger("jobe.extraction.posting")

EXTRACTOR = "posting-llm"

_REQUIRED_MARKERS = ("要求", "必须", "必备", "精通")
_BONUS_MARKERS = ("加分", "优先", "了解")

POSTING_SCHEMA = {
    "type": "object",
    "properties": {
        "competencies": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "statement": {"type": "string"},
                    "quote": {
                        "type": "string",
                        "description": "原文中的精确子串，一个字符都不能改",
                    },
                    "necessity": {"type": "string", "enum": ["required", "bonus"]},
                },
                "required": ["statement", "quote"],
            },
        },
        "skills": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "surface_form": {"type": "string"},
                    "quote": {"type": "string"},
                    "necessity": {"type": "string", "enum": ["required", "bonus"]},
                },
                "required": ["surface_form", "quote"],
            },
        },
    },
    "required": ["competencies", "skills"],
}


@dataclass
class ExtractedSkill:
    surface_form: str
    necessity: Necessity
    evidence: Evidence


@dataclass
class ExtractedPosting:
    competencies: list[Competency] = field(default_factory=list)
    skills: list[ExtractedSkill] = field(default_factory=list)
    evidence: list[Evidence] = field(default_factory=list)
    discarded: int = 0


def overlaps_boilerplate(span: TextSpan, ranges: list[tuple[int, int]]) -> bool:
    for a, b in ranges:
        if span.start < b and span.end > a:
            return True
    return False


def mask_boilerplate(text: str, ranges: list[tuple[int, int]]) -> str:
    if not ranges:
        return text
    chars = list(text)
    n = len(chars)
    for a, b in ranges:
        for i in range(max(0, a), min(n, b)):
            chars[i] = " "
    return "".join(chars)


def infer_necessity(quote: str, full_text: str) -> Necessity | None:
    """规则优先：要求/必须/精通→必备，加分/优先/了解→加分。无法判断返回 None 交给 LLM。

    看 quote 之前最近的标记，避免「要求…加分…」整段窗口把前面的必备项判成加分。
    """
    idx = full_text.find(quote) if quote else -1
    if idx < 0:
        idx = 0
    prefix = full_text[max(0, idx - 160) : idx + len(quote)]
    bonus_at = _last_marker(prefix, _BONUS_MARKERS)
    req_at = _last_marker(prefix, _REQUIRED_MARKERS)
    if bonus_at < 0 and req_at < 0:
        return None
    if bonus_at > req_at:
        return Necessity.BONUS
    return Necessity.REQUIRED


def _last_marker(text: str, markers: tuple[str, ...]) -> int:
    best = -1
    for m in markers:
        pos = text.rfind(m)
        if pos > best:
            best = pos
    return best


def _parse_necessity(raw: str | None) -> Necessity | None:
    if raw == "bonus":
        return Necessity.BONUS
    if raw == "required":
        return Necessity.REQUIRED
    return None


async def extract_posting(
    posting: Posting,
    *,
    llm: LLMClient,
    locator: SpanLocator,
    store: MemoryExtractionStore,
    role_id: str = "unassigned",
) -> ExtractedPosting:
    text = posting.description or ""
    doc = store.save_plain(text, kind="posting", doc_id=posting.id)
    masked = mask_boilerplate(text, posting.boilerplate_spans)
    prompt = (
        "你是职位抽取器。只做语义判断，不要输出字符位置或坐标。\n"
        "从下面的职位描述中抽取「能力项」（一条能力陈述）和「技能点」（最细可验证粒度）。\n"
        "每一项的 quote 必须是原文中真实存在的连续子串，原样拷贝。\n"
        "跳过福利待遇、五险一金等模板套话，它们不是技能点。\n"
        f"职位标题：{posting.title}\n"
        f"正文：\n---\n{masked}\n---"
    )
    raw = await llm.complete_json(prompt, POSTING_SCHEMA)
    out = ExtractedPosting()

    for item in raw.get("competencies") or []:
        quote = str(item.get("quote") or "")
        span = locator.locate(doc.id, quote)
        if span is None:
            logger.info("丢弃能力项：quote 无法在原文定位 statement=%s", item.get("statement"))
            out.discarded += 1
            continue
        if overlaps_boilerplate(span, posting.boilerplate_spans):
            logger.info("跳过模板段落中的能力项 quote=%s", quote[:40])
            out.discarded += 1
            continue
        necessity = (
            infer_necessity(quote, text)
            or _parse_necessity(item.get("necessity"))
            or Necessity.REQUIRED
        )
        ev = make_evidence(
            source_id=posting.source_id,
            span=span,
            quote=text[span.start : span.end],
            extractor=EXTRACTOR,
            confidence=0.85,
            posting_id=posting.id,
        )
        store.save_evidence(ev)
        out.evidence.append(ev)
        comp = Competency(
            id=new_id(),
            role_id=role_id,
            statement=str(item.get("statement") or quote),
            necessity=necessity,
            evidence_ids=[ev.id],
            grade=grade_evidence([ev]),
            state=PublishState.UNVERIFIED,
        )
        out.competencies.append(comp)
        store.put_claim(
            ClaimRecord(
                id=comp.id,
                kind="competency",
                text=comp.statement,
                evidence_ids=[ev.id],
                payload={"necessity": necessity.value, "posting_id": posting.id},
                doc_id=doc.id,
            )
        )

    for item in raw.get("skills") or []:
        quote = str(item.get("quote") or "")
        span = locator.locate(doc.id, quote)
        if span is None:
            logger.info("丢弃技能点：quote 无法在原文定位 surface=%s", item.get("surface_form"))
            out.discarded += 1
            continue
        if overlaps_boilerplate(span, posting.boilerplate_spans):
            logger.info("跳过模板段落中的技能点 quote=%s", quote[:40])
            out.discarded += 1
            continue
        necessity = (
            infer_necessity(quote, text)
            or _parse_necessity(item.get("necessity"))
            or Necessity.REQUIRED
        )
        ev = make_evidence(
            source_id=posting.source_id,
            span=span,
            quote=text[span.start : span.end],
            extractor=EXTRACTOR,
            confidence=0.85,
            posting_id=posting.id,
        )
        store.save_evidence(ev)
        out.evidence.append(ev)
        surface = str(item.get("surface_form") or quote)
        out.skills.append(ExtractedSkill(surface_form=surface, necessity=necessity, evidence=ev))
        store.put_claim(
            ClaimRecord(
                id=new_id(),
                kind="skill",
                text=surface,
                evidence_ids=[ev.id],
                payload={"necessity": necessity.value, "posting_id": posting.id},
                doc_id=doc.id,
            )
        )
    return out
