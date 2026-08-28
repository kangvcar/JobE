from __future__ import annotations

from app.extraction.locator import CanonicalSpanLocator
from app.extraction.ontology import SkillVocabEntry, load_skill_vocab
from app.extraction.resume import channel_a, extract_resume, segment_resume
from app.extraction.store import MemoryExtractionStore
from tests.extraction.conftest import FIXTURE_DIR, FakeLLM


def test_load_skill_vocab_fixture():
    vocab = load_skill_vocab(FIXTURE_DIR, "v0")
    names = {v.name for v in vocab}
    assert {"Python", "Go", "Kubernetes"} <= names


def test_segment_resume_by_headings():
    text = "张三\n基本信息\n男 北京\n教育经历\n清华大学\n工作经历\n某公司\n技能专长\nPython Go"
    blocks = segment_resume(text)
    kinds = [b.kind for b in blocks]
    assert "education" in kinds
    assert "work" in kinds
    assert "skill" in kinds


def test_channel_a_offsets_and_go_boundary():
    vocab = load_skill_vocab(FIXTURE_DIR, "v0")
    text = "精通 Go 与 Python，正在 Going 调研 JavaScript。"
    hits = channel_a(text, vocab)
    surfaces = {h[3] for h in hits}
    assert "Go" in surfaces
    assert "Python" in surfaces
    assert "Going" not in surfaces
    go = next(h for h in hits if h[3] == "Go")
    assert text[go[0] : go[1]] == "Go"


def test_channel_a_drops_all_lowercase_short_aliases_but_keeps_uppercase():
    """词表里 Rust 带别名 rs，不能让「rs 报告」命中 Rust；JS/ML 这类大写缩写要留住。"""
    vocab = [
        SkillVocabEntry(id="skill.rust", name="Rust", aliases=["rs", "rust"]),
        SkillVocabEntry(id="skill.javascript", name="JavaScript", aliases=["JS"]),
    ]
    assert channel_a("rs 报告已提交", vocab) == []
    assert {h[2] for h in channel_a("用过 JS 和 rust", vocab)} == {
        "skill.javascript",
        "skill.rust",
    }


async def test_channel_b_hallucination_dropped(store: MemoryExtractionStore):
    vocab = load_skill_vocab(FIXTURE_DIR, "v0")
    doc = store.save_plain("工作中使用 Python。", kind="resume", doc_id="r1")
    llm = FakeLLM(
        [
            {},
            {"skills": [{"surface_form": "Rust", "quote": "精通 Rust 十年"}]},
        ]
    )
    out = await extract_resume(
        doc, llm=llm, locator=CanonicalSpanLocator(store), store=store, vocab=vocab
    )
    assert out.discarded >= 1
    assert all(s.skill_id != "Rust" for s in out.profile.skills)


async def test_channel_b_new_skill_enters_unverified(store: MemoryExtractionStore):
    vocab = load_skill_vocab(FIXTURE_DIR, "v0")
    text = "张三\n熟悉 Flink 流处理。"
    doc = store.save_plain(text, kind="resume", doc_id="r2")
    llm = FakeLLM(
        [
            {"name": "张三"},
            {"skills": [{"surface_form": "Flink", "quote": "Flink"}]},
            {"skill_id": None, "confidence": 0.1, "reason": "词表没有"},
        ]
    )
    out = await extract_resume(
        doc, llm=llm, locator=CanonicalSpanLocator(store), store=store, vocab=vocab
    )
    assert any(c.surface_form == "Flink" for c in out.candidates)
    assert any(c.kind == "new_skill" for c in store.unverified())
    assert any(f.name == "name" and f.value == "张三" for f in out.fields)


async def test_field_hallucination_dropped(store: MemoryExtractionStore):
    vocab: list[SkillVocabEntry] = []
    doc = store.save_plain("姓名：李四", kind="resume", doc_id="r3")
    llm = FakeLLM([{"name": "王五"}, {"skills": []}])
    out = await extract_resume(
        doc, llm=llm, locator=CanonicalSpanLocator(store), store=store, vocab=vocab
    )
    assert out.fields == []
    assert out.discarded >= 1
