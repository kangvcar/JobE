from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


def test_list_sources_includes_license():
    client = TestClient(app)
    data = client.get("/api/collect/sources").json()
    ids = {row["id"] for row in data}
    assert {
        "mohrss",
        "moka",
        "liepin",
        "zhipin",
        "greenhouse",
        "lever",
        "ashby",
        "jobhive_beisen",
        "jobhive_moka",
    } <= ids
    mohrss = next(row for row in data if row["id"] == "mohrss")
    assert mohrss["requires_login"] is False
    assert mohrss["license"]
    liepin = next(row for row in data if row["id"] == "liepin")
    assert liepin["requires_login"] is True


def test_status_starts_idle():
    client = TestClient(app)
    data = client.get("/api/collect/status").json()
    assert "state" in data
