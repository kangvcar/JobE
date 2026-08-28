from __future__ import annotations

from pathlib import Path

import pytest

from app.extraction.deps import ExtractionDeps, set_deps
from app.extraction.store import MemoryExtractionStore

FIXTURE_DIR = Path(__file__).parent / "fixtures"


class FakeLLM:
    """单元测试用：按顺序返回预先写好的 JSON，绝不联网。"""

    def __init__(self, responses: list[dict] | dict | None = None) -> None:
        if responses is None:
            self._responses: list[dict] = [{}]
        elif isinstance(responses, dict):
            self._responses = [responses]
        else:
            self._responses = list(responses)
        self.calls: list[dict] = []
        self._i = 0

    async def complete_json(self, prompt: str, schema: dict, *, temperature: float = 0.0) -> dict:
        self.calls.append({"prompt": prompt, "schema": schema, "temperature": temperature})
        item = self._responses[min(self._i, len(self._responses) - 1)]
        self._i += 1
        return dict(item)

    async def complete_text(self, prompt: str, *, temperature: float = 0.0) -> str:
        return ""


@pytest.fixture
def store() -> MemoryExtractionStore:
    return MemoryExtractionStore()


@pytest.fixture
def fake_llm() -> FakeLLM:
    return FakeLLM()


@pytest.fixture(autouse=True)
def _wire_deps(store: MemoryExtractionStore, fake_llm: FakeLLM):
    set_deps(
        ExtractionDeps(
            store=store,
            llm=fake_llm,
            reviewer_llm=fake_llm,
            ontology_dir=FIXTURE_DIR,
            ontology_version="v0",
        )
    )
    yield
    set_deps(None)
