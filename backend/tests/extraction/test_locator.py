from __future__ import annotations

from app.extraction.layout import CharIndex
from app.extraction.locator import CanonicalSpanLocator, find_hits, fold
from app.extraction.store import MemoryExtractionStore


def _doc(
    store: MemoryExtractionStore, text: str, doc_id: str = "d1", blocks: list[dict] | None = None
):
    rec = store.save_plain(text, kind="posting", doc_id=doc_id)
    if blocks:
        rec.char_index.blocks = blocks
    return rec


def test_exact_match(store: MemoryExtractionStore):
    text = "任职要求：精通 Python 与 Kubernetes。"
    _doc(store, text)
    loc = CanonicalSpanLocator(store)
    span = loc.locate("d1", "精通 Python")
    assert span is not None
    assert text[span.start : span.end] == "精通 Python"
    assert span.page_index is None


def test_whitespace_difference(store: MemoryExtractionStore):
    text = "熟悉 Python 与 Go 语言"
    _doc(store, text)
    loc = CanonicalSpanLocator(store)
    span = loc.locate("d1", "熟悉Python与Go")
    assert span is not None
    assert "Python" in text[span.start : span.end]
    assert "Go" in text[span.start : span.end]


def test_fullwidth_halfwidth(store: MemoryExtractionStore):
    text = "掌握 Ｐｙｔｈｏｎ 开发"
    _doc(store, text)
    loc = CanonicalSpanLocator(store)
    span = loc.locate("d1", "Python")
    assert span is not None
    folded, _ = fold(text[span.start : span.end])
    assert "Python" in folded


def test_multiple_hits_uses_hint(store: MemoryExtractionStore):
    text = "第一段使用 Python。第二段使用 Python 做服务。"
    _doc(store, text)
    loc = CanonicalSpanLocator(store)
    first = text.find("Python")
    second = text.find("Python", first + 1)
    span = loc.locate("d1", "Python", hint_start=second)
    assert span is not None
    assert span.start == second


def test_multiple_hits_block_boundary(store: MemoryExtractionStore):
    text = "技能\nPython\n项目\nPython"
    first = text.find("Python")
    second = text.find("Python", first + 1)
    _doc(
        store,
        text,
        blocks=[
            {"start": 0, "end": second, "kind": "skill"},
            {"start": second - 3, "end": len(text), "kind": "project"},
        ],
    )
    loc = CanonicalSpanLocator(store)
    span = loc.locate("d1", "Python", hint_start=second)
    assert span is not None
    assert span.start == second


def test_no_match_returns_none(store: MemoryExtractionStore):
    _doc(store, "熟悉 Java 开发")
    loc = CanonicalSpanLocator(store)
    assert loc.locate("d1", "React Native") is None


def test_empty_quote_returns_none(store: MemoryExtractionStore):
    _doc(store, "熟悉 Java")
    loc = CanonicalSpanLocator(store)
    assert loc.locate("d1", "") is None
    assert loc.locate("d1", "   ") is None
    assert loc.locate("missing", "Java") is None


def test_find_hits_exact_and_folded():
    text = "A  B"
    assert find_hits(text, "A  B") == [(0, 4)]
    assert find_hits(text, "AB") == [(0, 4)]


def test_span_geometry_union():
    idx = CharIndex(
        pages=[{"w": 100, "h": 100}],
        runs=[[0, 2, 0, 10, 20, 15, 30], [2, 4, 0, 15, 18, 40, 32]],
    )
    page, bbox = idx.span_geometry(0, 4)
    assert page == 0
    assert bbox == (10, 18, 40, 32)
