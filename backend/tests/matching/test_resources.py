"""资源挂接与失效链接下线。全程打桩，不联网。"""

from __future__ import annotations

import httpx

from app.matching.protocols import ResourceCandidate
from app.matching.resources import (
    HttpxLinkChecker,
    InMemoryResourceCache,
    ResourceAttacher,
    filter_reachable,
)

from .fakes import FakeCatalog, FakeChecker, FakeLLM

LIVE = "https://docs.example/python"
DEAD = "https://dead.example/gone"
DOCS = ResourceCandidate(title="Python 文档", url=LIVE, kind="docs", source="docs.python.org")
BROKEN = ResourceCandidate(title="失效课", url=DEAD, kind="course", source="mooc.example")
GITHUB = ResourceCandidate(
    title="roadmap", url="https://github.example/roadmap", kind="github", source="github"
)


async def test_dead_link_is_taken_offline():
    attacher = ResourceAttacher(
        InMemoryResourceCache(),
        FakeCatalog({"python": [DOCS, BROKEN]}),
        FakeChecker({DEAD}),
    )
    resources = await attacher.attach("python", "Python")
    assert [r.url for r in resources] == [LIVE]
    assert resources[0].checked_at is not None
    assert resources[0].source == "docs.python.org"


async def test_cache_hit_skips_catalog():
    cache = InMemoryResourceCache()
    catalog = FakeCatalog({"python": [DOCS]})
    attacher = ResourceAttacher(cache, catalog, FakeChecker())
    first = await attacher.attach("python", "Python")
    second = await attacher.attach("python", "Python")
    assert catalog.calls == ["python"]
    assert [r.url for r in first] == [r.url for r in second]


async def test_cached_dead_link_is_dropped_on_reread():
    cache = InMemoryResourceCache()
    catalog = FakeCatalog({"python": [DOCS, BROKEN]})
    live_checker = FakeChecker()
    attacher = ResourceAttacher(cache, catalog, live_checker)
    stored = await attacher.attach("python", "Python")
    assert {r.url for r in stored} == {LIVE, DEAD}

    attacher_later = ResourceAttacher(cache, catalog, FakeChecker({DEAD}))
    later = await attacher_later.attach("python", "Python")
    assert [r.url for r in later] == [LIVE]
    assert catalog.calls == ["python"]


async def test_llm_picks_only_candidate_urls():
    llm = FakeLLM(
        json_payload={
            "picks": [
                {"url": LIVE, "title": "官方文档", "kind": "docs"},
                {"url": "https://invented.example/nope", "title": "幻觉"},
            ]
        }
    )
    attacher = ResourceAttacher(
        InMemoryResourceCache(),
        FakeCatalog({"python": [DOCS, GITHUB]}),
        FakeChecker(),
        llm,
    )
    resources = await attacher.attach("python", "Python")
    assert [r.url for r in resources] == [LIVE]
    assert resources[0].title == "官方文档"
    assert llm.json_calls == 1


async def test_llm_error_falls_back_to_candidate_order():
    attacher = ResourceAttacher(
        InMemoryResourceCache(),
        FakeCatalog({"python": [DOCS, GITHUB]}),
        FakeChecker(),
        FakeLLM(json_error=RuntimeError("boom")),
    )
    resources = await attacher.attach("python", "Python")
    assert [r.url for r in resources] == [LIVE, "https://github.example/roadmap"]


def test_filter_reachable_drops_dead():
    from datetime import UTC, datetime

    from app.domain.models import Resource

    now = datetime(2026, 8, 28, tzinfo=UTC)
    kept = filter_reachable(
        [
            Resource(title="a", url=LIVE, kind="docs", source="x"),
            Resource(title="b", url=DEAD, kind="docs", source="x"),
        ],
        FakeChecker({DEAD}),
        checked_at=now,
    )
    assert len(kept) == 1
    assert kept[0].checked_at == now


def test_httpx_checker_head_ok():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "HEAD" and str(request.url) == LIVE:
            return httpx.Response(200)
        return httpx.Response(404)

    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)
    checker = HttpxLinkChecker(client)
    assert checker.is_reachable(LIVE) is True
    assert checker.is_reachable(DEAD) is False


def test_httpx_checker_falls_back_get_on_405():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "HEAD":
            return httpx.Response(405)
        if request.method == "GET" and str(request.url) == LIVE:
            return httpx.Response(200)
        return httpx.Response(404)

    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)
    checker = HttpxLinkChecker(client)
    assert checker.is_reachable(LIVE) is True


def test_httpx_checker_network_error_is_unreachable():
    def handler(request: httpx.Request) -> httpx.Response:
        del request
        raise httpx.ConnectError("nope")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    assert HttpxLinkChecker(client).is_reachable(LIVE) is False


async def test_empty_catalog_caches_empty_list():
    cache = InMemoryResourceCache()
    attacher = ResourceAttacher(cache, FakeCatalog(), FakeChecker())
    assert await attacher.attach("python", "Python") == []
    assert cache.get("python") == []
