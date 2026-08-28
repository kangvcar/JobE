from __future__ import annotations

import json
from pathlib import Path

import httpx
import respx

from app.collectors.mohrss import MohrssCollector, parse_findjoblist
from app.collectors.rate_limit import RateLimiter

FIXTURES = Path(__file__).parent / "fixtures"
PII_KEYS = {"aae004", "aae005"}


def _keys(obj) -> set[str]:
    found: set[str] = set()
    if isinstance(obj, dict):
        found.update(obj)
        for value in obj.values():
            found |= _keys(value)
    elif isinstance(obj, list):
        for value in obj:
            found |= _keys(value)
    return found


def test_parse_findjoblist_reads_hidden_json():
    html = (FIXTURES / "mohrss_list.html").read_text(encoding="utf-8")
    items = parse_findjoblist(html)
    assert len(items) == 2
    assert len(items[0]) == 93
    assert items[0]["acb22a"] == "Java开发工程师"
    assert "aae004" in items[0]


@respx.mock
def test_mohrss_drops_pii_before_snapshot():
    html = (FIXTURES / "mohrss_list.html").read_text(encoding="utf-8")
    empty = (FIXTURES / "mohrss_list_empty.html").read_text(encoding="utf-8")
    respx.route(method="GET", host="job.mohrss.gov.cn").mock(
        side_effect=[
            httpx.Response(200, text=html),
            httpx.Response(200, text=empty),
        ]
    )
    snaps = list(MohrssCollector(limiter=RateLimiter(0), max_items=20).collect())
    assert len(snaps) == 2
    blob = json.dumps(snaps[0].payload, ensure_ascii=False)
    assert "aae004" not in blob
    assert "aae005" not in blob
    assert "13800138001" not in blob
    assert "张1测试" not in blob
    for snap in snaps:
        assert PII_KEYS.isdisjoint(_keys(snap.payload))
        assert snap.source_id == "mohrss"
        assert snap.payload["acb22a"]
        assert snap.payload["md5"]


@respx.mock
def test_mohrss_since_and_max_items():
    html = (FIXTURES / "mohrss_list.html").read_text(encoding="utf-8")
    empty = (FIXTURES / "mohrss_list_empty.html").read_text(encoding="utf-8")
    respx.route(method="GET", host="job.mohrss.gov.cn").mock(
        side_effect=[
            httpx.Response(200, text=html),
            httpx.Response(200, text=empty),
        ]
    )
    from datetime import date

    snaps = list(
        MohrssCollector(limiter=RateLimiter(0), max_items=1).collect(since=date(2026, 8, 3))
    )
    assert len(snaps) == 1
    assert snaps[0].payload["md5"] == "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
