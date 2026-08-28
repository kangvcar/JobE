"""学习资源挂接。候选必须来自检索；每条记 source 与 checked_at；URL 不可达即下线。

不自建课程库。大模型只能从检索候选里挑，发明的 URL 直接丢弃（ADR 0003）。
"""

from __future__ import annotations

from datetime import UTC, datetime

import httpx

from app.domain.models import Resource
from app.domain.ports import LLMClient
from app.matching.protocols import (
    LinkChecker,
    ResourceCache,
    ResourceCandidate,
    ResourceCatalog,
)

MAX_RESOURCES_PER_SKILL = 3

_PICK_SCHEMA = {
    "type": "object",
    "properties": {
        "picks": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "url": {"type": "string"},
                    "title": {"type": "string"},
                    "kind": {"type": "string"},
                },
            },
        }
    },
}


class HttpxLinkChecker:
    """HEAD 探测；405 时改 GET。超时与网络错误视为不可达。"""

    def __init__(self, client: httpx.Client | None = None) -> None:
        self._client = client
        self._owns_client = client is None

    def is_reachable(self, url: str) -> bool:
        client = self._client or httpx.Client(timeout=5.0, follow_redirects=True)
        try:
            response = client.head(url)
            if response.status_code == 405:
                response = client.get(url)
            return 200 <= response.status_code < 400
        except httpx.HTTPError:
            return False
        finally:
            if self._owns_client:
                client.close()


class InMemoryResourceCache:
    """进程内缓存。集成时换成 PostgreSQL 实现。"""

    def __init__(self) -> None:
        self._store: dict[str, list[Resource]] = {}

    def get(self, skill_id: str) -> list[Resource] | None:
        if skill_id not in self._store:
            return None
        return list(self._store[skill_id])

    def put(self, skill_id: str, resources: list[Resource]) -> None:
        self._store[skill_id] = list(resources)


def _now() -> datetime:
    return datetime.now(UTC)


def filter_reachable(
    resources: list[Resource],
    checker: LinkChecker,
    *,
    checked_at: datetime | None = None,
) -> list[Resource]:
    """不可达的资源不下发，即自动下线。"""
    stamp = checked_at or _now()
    alive: list[Resource] = []
    for item in resources:
        if checker.is_reachable(item.url):
            alive.append(item.model_copy(update={"checked_at": stamp}))
    return alive


async def _llm_pick(
    llm: LLMClient,
    skill_name: str,
    candidates: list[ResourceCandidate],
) -> list[ResourceCandidate]:
    by_url = {c.url: c for c in candidates}
    prompt = (
        f"从下列公开学习资源中为技能点「{skill_name}」挑选最多 "
        f"{MAX_RESOURCES_PER_SKILL} 条。"
        "只许返回候选里出现过的 url，不要编造。"
        "优先官方文档、开源课程、GitHub roadmap、公开课。\n"
        + "\n".join(f"- {c.kind} | {c.title} | {c.url} | 来源:{c.source}" for c in candidates)
    )
    payload = await llm.complete_json(prompt, _PICK_SCHEMA, temperature=0.0)
    picks = payload.get("picks") if isinstance(payload, dict) else None
    if not isinstance(picks, list):
        return candidates[:MAX_RESOURCES_PER_SKILL]
    selected: list[ResourceCandidate] = []
    seen: set[str] = set()
    for raw in picks:
        if not isinstance(raw, dict):
            continue
        url = raw.get("url")
        if not isinstance(url, str) or url in seen or url not in by_url:
            continue
        seen.add(url)
        origin = by_url[url]
        title = raw.get("title")
        kind = raw.get("kind")
        selected.append(
            ResourceCandidate(
                title=title if isinstance(title, str) and title else origin.title,
                url=origin.url,
                kind=kind if isinstance(kind, str) and kind else origin.kind,
                source=origin.source,
            )
        )
        if len(selected) >= MAX_RESOURCES_PER_SKILL:
            break
    return selected


class ResourceAttacher:
    def __init__(
        self,
        cache: ResourceCache,
        catalog: ResourceCatalog,
        checker: LinkChecker,
        llm: LLMClient | None = None,
    ) -> None:
        self._cache = cache
        self._catalog = catalog
        self._checker = checker
        self._llm = llm

    async def attach(self, skill_id: str, skill_name: str) -> list[Resource]:
        cached = self._cache.get(skill_id)
        if cached is not None:
            alive = filter_reachable(cached, self._checker)
            if len(alive) != len(cached):
                self._cache.put(skill_id, alive)
            return alive

        candidates = self._catalog.candidates(skill_id, skill_name)
        if not candidates:
            self._cache.put(skill_id, [])
            return []

        if self._llm is not None:
            try:
                chosen = await _llm_pick(self._llm, skill_name, candidates)
            except Exception:
                chosen = candidates[:MAX_RESOURCES_PER_SKILL]
        else:
            chosen = candidates[:MAX_RESOURCES_PER_SKILL]

        stamp = _now()
        resources = [
            Resource(
                title=c.title,
                url=c.url,
                kind=c.kind,
                source=c.source,
                checked_at=stamp,
            )
            for c in chosen
        ]
        alive = filter_reachable(resources, self._checker, checked_at=stamp)
        self._cache.put(skill_id, alive)
        return alive
