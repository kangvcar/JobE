from __future__ import annotations

from pathlib import Path

import pytest

from app.collectors.liepin import (
    LiepinCollector,
    LiepinHalted,
    LiepinUnavailable,
)
from app.collectors.rate_limit import RateLimiter

FIXTURES = Path(__file__).parent / "fixtures"


def test_disabled_yields_nothing():
    collector = LiepinCollector(enabled=False, limiter=RateLimiter(0))
    assert list(collector.collect()) == []


def test_captcha_stops_immediately():
    collector = LiepinCollector(
        enabled=True,
        limiter=RateLimiter(0),
        fetch_listing=lambda: (200, "<html>请完成验证码后继续</html>"),
    )
    with pytest.raises(LiepinHalted, match="验证码"):
        list(collector.collect())


def test_http_error_stops_immediately():
    collector = LiepinCollector(
        enabled=True,
        limiter=RateLimiter(0),
        fetch_listing=lambda: (403, "forbidden"),
    )
    with pytest.raises(LiepinHalted, match="403"):
        list(collector.collect())


def test_empty_results_stop():
    collector = LiepinCollector(
        enabled=True,
        limiter=RateLimiter(0),
        fetch_listing=lambda: (200, "<html><body>暂无职位</body></html>"),
    )
    with pytest.raises(LiepinHalted, match="空结果集"):
        list(collector.collect())


def test_listing_cards_skip_query_strings():
    html = (FIXTURES / "liepin_list.html").read_text(encoding="utf-8")
    collector = LiepinCollector(
        enabled=True,
        limiter=RateLimiter(0),
        fetch_listing=lambda: (200, html),
    )
    snaps = list(collector.collect())
    assert len(snaps) == 2
    hrefs = [s.payload["href"] for s in snaps]
    assert all("?" not in h for h in hrefs)
    assert all("/zhaopin/" in h for h in hrefs)


def test_missing_playwright(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.collectors.liepin.sync_playwright", None)
    state = tmp_path / "liepin.json"
    state.write_text("{}", encoding="utf-8")
    collector = LiepinCollector(enabled=True, limiter=RateLimiter(0), storage_state=state)
    with pytest.raises(LiepinUnavailable, match="Playwright"):
        list(collector.collect())


def test_missing_storage_state(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("app.collectors.liepin.sync_playwright", object)
    collector = LiepinCollector(
        enabled=True, limiter=RateLimiter(0), storage_state=tmp_path / "missing.json"
    )
    with pytest.raises(LiepinUnavailable, match="登录态"):
        list(collector.collect())


def test_playwright_happy_path(monkeypatch, tmp_path: Path):
    html = (FIXTURES / "liepin_list.html").read_text(encoding="utf-8")
    state = tmp_path / "liepin.json"
    state.write_text("{}", encoding="utf-8")

    class FakeResponse:
        status = 200

    class FakePage:
        def goto(self, url, wait_until=None):
            assert url == "https://www.liepin.com/zhaopin/"
            return FakeResponse()

        def content(self):
            return html

    class FakeContext:
        def new_page(self):
            return FakePage()

        def close(self):
            return None

    class FakeBrowser:
        def new_context(self, **kwargs):
            assert "storage_state" in kwargs
            return FakeContext()

        def close(self):
            return None

    class FakeChromium:
        def launch(self, headless=True):
            return FakeBrowser()

    class FakePlaywright:
        chromium = FakeChromium()

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    monkeypatch.setattr("app.collectors.liepin.sync_playwright", lambda: FakePlaywright())
    snaps = list(
        LiepinCollector(enabled=True, limiter=RateLimiter(0), storage_state=state).collect()
    )
    assert len(snaps) == 2
