from __future__ import annotations

from datetime import date

from app.domain.models import Necessity, Posting
from app.extraction.locator import CanonicalSpanLocator
from app.extraction.posting import (
    extract_posting,
    infer_necessity,
    mask_boilerplate,
    overlaps_boilerplate,
)
from app.extraction.store import MemoryExtractionStore
from tests.extraction.conftest import FakeLLM


def _posting(text: str, spans: list[tuple[int, int]] | None = None) -> Posting:
    return Posting(
        id="p1",
        source_id="moka",
        snapshot_id="s1",
        title="后端工程师",
        published_at=date(2026, 1, 1),
        description=text,
        boilerplate_spans=spans or [],
    )


def test_infer_necessity_required_and_bonus():
    text = "任职要求：必须精通 Python。\n加分项：了解 Rust。"
    assert infer_necessity("Python", text) is Necessity.REQUIRED
    assert infer_necessity("Rust", text) is Necessity.BONUS
    mixed = "要求熟悉 Java，加分了解 Go。"
    assert infer_necessity("Java", mixed) is Necessity.REQUIRED
    assert infer_necessity("Go", mixed) is Necessity.BONUS


def test_infer_necessity_unknown_returns_none():
    assert infer_necessity("GraphQL", "日常使用 GraphQL 进行接口开发。") is None


def test_mask_boilerplate_blanks_span():
    text = "技能：Python。福利：五险一金。"
    i = text.find("福利")
    masked = mask_boilerplate(text, [(i, len(text))])
    assert "Python" in masked
    assert "五险一金" not in masked


async def test_hallucinated_quote_is_discarded(store: MemoryExtractionStore):
    text = "任职要求：精通 Python。"
    llm = FakeLLM(
        {
            "competencies": [{"statement": "前端跨端", "quote": "React Native 八年经验"}],
            "skills": [{"surface_form": "React Native", "quote": "React Native"}],
        }
    )
    loc = CanonicalSpanLocator(store)
    out = await extract_posting(_posting(text), llm=llm, locator=loc, store=store)
    assert out.competencies == []
    assert out.skills == []
    assert out.discarded == 2


async def test_boilerplate_skill_skipped(store: MemoryExtractionStore):
    text = "技能要求：Python。福利待遇：五险一金、带薪年假。"
    i = text.find("福利")
    llm = FakeLLM(
        {
            "competencies": [],
            "skills": [
                {"surface_form": "五险一金", "quote": "五险一金"},
                {"surface_form": "Python", "quote": "Python"},
            ],
        }
    )
    loc = CanonicalSpanLocator(store)
    out = await extract_posting(
        _posting(text, [(i, len(text))]),
        llm=llm,
        locator=loc,
        store=store,
    )
    assert [s.surface_form for s in out.skills] == ["Python"]
    assert out.discarded >= 1
    span = out.skills[0].evidence.span
    assert not overlaps_boilerplate(span, [(i, len(text))])


async def test_necessity_rule_overrides_llm(store: MemoryExtractionStore):
    text = "加分项：优先了解 Rust。"
    llm = FakeLLM(
        {
            "competencies": [
                {"statement": "了解 Rust", "quote": "优先了解 Rust", "necessity": "required"}
            ],
            "skills": [],
        }
    )
    loc = CanonicalSpanLocator(store)
    out = await extract_posting(_posting(text), llm=llm, locator=loc, store=store)
    assert len(out.competencies) == 1
    assert out.competencies[0].necessity is Necessity.BONUS


async def test_necessity_llm_fallback_when_no_marker(store: MemoryExtractionStore):
    text = "日常使用 GraphQL 进行接口开发。"
    llm = FakeLLM(
        {
            "competencies": [{"statement": "会 GraphQL", "quote": "GraphQL", "necessity": "bonus"}],
            "skills": [],
        }
    )
    loc = CanonicalSpanLocator(store)
    out = await extract_posting(_posting(text), llm=llm, locator=loc, store=store)
    assert out.competencies[0].necessity is Necessity.BONUS


async def test_kept_item_has_evidence_offsets(store: MemoryExtractionStore):
    text = "要求精通 Kubernetes。"
    llm = FakeLLM(
        {
            "competencies": [{"statement": "精通 K8s", "quote": "精通 Kubernetes"}],
            "skills": [{"surface_form": "Kubernetes", "quote": "Kubernetes"}],
        }
    )
    loc = CanonicalSpanLocator(store)
    out = await extract_posting(_posting(text), llm=llm, locator=loc, store=store)
    assert out.discarded == 0
    ev = out.evidence[0]
    assert text[ev.span.start : ev.span.end] == ev.quote
    assert ev.quote in text
    assert store.unverified()
