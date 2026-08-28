from __future__ import annotations

from app.extraction.normalize import VectorHit, char_recall, normalize_surface, try_vector_index
from app.extraction.ontology import load_skill_vocab
from app.extraction.store import AliasDecision, MemoryExtractionStore
from tests.extraction.conftest import FIXTURE_DIR, FakeLLM


def test_char_recall_finds_python():
    vocab = load_skill_vocab(FIXTURE_DIR, "v0")
    ids = char_recall("python 开发", vocab)
    assert "sk.py" in ids


async def test_alias_table_skips_llm(store: MemoryExtractionStore):
    vocab = load_skill_vocab(FIXTURE_DIR, "v0")
    store.put_alias(
        AliasDecision(surface_form="py", skill_id="sk.py", decided_by="human", confidence=1.0)
    )
    llm = FakeLLM({"skill_id": "should-not-be-called", "confidence": 0})
    d = await normalize_surface("py", vocab, llm=llm, store=store)
    assert d.skill_id == "sk.py"
    assert llm.calls == []


async def test_exact_name_no_llm(store: MemoryExtractionStore):
    vocab = load_skill_vocab(FIXTURE_DIR, "v0")
    llm = FakeLLM({"skill_id": "nope", "confidence": 0})
    d = await normalize_surface("Python", vocab, llm=llm, store=store)
    assert d.skill_id == "sk.py"
    assert d.decided_by == "exact"
    assert store.get_alias("Python") is d


async def test_go_verb_not_exact_mapped(store: MemoryExtractionStore):
    """小写 go 不得直接当成编程语言，须走裁决。"""
    vocab = load_skill_vocab(FIXTURE_DIR, "v0")
    llm = FakeLLM({"skill_id": None, "confidence": 0.2, "reason": "动词"})
    d = await normalize_surface("go", vocab, llm=llm, store=store, context="Let's go to lunch")
    assert d.skill_id is None
    assert llm.calls  # 走了裁决而不是 exact
    # 同一别名对只裁决一次
    llm2 = FakeLLM({"skill_id": "sk.go", "confidence": 0.9})
    d2 = await normalize_surface("go", vocab, llm=llm2, store=store, context="again")
    assert d2.skill_id is None
    assert llm2.calls == []


async def test_adjudicate_rejects_unknown_id(store: MemoryExtractionStore):
    vocab = load_skill_vocab(FIXTURE_DIR, "v0")
    llm = FakeLLM({"skill_id": "sk.not-in-candidates", "confidence": 0.9})
    d = await normalize_surface("Flink", vocab, llm=llm, store=store, context="熟悉 Flink")
    assert d.skill_id is None


async def test_vector_recall_merged(store: MemoryExtractionStore):
    vocab = load_skill_vocab(FIXTURE_DIR, "v0")

    class _Vec:
        def top_k(self, surface: str, k: int = 20) -> list[VectorHit]:
            return [VectorHit(skill_id="sk.k8s", score=0.99)]

    llm = FakeLLM({"skill_id": "sk.k8s", "confidence": 0.8})
    d = await normalize_surface("k8s编排", vocab, llm=llm, store=store, vector_index=_Vec())
    assert d.skill_id == "sk.k8s"


def test_try_vector_index_missing(monkeypatch, caplog):
    caplog.set_level("WARNING")

    def _boom(*_a, **_k):
        raise ImportError("nope")

    monkeypatch.setattr("app.extraction.normalize.BgeM3VectorIndex", _boom)
    idx = try_vector_index([])
    assert idx is None
    assert "bge-m3" in caplog.text.lower() or "FlagEmbedding" in caplog.text
