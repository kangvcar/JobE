"""抽取层依赖注入。路由与测试通过 get_deps / set_deps 替换实现。"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from app.domain.ports import LLMClient
from app.extraction.ontology import SkillVocabEntry, load_skill_vocab
from app.extraction.store import MemoryExtractionStore

_deps: ExtractionDeps | None = None


@dataclass
class ExtractionDeps:
    store: MemoryExtractionStore
    llm: LLMClient
    reviewer_llm: LLMClient
    ontology_dir: Path | None = None
    ontology_version: str | None = None
    vocab: list[SkillVocabEntry] = field(default_factory=list)

    def skill_vocab(self) -> list[SkillVocabEntry]:
        if self.vocab:
            return self.vocab
        return load_skill_vocab(self.ontology_dir, self.ontology_version)


def get_deps() -> ExtractionDeps:
    global _deps
    if _deps is None:
        _deps = build_default_deps()
    return _deps


def set_deps(deps: ExtractionDeps | None) -> None:
    global _deps
    _deps = deps


def build_default_deps() -> ExtractionDeps:
    from app.extraction.llm import make_extractor_client, make_reviewer_client

    return ExtractionDeps(
        store=MemoryExtractionStore(),
        llm=make_extractor_client(),
        reviewer_llm=make_reviewer_client(),
    )
