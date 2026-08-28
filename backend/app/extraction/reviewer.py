"""AI 审核员：独立于抽取链路，只判断结论是否被证据支持，不产生新结论。"""

from __future__ import annotations

import json
import logging

from app.domain.models import Evidence, EvidenceGrade, ReviewOutcome, ReviewVerdict
from app.domain.ports import LLMClient

logger = logging.getLogger("jobe.extraction.reviewer")

WEAK_CONFIDENCE = 0.5

REVIEW_SCHEMA = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string", "enum": ["supported", "unsupported", "uncertain"]},
        "reason": {"type": "string"},
        "cited_evidence_ids": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["verdict", "reason", "cited_evidence_ids"],
}


def grade_evidence(items: list[Evidence]) -> EvidenceGrade:
    """多源确认 / 单源 / 弱证据。低置信度或空证据一律弱证据。"""
    strong = [e for e in items if e.confidence >= WEAK_CONFIDENCE]
    if not strong:
        return EvidenceGrade.WEAK
    sources = {e.source_id for e in strong}
    if len(sources) >= 2:
        return EvidenceGrade.MULTI_SOURCE
    return EvidenceGrade.SINGLE_SOURCE


class LLMReviewer:
    """ports.Reviewer。换模型、换 prompt、回原文取证。"""

    def __init__(self, llm: LLMClient) -> None:
        self._llm = llm

    async def review(self, claim: str, evidence: list[Evidence]) -> ReviewOutcome:
        payload = [
            {
                "id": e.id,
                "source_id": e.source_id,
                "quote": e.quote,
                "confidence": e.confidence,
            }
            for e in evidence
        ]
        allowed = {e.id for e in evidence}
        prompt = (
            "你是独立审核员，不产生新结论，不补充新事实。\n"
            "只判断「这条结论是否被下列证据支持」。\n"
            "supported：证据原文明确支持结论。\n"
            "unsupported：证据与结论矛盾或完全无关。\n"
            "uncertain：证据不足以下判断。\n"
            "cited_evidence_ids 只能引用下面给出的证据 id。\n"
            f"结论：{claim}\n"
            f"证据：\n{json.dumps(payload, ensure_ascii=False)}"
        )
        raw = await self._llm.complete_json(prompt, REVIEW_SCHEMA)
        try:
            verdict = ReviewVerdict(str(raw.get("verdict")))
        except ValueError:
            verdict = ReviewVerdict.UNCERTAIN
        cited = [i for i in (raw.get("cited_evidence_ids") or []) if i in allowed]
        return ReviewOutcome(
            verdict=verdict,
            reason=str(raw.get("reason") or ""),
            cited_evidence_ids=cited,
        )
