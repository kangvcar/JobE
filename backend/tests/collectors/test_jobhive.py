from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from app.api.routers.collect import _collectors
from app.collectors.jobhive import JobhiveCollector
from app.collectors.postings import posting_from_snapshot
from app.domain.models import Snapshot

FIXTURES = Path(__file__).parent / "fixtures"
SAMPLE = FIXTURES / "jobhive.sample.jsonl"


def test_jobhive_beisen_reads_local_jsonl_and_skips_moka():
    snaps = list(
        JobhiveCollector(ats="beisen", path=SAMPLE, max_items=20, allow_download=False).collect()
    )
    assert snaps
    assert all(s.source_id == "jobhive_beisen" for s in snaps)
    assert all(s.payload.get("ats_type") == "beisen" for s in snaps)
    titles = {s.payload["title"] for s in snaps}
    assert "ios/安卓开发工程师" in titles
    assert "应用技术工程师" not in titles
    ifly = next(s for s in snaps if s.payload["title"] == "ios/安卓开发工程师")
    assert ifly.url == "https://iflytek.zhiye.com/portal/jobs/190822459"
    assert ifly.content_hash
    assert "负责iOS" in ifly.payload["description"]


def test_jobhive_moka_reads_slug_company():
    snaps = list(
        JobhiveCollector(ats="moka", path=SAMPLE, max_items=20, allow_download=False).collect()
    )
    assert len(snaps) == 1
    snap = snaps[0]
    assert snap.source_id == "jobhive_moka"
    assert snap.payload["company"] == "hanscnc"
    posting = posting_from_snapshot(snap)
    assert posting.title == "应用技术工程师"
    assert posting.company == "hanscnc"
    assert posting.city == "宝安区, 广东, 中国"
    assert posting.description
    assert "软硬件测试" in posting.description
    assert posting.salary_min is None
    assert posting.salary_max is None


def test_jobhive_missing_local_file_does_not_download():
    snaps = list(
        JobhiveCollector(
            ats="beisen",
            path=Path("/tmp/jobhive-does-not-exist.jsonl"),
            max_items=5,
            allow_download=False,
        ).collect()
    )
    assert snaps == []


def test_jobhive_max_items_caps_yield():
    snaps = list(
        JobhiveCollector(ats="beisen", path=SAMPLE, max_items=2, allow_download=False).collect()
    )
    assert len(snaps) == 2


def test_jobhive_maps_description_and_negotiable_salary():
    snap = next(
        JobhiveCollector(ats="beisen", path=SAMPLE, max_items=20, allow_download=False).collect()
    )
    posting = posting_from_snapshot(snap)
    assert posting.source_id == "jobhive_beisen"
    assert posting.title
    assert posting.description
    assert posting.published_at is not None


def test_jobhive_salary_mianyi_is_none():
    snaps = {
        s.payload["title"]: s
        for s in JobhiveCollector(
            ats="beisen", path=SAMPLE, max_items=20, allow_download=False
        ).collect()
    }
    posting = posting_from_snapshot(snaps["ios/安卓开发工程师"])
    assert posting.salary_min is None
    assert posting.salary_max is None
    assert posting.city == "安徽省·合肥市"
    assert posting.company == "iFLYTEK"


def test_jobhive_salary_k_per_month():
    snaps = {
        s.payload["title"]: s
        for s in JobhiveCollector(
            ats="beisen", path=SAMPLE, max_items=20, allow_download=False
        ).collect()
    }
    posting = posting_from_snapshot(snaps["后端开发工程师"])
    assert posting.salary_min == 10000
    assert posting.salary_max == 15000


def test_jobhive_salary_wan_per_year_to_monthly():
    snaps = {
        s.payload["title"]: s
        for s in JobhiveCollector(
            ats="beisen", path=SAMPLE, max_items=20, allow_download=False
        ).collect()
    }
    posting = posting_from_snapshot(snaps["算法工程师"])
    assert posting.salary_min == 16_666
    assert posting.salary_max == 25_000


def test_jobhive_structured_salary_below_1000_is_k():
    payload = {
        "url": "https://example.zhiye.com/j/9",
        "title": "前端开发",
        "company": "示例",
        "ats_type": "beisen",
        "ats_id": 9,
        "location": "杭州市",
        "salary_min": 20,
        "salary_max": 35,
        "salary_summary": None,
        "description": "写 React。",
        "posted_at": "2026-07-01",
    }
    snap = Snapshot(
        id="x",
        source_id="jobhive_beisen",
        fetched_at=datetime(2026, 8, 28, tzinfo=UTC),
        url=payload["url"],
        content_hash="a" * 64,
        payload=payload,
    )
    posting = posting_from_snapshot(snap)
    assert posting.salary_min == 20000
    assert posting.salary_max == 35000
    assert posting.description == "写 React。"


def test_jobhive_payload_is_json_serializable():
    snap = next(
        JobhiveCollector(ats="beisen", path=SAMPLE, max_items=1, allow_download=False).collect()
    )
    json.dumps(snap.payload, ensure_ascii=False)


def test_default_collect_run_omits_jobhive():
    out = _collectors(10, 0, liepin_enabled=False)
    assert "jobhive_beisen" not in out
    assert "jobhive_moka" not in out
    explicit = _collectors(10, 0, liepin_enabled=False, source_id="jobhive_beisen")
    assert "jobhive_beisen" in explicit
