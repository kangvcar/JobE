from __future__ import annotations

import json
from pathlib import Path

import httpx
import respx

from app.collectors.moka import MokaCollector, load_orgs
from app.collectors.rate_limit import RateLimiter

FIXTURES = Path(__file__).parent / "fixtures"
PII_KEYS = {"jobManager", "jobHrAssistant", "jobHiringManager", "jobInterviewer"}


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


def test_load_orgs_skips_comments(tmp_path: Path):
    path = tmp_path / "orgs.txt"
    path.write_text("# skip\n\ngeely\t吉利\nmoka\n", encoding="utf-8")
    assert load_orgs(path) == [("geely", "吉利"), ("moka", "moka")]


def test_load_orgs_missing_file(tmp_path: Path):
    assert load_orgs(tmp_path / "nope.txt") == []


@respx.mock
def test_moka_drops_manager_pii():
    body = json.loads((FIXTURES / "moka_jobs.json").read_text(encoding="utf-8"))
    respx.route(method="GET", host="api.mokahr.com").mock(
        return_value=httpx.Response(200, json=body)
    )
    snaps = list(
        MokaCollector(
            limiter=RateLimiter(0),
            max_items=10,
            orgs=[("geely", "吉利")],
            modes=("social",),
        ).collect()
    )
    assert len(snaps) == 2
    for snap in snaps:
        assert PII_KEYS.isdisjoint(_keys(snap.payload))
        blob = json.dumps(snap.payload, ensure_ascii=False)
        assert "lisi@example.com" not in blob
        assert "13900139000" not in blob
        assert "李四" not in blob
        assert snap.payload["org_name"] == "吉利"
        assert snap.payload["job"]["title"]
        assert "description" in snap.payload["job"]


@respx.mock
def test_moka_empty_org_list_yields_nothing():
    snaps = list(MokaCollector(limiter=RateLimiter(0), orgs=[]).collect())
    assert snaps == []
