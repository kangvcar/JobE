"""表面形式 → 技能点 ID。同一别名对只裁决一次，结果写入 alias_decisions。"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from rapidfuzz import fuzz, process

from app.domain.ports import LLMClient
from app.extraction.ontology import SkillVocabEntry
from app.extraction.store import AliasDecision, MemoryExtractionStore

logger = logging.getLogger("jobe.extraction.normalize")

_CHAR_TOP_K = 20
_VEC_TOP_K = 20
_AMBIGUOUS_SHORT = 3

NORMALIZE_SCHEMA = {
    "type": "object",
    "properties": {
        "skill_id": {"type": ["string", "null"]},
        "confidence": {"type": "number"},
        "reason": {"type": "string"},
    },
    "required": ["skill_id", "confidence"],
}


@dataclass
class VectorHit:
    skill_id: str
    score: float


class VectorIndex:
    """可选向量召回。BAAI/bge-m3 未装时不要实例化。"""

    def top_k(self, surface: str, k: int = _VEC_TOP_K) -> list[VectorHit]:
        raise NotImplementedError


class BgeM3VectorIndex(VectorIndex):
    def __init__(self, vocab: list[SkillVocabEntry]) -> None:
        import numpy as np
        from FlagEmbedding import BGEM3FlagModel

        self._np = np
        self._ids = [v.id for v in vocab]
        self._model = BGEM3FlagModel("BAAI/bge-m3", use_fp16=True)
        names = [v.name for v in vocab]
        encoded = self._model.encode(names)["dense_vecs"]
        self._mat = np.asarray(encoded, dtype="float32")

    def top_k(self, surface: str, k: int = _VEC_TOP_K) -> list[VectorHit]:
        q = self._model.encode([surface])["dense_vecs"]
        vec = self._np.asarray(q, dtype="float32")[0]
        mat = self._mat
        denom = (self._np.linalg.norm(mat, axis=1) * (self._np.linalg.norm(vec) + 1e-9)) + 1e-9
        scores = mat @ vec / denom
        k = min(k, len(self._ids))
        idxs = self._np.argsort(-scores)[:k]
        return [VectorHit(skill_id=self._ids[int(i)], score=float(scores[int(i)])) for i in idxs]


def try_vector_index(vocab: list[SkillVocabEntry]) -> VectorIndex | None:
    try:
        return BgeM3VectorIndex(vocab)
    except ImportError as exc:
        logger.warning("BAAI/bge-m3（FlagEmbedding）未安装，别名召回仅用字符相似度。原因：%s", exc)
        return None


def char_recall(surface: str, vocab: list[SkillVocabEntry], k: int = _CHAR_TOP_K) -> list[str]:
    corpus: dict[str, str] = {}
    owner: dict[str, str] = {}
    n = 0
    for entry in vocab:
        for form in entry.surface_forms():
            key = f"{n}:{form}"
            corpus[key] = form
            owner[key] = entry.id
            n += 1
    if not corpus:
        return []
    hits = process.extract(surface, corpus, scorer=fuzz.token_set_ratio, limit=k)
    ids: list[str] = []
    seen: set[str] = set()
    for _form, _score, key in hits:
        sid = owner[str(key)]
        if sid not in seen:
            seen.add(sid)
            ids.append(sid)
    return ids


async def normalize_surface(
    surface: str,
    vocab: list[SkillVocabEntry],
    *,
    llm: LLMClient,
    store: MemoryExtractionStore,
    context: str = "",
    vector_index: VectorIndex | None = None,
    decided_by: str = "llm-normalizer",
) -> AliasDecision:
    """表面形式归一。命中别名表则直接返回，不再调用 LLM。"""
    cached = store.get_alias(surface)
    if cached is not None:
        return cached

    exact = _exact_id(surface, vocab)
    if exact is not None:
        decision = AliasDecision(
            surface_form=surface, skill_id=exact, decided_by="exact", confidence=1.0
        )
        store.put_alias(decision)
        return decision

    by_id = {v.id: v for v in vocab}
    recalled = char_recall(surface, vocab)
    if vector_index is not None:
        for hit in vector_index.top_k(surface):
            if hit.skill_id not in recalled:
                recalled.append(hit.skill_id)
    candidates = [by_id[i] for i in recalled if i in by_id][:40]
    decision = await _adjudicate(surface, candidates, llm, context, decided_by)
    store.put_alias(decision)
    return decision


def _exact_id(surface: str, vocab: list[SkillVocabEntry]) -> str | None:
    target = surface.strip()
    for entry in vocab:
        if entry.name == target or target in entry.aliases:
            return entry.id
    lower = target.casefold()
    # 短拉丁名大小写必须一致，避免 go 动词被当成 Go
    for entry in vocab:
        if len(entry.name) <= _AMBIGUOUS_SHORT and entry.name.isascii():
            continue
        if entry.name.casefold() == lower:
            return entry.id
        for a in entry.aliases:
            if len(a) <= _AMBIGUOUS_SHORT and a.isascii():
                continue
            if a.casefold() == lower:
                return entry.id
    return None


async def _adjudicate(
    surface: str,
    candidates: list[SkillVocabEntry],
    llm: LLMClient,
    context: str,
    decided_by: str,
) -> AliasDecision:
    options = [{"id": c.id, "name": c.name, "aliases": c.aliases} for c in candidates]
    prompt = (
        "你是技能点归一裁决器。把表面形式映射到候选技能点 id，或判定无法映射。\n"
        "注意消歧：短词如 Go/C/R 可能是编程语言，也可能是普通词语；"
        "没有上下文支持就返回 skill_id=null。\n"
        "不要输出坐标。\n"
        f"表面形式：{surface}\n"
        f"上下文：{context or '（无）'}\n"
        f"候选：{options}"
    )
    raw = await llm.complete_json(prompt, NORMALIZE_SCHEMA)
    skill_id = raw.get("skill_id")
    if skill_id not in {c.id for c in candidates}:
        skill_id = None
    try:
        confidence = float(raw.get("confidence") or 0.0)
    except (TypeError, ValueError):
        confidence = 0.0
    return AliasDecision(
        surface_form=surface,
        skill_id=skill_id,
        decided_by=decided_by,
        confidence=confidence,
    )
