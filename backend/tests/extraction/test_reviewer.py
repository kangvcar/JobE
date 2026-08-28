from __future__ import annotations

from datetime import UTC, datetime

from app.domain.models import Evidence, EvidenceGrade, ReviewVerdict, TextSpan
from app.extraction.reviewer import LLMReviewer, grade_evidence
from tests.extraction.conftest import FakeLLM


def _ev(*, source_id: str, confidence: float, eid: str = "e1") -> Evidence:
    return Evidence(
        id=eid,
        source_id=source_id,
        span=TextSpan(doc_id="d", start=0, end=4),
        quote="Python",
        fetched_at=datetime.now(UTC),
        extractor="test",
        confidence=confidence,
    )


def test_grade_multi_source():
    items = [
        _ev(source_id="a", confidence=0.9, eid="1"),
        _ev(source_id="b", confidence=0.8, eid="2"),
    ]
    assert grade_evidence(items) is EvidenceGrade.MULTI_SOURCE


def test_grade_single_source():
    items = [
        _ev(source_id="a", confidence=0.9, eid="1"),
        _ev(source_id="a", confidence=0.8, eid="2"),
    ]
    assert grade_evidence(items) is EvidenceGrade.SINGLE_SOURCE


def test_grade_weak_low_confidence():
    assert grade_evidence([_ev(source_id="a", confidence=0.2)]) is EvidenceGrade.WEAK
    assert grade_evidence([]) is EvidenceGrade.WEAK


def test_grade_weak_overrides_even_if_two_sources_are_all_weak():
    items = [
        _ev(source_id="a", confidence=0.1, eid="1"),
        _ev(source_id="b", confidence=0.2, eid="2"),
    ]
    assert grade_evidence(items) is EvidenceGrade.WEAK


async def test_reviewer_supported():
    llm = FakeLLM(
        {
            "verdict": "supported",
            "reason": "原文写了精通 Python",
            "cited_evidence_ids": ["e1", "ghost"],
        }
    )
    out = await LLMReviewer(llm).review(
        "候选人掌握 Python", [_ev(source_id="moka", confidence=0.9)]
    )
    assert out.verdict is ReviewVerdict.SUPPORTED
    assert out.cited_evidence_ids == ["e1"]  # ghost 被丢掉


async def test_reviewer_unsupported_and_invalid_verdict():
    llm = FakeLLM({"verdict": "not-a-verdict", "reason": "?", "cited_evidence_ids": []})
    out = await LLMReviewer(llm).review("结论", [_ev(source_id="x", confidence=0.9)])
    assert out.verdict is ReviewVerdict.UNCERTAIN
