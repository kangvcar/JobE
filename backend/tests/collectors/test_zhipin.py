from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.collectors.rate_limit import RateLimiter
from app.collectors.zhipin import (
    ZhipinCollector,
    ZhipinHalted,
    ZhipinUnavailable,
)

FIXTURES = Path(__file__).parent / "fixtures"
PII_MARKERS = ("李招聘", "王招聘", "bossName", "bossInfo", "securityId")


def _joblist():
    return json.loads((FIXTURES / "zhipin_joblist.json").read_text(encoding="utf-8"))


def _details():
    return json.loads((FIXTURES / "zhipin_details.json").read_text(encoding="utf-8"))


def _collector(**kwargs) -> ZhipinCollector:
    defaults = {
        "enabled": True,
        "limiter": RateLimiter(0),
        "keywords": ("后端",),
        "cities": (("北京", "101010100"),),
        "max_items": 10,
        "max_pages": 1,
    }
    defaults.update(kwargs)
    return ZhipinCollector(**defaults)


def _hooks(joblist=None, details=None):
    listing = joblist if joblist is not None else _joblist()
    detail_map = details if details is not None else _details()

    def fetch_joblist(keyword: str, city_code: str, page: int):
        assert keyword == "后端"
        assert city_code == "101010100"
        assert page == 1
        return 200, listing

    def fetch_detail(job: dict):
        sid = job["securityId"]
        return 200, detail_map[sid]

    return fetch_joblist, fetch_detail


def test_disabled_zero_network():
    def boom(*_a, **_k):
        raise AssertionError("enabled=False 时不得发请求")

    snaps = list(
        ZhipinCollector(
            enabled=False,
            limiter=RateLimiter(0),
            fetch_joblist=boom,
            fetch_detail=boom,
        ).collect()
    )
    assert snaps == []


def test_joblist_plus_detail_builds_description():
    fetch_joblist, fetch_detail = _hooks()
    snaps = list(_collector(fetch_joblist=fetch_joblist, fetch_detail=fetch_detail).collect())
    assert len(snaps) == 2
    first = snaps[0]
    job = first.payload["job"]
    assert first.source_id == "zhipin"
    assert job["jobName"] == "后端开发工程师"
    assert job["salaryDesc"] == "20-35K"
    assert "Java" in job["skills"]
    assert "岗位职责" in job["postDescription"]
    assert "Spring Boot" in job["postDescription"]
    assert job["description"] == job["postDescription"]
    assert first.url.endswith("/job_detail/aabbccddee0011223344556677889900.html")
    blob = json.dumps(first.payload, ensure_ascii=False)
    for marker in PII_MARKERS:
        assert marker not in blob
    assert first.content_hash == snaps[0].content_hash
    assert snaps[0].content_hash != snaps[1].content_hash


def test_list_skills_are_not_a_substitute_for_jd():
    listing = _joblist()
    listing["zpData"]["jobList"] = listing["zpData"]["jobList"][:1]
    details = _details()

    def fetch_joblist(keyword, city_code, page):
        return 200, listing

    def fetch_detail(job):
        return 200, details[job["securityId"]]

    snaps = list(_collector(fetch_joblist=fetch_joblist, fetch_detail=fetch_detail).collect())
    job = snaps[0].payload["job"]
    assert job["skills"] == ["Java", "Spring", "MySQL"]
    assert "任职要求" in job["postDescription"]
    assert len(job["postDescription"]) > len(" ".join(job["skills"]))


def test_code_37_halts():
    body = {
        "code": 37,
        "message": "您的环境存在异常.",
        "zpData": {"seed": "x", "ts": 1, "name": "5e1648a1"},
    }
    collector = _collector(
        fetch_joblist=lambda *_a: (200, body),
        fetch_detail=lambda *_a: (200, {}),
    )
    with pytest.raises(ZhipinHalted, match="环境存在异常"):
        list(collector.collect())


def test_captcha_html_halts():
    collector = _collector(
        fetch_joblist=lambda *_a: (200, "<html>请完成滑动验证后继续</html>"),
        fetch_detail=lambda *_a: (200, {}),
    )
    with pytest.raises(ZhipinHalted, match="验证码"):
        list(collector.collect())


def test_http_error_halts():
    collector = _collector(
        fetch_joblist=lambda *_a: (403, "forbidden"),
        fetch_detail=lambda *_a: (200, {}),
    )
    with pytest.raises(ZhipinHalted, match="403"):
        list(collector.collect())


def test_missing_salary_is_unavailable():
    listing = _joblist()
    for job in listing["zpData"]["jobList"]:
        job["salaryDesc"] = ""

    collector = _collector(
        fetch_joblist=lambda *_a: (200, listing),
        fetch_detail=lambda job: (200, _details()[job["securityId"]]),
    )
    with pytest.raises(ZhipinUnavailable, match="salaryDesc"):
        list(collector.collect())


def test_missing_playwright(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.collectors.zhipin.sync_playwright", None)
    state = tmp_path / "zhipin.json"
    state.write_text("{}", encoding="utf-8")
    collector = _collector(storage_state=state)
    with pytest.raises(ZhipinUnavailable, match="Playwright"):
        list(collector.collect())


def test_cdp_down_and_missing_storage(tmp_path: Path, monkeypatch):
    class FakePlaywright:
        class chromium:
            @staticmethod
            def connect_over_cdp(url):
                raise ConnectionError("refused")

            @staticmethod
            def launch(headless=True):
                raise AssertionError("无登录态时不得 launch")

        def start(self):
            return self

        def stop(self):
            return None

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    monkeypatch.setattr("app.collectors.zhipin.sync_playwright", lambda: FakePlaywright())
    collector = _collector(storage_state=tmp_path / "missing.json")
    with pytest.raises(ZhipinUnavailable, match="登录态"):
        list(collector.collect())


def test_playwright_cdp_happy_path(monkeypatch):
    listing = _joblist()
    listing["zpData"]["jobList"] = listing["zpData"]["jobList"][:1]
    details = _details()
    calls: list[str] = []

    class FakeResponse:
        status = 200

    class FakePage:
        def goto(self, url, wait_until=None):
            assert "zhipin.com" in url
            return FakeResponse()

        def content(self):
            return "<html><body>职位搜索</body></html>"

        def evaluate(self, js, url):
            calls.append(url)
            if "joblist.json" in url:
                return {"status": 200, "body": json.dumps(listing, ensure_ascii=False)}
            if "detail.json" in url:
                return {
                    "status": 200,
                    "body": json.dumps(details["sec_demo_java_001"], ensure_ascii=False),
                }
            raise AssertionError(url)

        def close(self):
            return None

    class FakeContext:
        def new_page(self):
            return FakePage()

    class FakeBrowser:
        contexts = [FakeContext()]

        def close(self):
            raise AssertionError("不得关闭用户 Chrome")

    class FakeChromium:
        def connect_over_cdp(self, url):
            assert "9222" in url
            return FakeBrowser()

        def launch(self, headless=True):
            raise AssertionError("CDP 可用时不得 launch")

    class FakePlaywright:
        chromium = FakeChromium()

        def start(self):
            return self

        def stop(self):
            return None

    monkeypatch.setattr("app.collectors.zhipin.sync_playwright", lambda: FakePlaywright())
    snaps = list(_collector().collect())
    assert len(snaps) == 1
    assert "岗位职责" in snaps[0].payload["job"]["postDescription"]
    assert any("joblist.json" in u for u in calls)
    assert any("detail.json" in u and "securityId=sec_demo_java_001" in u for u in calls)
