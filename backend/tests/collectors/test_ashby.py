from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import httpx
import respx

from app.collectors.ashby import AshbyCollector, load_boards
from app.collectors.rate_limit import RateLimiter

FIXTURES = Path(__file__).parent / "fixtures"


def test_load_boards_skips_comments(tmp_path: Path):
    path = tmp_path / "boards.txt"
    path.write_text("# skip\n\nopenai\tOpenAI\ncursor\n", encoding="utf-8")
    assert load_boards(path) == [("openai", "OpenAI"), ("cursor", "cursor")]


def test_load_boards_missing_file(tmp_path: Path):
    assert load_boards(tmp_path / "nope.txt") == []


@respx.mock
def test_ashby_collects_jobs_as_snapshots():
    body = json.loads((FIXTURES / "ashby_jobs.json").read_text(encoding="utf-8"))
    respx.route(method="GET", host="api.ashbyhq.com").mock(
        return_value=httpx.Response(200, json=body)
    )
    snaps = list(
        AshbyCollector(
            limiter=RateLimiter(0),
            max_items=10,
            boards=[("openai", "OpenAI")],
        ).collect()
    )
    assert len(snaps) == 2
    for snap in snaps:
        assert snap.source_id == "ashby"
        assert snap.id.startswith("ashby:")
        assert snap.payload["board_token"] == "openai"
        assert snap.payload["board_name"] == "OpenAI"
        job = snap.payload["job"]
        assert job["title"]
        assert job["descriptionHtml"] or job.get("descriptionPlain")
        assert job.get("location")
        assert job.get("compensation")
        assert "jobManager" not in job
    titles = {s.payload["job"]["title"] for s in snaps}
    assert "Research Engineer" in titles


@respx.mock
def test_ashby_since_filters_by_published_at():
    body = json.loads((FIXTURES / "ashby_jobs.json").read_text(encoding="utf-8"))
    respx.route(method="GET", host="api.ashbyhq.com").mock(
        return_value=httpx.Response(200, json=body)
    )
    snaps = list(
        AshbyCollector(
            limiter=RateLimiter(0),
            boards=[("openai", "OpenAI")],
        ).collect(since=date(2026, 1, 1))
    )
    assert len(snaps) == 1
    assert snaps[0].payload["job"]["title"] == (
        "Technical Program Manager, Compute Infrastructure"
    )


@respx.mock
def test_ashby_empty_board_list_yields_nothing():
    snaps = list(AshbyCollector(limiter=RateLimiter(0), boards=[]).collect())
    assert snaps == []
