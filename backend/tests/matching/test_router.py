"""路由最小可用：诊断、路径、反向推荐。"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routers.match import router
from app.domain.models import Role
from app.matching.service import MatchingService, set_matching_service

from .fakes import FakeBursts, FakePrereqs, FakeRequirements, numbered_specs, profile_holding


def _client() -> TestClient:
    svc = MatchingService(
        FakeRequirements(
            roles={
                "r1": Role(id="r1", name="机器学习工程师"),
                "r2": Role(id="r2", name="数据工程师"),
            },
            specs={
                "r1": numbered_specs(10),
                "r2": numbered_specs(4),
            },
        ),
        FakePrereqs(),
        FakeBursts(),
    )
    set_matching_service(svc)
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def teardown_function() -> None:
    set_matching_service(None)


def test_diagnose_returns_judgments():
    client = _client()
    profile = profile_holding([f"s{i:02d}" for i in range(9)])
    response = client.post(
        "/api/match/diagnose",
        json={"profile": profile.model_dump(mode="json"), "role_id": "r1"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["tier"] == "strong"
    assert len(body["judgments"]) == 10
    assert body["judgments"][-1]["skill_id"] == "s09"
    assert body["judgments"][-1]["satisfied"] is False
    assert "coverage" in body and "score" in body


def test_diagnose_unknown_role_404():
    client = _client()
    profile = profile_holding([])
    response = client.post(
        "/api/match/diagnose",
        json={"profile": profile.model_dump(mode="json"), "role_id": "missing"},
    )
    assert response.status_code == 404


def test_path_unknown_role_404():
    client = _client()
    profile = profile_holding([])
    response = client.post(
        "/api/match/path",
        json={"profile": profile.model_dump(mode="json"), "role_id": "missing"},
    )
    assert response.status_code == 404


def test_path_endpoint():
    client = _client()
    profile = profile_holding([f"s{i:02d}" for i in range(8)])
    response = client.post(
        "/api/match/path",
        json={"profile": profile.model_dump(mode="json"), "role_id": "r1"},
    )
    assert response.status_code == 200
    steps = response.json()["steps"]
    assert [s["skill_id"] for s in steps] == ["s08", "s09"]
    assert steps[0]["reason"]


def test_discover_endpoint():
    client = _client()
    profile = profile_holding([f"s{i:02d}" for i in range(10)])
    response = client.post(
        "/api/match/discover",
        json={"profile": profile.model_dump(mode="json"), "top_k": 2},
    )
    assert response.status_code == 200
    items = response.json()["items"]
    assert items[0]["role_id"] == "r1"
    assert "score" in items[0]


def test_unconfigured_service_503():
    set_matching_service(None)
    app = FastAPI()
    app.include_router(router)
    response = TestClient(app).post(
        "/api/match/discover",
        json={"profile": profile_holding([]).model_dump(mode="json")},
    )
    assert response.status_code == 503
