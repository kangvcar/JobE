from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import httpx
import respx

from app.collectors.greenhouse import GreenhouseCollector, load_boards
from app.collectors.rate_limit import RateLimiter

FIXTURES = Path(__file__).parent / "fixtures"


def test_load_boards_skips_comments(tmp_path: Path):
    path = tmp_path / "boards.txt"
    path.write_text("# skip\n\nstripe\tStripe\ndatabricks\n", encoding="utf-8")
    assert load_boards(path) == [("stripe", "Stripe"), ("databricks", "databricks")]


def test_load_boards_missing_file(tmp_path: Path):
    assert load_boards(tmp_path / "nope.txt") == []


@respx.mock
def test_greenhouse_collects_jobs_as_snapshots():
    body = json.loads((FIXTURES / "greenhouse_jobs.json").read_text(encoding="utf-8"))
    respx.route(method="GET", host="boards-api.greenhouse.io").mock(
        return_value=httpx.Response(200, json=body)
    )
    snaps = list(
        GreenhouseCollector(
            limiter=RateLimiter(0),
            max_items=10,
            boards=[("stripe", "Stripe")],
        ).collect()
    )
    assert len(snaps) == 2
    for snap in snaps:
        assert snap.source_id == "greenhouse"
        assert snap.id.startswith("greenhouse:")
        assert snap.payload["board_token"] == "stripe"
        assert snap.payload["board_name"] == "Stripe"
        job = snap.payload["job"]
        assert job["title"]
        assert job["content"]
        assert job["company_name"] == "Stripe"
        assert job.get("location", {}).get("name")
        assert "jobManager" not in job
    titles = {s.payload["job"]["title"] for s in snaps}
    assert "Account Executive, AI Sales" in titles


@respx.mock
def test_greenhouse_since_filters_by_updated_at():
    body = json.loads((FIXTURES / "greenhouse_jobs.json").read_text(encoding="utf-8"))
    respx.route(method="GET", host="boards-api.greenhouse.io").mock(
        return_value=httpx.Response(200, json=body)
    )
    snaps = list(
        GreenhouseCollector(
            limiter=RateLimiter(0),
            boards=[("stripe", "Stripe")],
        ).collect(since=date(2026, 8, 20))
    )
    assert len(snaps) == 1
    assert snaps[0].payload["job"]["title"] == "Account Executive, AI Sales"


@respx.mock
def test_greenhouse_empty_board_list_yields_nothing():
    snaps = list(GreenhouseCollector(limiter=RateLimiter(0), boards=[]).collect())
    assert snaps == []
