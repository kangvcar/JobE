from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import httpx
import respx

from app.collectors.lever import LeverCollector, load_boards
from app.collectors.rate_limit import RateLimiter

FIXTURES = Path(__file__).parent / "fixtures"


def test_load_boards_skips_comments(tmp_path: Path):
    path = tmp_path / "boards.txt"
    path.write_text("# skip\n\npalantir\tPalantir\nzoox\n", encoding="utf-8")
    assert load_boards(path) == [("palantir", "Palantir"), ("zoox", "zoox")]


def test_load_boards_missing_file(tmp_path: Path):
    assert load_boards(tmp_path / "nope.txt") == []


@respx.mock
def test_lever_collects_jobs_as_snapshots():
    body = json.loads((FIXTURES / "lever_jobs.json").read_text(encoding="utf-8"))
    respx.route(method="GET", host="api.lever.co").mock(
        return_value=httpx.Response(200, json=body)
    )
    snaps = list(
        LeverCollector(
            limiter=RateLimiter(0),
            max_items=10,
            boards=[("zoox", "Zoox")],
        ).collect()
    )
    assert len(snaps) == 2
    for snap in snaps:
        assert snap.source_id == "lever"
        assert snap.id.startswith("lever:")
        assert snap.payload["board_token"] == "zoox"
        assert snap.payload["board_name"] == "Zoox"
        job = snap.payload["job"]
        assert job["text"]
        assert job["description"] or job.get("descriptionPlain")
        assert job.get("categories", {}).get("location")
        assert job.get("salaryRange", {}).get("min")
        assert "jobManager" not in job
    titles = {s.payload["job"]["text"] for s in snaps}
    assert "Autonomy System Test Engineer" in titles


@respx.mock
def test_lever_since_filters_by_created_at():
    body = json.loads((FIXTURES / "lever_jobs.json").read_text(encoding="utf-8"))
    respx.route(method="GET", host="api.lever.co").mock(
        return_value=httpx.Response(200, json=body)
    )
    # fixture createdAt: 1777936261125 (~2026-05) and 1757985728853 (~2025-09)
    snaps = list(
        LeverCollector(
            limiter=RateLimiter(0),
            boards=[("zoox", "Zoox")],
        ).collect(since=date(2026, 1, 1))
    )
    assert len(snaps) == 1
    assert snaps[0].payload["job"]["text"] == "Autonomy System Test Engineer"


@respx.mock
def test_lever_empty_board_list_yields_nothing():
    snaps = list(LeverCollector(limiter=RateLimiter(0), boards=[]).collect())
    assert snaps == []
