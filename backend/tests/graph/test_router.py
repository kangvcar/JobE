from __future__ import annotations

from datetime import UTC, date, datetime
from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routers import graph as graph_router
from app.domain.models import ChangeKind, CompetencyChange, PublishState


def _client(svc: MagicMock, repo: MagicMock) -> TestClient:
    app = FastAPI()
    app.include_router(graph_router.router)
    app.dependency_overrides[graph_router.get_query_service] = lambda: svc
    app.dependency_overrides[graph_router.get_repository] = lambda: repo
    return TestClient(app)


def test_panorama_and_compare_endpoints() -> None:
    svc = MagicMock()
    repo = MagicMock()
    svc.panorama.return_value = {
        "nodes": [{"data": {"id": "role:r1", "label": "后端", "type": "role"}}],
        "edges": [],
    }
    svc.compare_roles.return_value = {"only_a": [], "only_b": [], "both": []}
    client = _client(svc, repo)

    res = client.get("/api/graph/panorama", params={"period": "2026Q1", "family_id": "backend"})
    assert res.status_code == 200
    assert res.json()["nodes"][0]["data"]["type"] == "role"
    svc.panorama.assert_called_once()

    res = client.get(
        "/api/graph/compare-roles",
        params={"role_a": "ra", "role_b": "rb", "period": "2026Q1"},
    )
    assert res.status_code == 200
    svc.compare_roles.assert_called_once_with("ra", "rb", "2026Q1")


def test_snapshot_and_diff_endpoints() -> None:
    svc = MagicMock()
    repo = MagicMock()
    repo.snapshot_at.return_value = {
        "period": "2026Q1",
        "roles": [],
        "skills": [],
        "requirements": [],
    }
    repo.diff.return_value = [
        CompetencyChange(
            id="x",
            role_id="r1",
            competency_id="c1",
            kind=ChangeKind.ADDED,
            after="{}",
            reason="新增",
            occurred_on=date(2026, 6, 30),
            recorded_at=datetime(2026, 7, 1, tzinfo=UTC),
            state=PublishState.PUBLISHED,
        )
    ]
    client = _client(svc, repo)
    assert client.get("/api/graph/snapshot", params={"period": "2026Q1"}).status_code == 200
    diff = client.get("/api/graph/diff", params={"period_a": "2026Q1", "period_b": "2026Q2"})
    assert diff.status_code == 200
    assert diff.json()[0]["kind"] == "added"


def test_role_and_skill_detail_404_and_400() -> None:
    svc = MagicMock()
    repo = MagicMock()
    svc.role_panorama.return_value = None
    svc.skill_cooccurrence.return_value = {
        "skill": None,
        "graph": {"nodes": [], "edges": []},
    }
    client = _client(svc, repo)
    assert client.get("/api/graph/roles/missing/panorama").status_code == 404
    assert client.get("/api/graph/skills/missing/cooccurrence").status_code == 404

    svc.role_panorama.side_effect = ValueError("时间片必须是 YYYYQn，收到：bad")
    assert client.get("/api/graph/roles/r1/panorama", params={"period": "bad"}).status_code == 400

    svc.panorama.side_effect = ValueError("重要度层级必须是 high/medium/low，收到：x")
    assert (
        client.get(
            "/api/graph/panorama", params={"period": "2026Q1", "importance_tier": "x"}
        ).status_code
        == 400
    )

    svc.role_panorama.side_effect = None
    svc.role_panorama.return_value = {"role": {"id": "r1"}, "competencies": []}
    svc.skill_cooccurrence.side_effect = None
    svc.skill_cooccurrence.return_value = {
        "skill": {"id": "s1", "name": "Python"},
        "graph": {"nodes": [], "edges": []},
    }
    assert client.get("/api/graph/roles/r1/panorama").status_code == 200
    assert client.get("/api/graph/skills/s1/cooccurrence", params={"hops": 2}).status_code == 200


def test_snapshot_diff_compare_400() -> None:
    svc = MagicMock()
    repo = MagicMock()
    repo.snapshot_at.side_effect = ValueError("bad period")
    repo.diff.side_effect = ValueError("bad period")
    svc.compare_roles.side_effect = ValueError("bad period")
    svc.skill_cooccurrence.side_effect = ValueError("共现子图只支持 1 或 2 跳")
    client = _client(svc, repo)
    assert client.get("/api/graph/snapshot", params={"period": "x"}).status_code == 400
    assert (
        client.get("/api/graph/diff", params={"period_a": "2026Q1", "period_b": "x"}).status_code
        == 400
    )
    assert (
        client.get(
            "/api/graph/compare-roles",
            params={"role_a": "a", "role_b": "b", "period": "x"},
        ).status_code
        == 400
    )
    assert client.get("/api/graph/skills/s1/cooccurrence", params={"hops": 1}).status_code == 400


def test_driver_factories_use_settings() -> None:
    graph_router._driver.cache_clear()
    fake_driver = object()
    with (
        patch("app.api.routers.graph.create_driver", return_value=fake_driver),
        patch("app.api.routers.graph.get_settings") as settings,
    ):
        settings.return_value.ontology_version = "v0"
        executor = graph_router.get_executor()
        assert executor._driver is fake_driver
        repo = graph_router.get_repository(executor)
        assert repo._ontology_version == "v0"
        svc = graph_router.get_query_service(executor)
        assert svc._ontology_version == "v0"
    graph_router._driver.cache_clear()
