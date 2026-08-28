"""路由最小可用：趋势、领先滞后、通胀、能力变更、新兴岗位两区。"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routers.evolution import router
from app.evolution.cluster import Cooccurrence
from tests.evolution.factories import make_obs, series_from_counts


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_skill_trend_endpoint() -> None:
    counts = [25] * 8 + [200] * 4 + [25] * 8
    series = series_from_counts("pytorch", counts, 500)
    res = _client().post(
        "/api/evolution/skills/trend",
        json={"series": [o.model_dump() for o in series], "source_id": "boss"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["skill_id"] == "pytorch"
    assert body["bursts"]
    assert body["label"] in {"hype", "growth", "stable", "decline"}


def test_lead_lag_endpoint() -> None:
    n = 20
    lead = [0] * n
    lead[4:8] = [150, 550, 600, 200]
    lag = [0] * n
    lag[7:11] = [150, 550, 600, 200]
    leading = series_from_counts("cuda", lead, 1000)
    lagging = series_from_counts("cuda", lag, 1000)
    res = _client().post(
        "/api/evolution/lead-lag",
        json={
            "leading": [o.model_dump() for o in leading],
            "lagging": [o.model_dump() for o in lagging],
            "leading_source_id": "github",
            "lagging_source_id": "boss",
        },
    )
    assert res.status_code == 200
    body = res.json()
    assert body is not None
    assert body["lag_periods"] == 3


def test_inflation_endpoint() -> None:
    loads = [
        {
            "period": f"202{i}Q1",
            "n_postings": 100,
            "n_skill_mentions": 400 + 80 * i,
            "total_text_chars": 20000,
        }
        for i in range(6)
    ]
    res = _client().post("/api/evolution/inflation", json={"loads": loads})
    assert res.status_code == 200
    assert res.json()["report"]["inflated"] is True


def test_role_changes_endpoint() -> None:
    before = [make_obs("java", "2023Q4", 40, 100, role_id="backend", weight=0.4)]
    after = [
        make_obs("java", "2024Q1", 40, 100, role_id="backend", weight=0.4),
        make_obs("kafka", "2024Q1", 30, 100, role_id="backend", weight=0.3),
    ]
    res = _client().post(
        "/api/evolution/roles/changes",
        json={
            "role_id": "backend",
            "before": [o.model_dump() for o in before],
            "after": [o.model_dump() for o in after],
            "recorded_at": datetime(2024, 4, 1, tzinfo=UTC).isoformat(),
            "evidence_by_skill": {"kafka": ["e1"]},
        },
    )
    assert res.status_code == 200
    kinds = {c["competency_id"]: c["kind"] for c in res.json()}
    assert kinds["kafka"] == "added"


def test_emerging_endpoint_two_zones() -> None:
    new = ["llm", "rag", "agent", "eval"]
    old = ["java", "spring", "mysql"]
    edges: list[dict] = []
    for period in ("2023Q1", "2023Q2", "2023Q3", "2023Q4"):
        for i, a in enumerate(old):
            for b in old[i + 1 :]:
                edges.append(Cooccurrence("boss", period, a, b, 2.0).__dict__)
    for period in ("2024Q1", "2024Q2", "2024Q3", "2024Q4"):
        for src in ("boss", "liepin"):
            for i, a in enumerate(new):
                for b in new[i + 1 :]:
                    edges.append(Cooccurrence(src, period, a, b, 4.0).__dict__)
    bursts = [
        {
            "skill_id": s,
            "source_id": "boss",
            "start_period": "2024Q1",
            "end_period": "2024Q4",
            "level": 1,
            "weight": 4.0,
        }
        for s in new
    ]
    res = _client().post(
        "/api/evolution/emerging",
        json={
            "edges": edges,
            "bursts": bursts,
            "existing_roles": [{"role_id": "backend", "skill_ids": old}],
            "catalog": [{"code": "4-05-02-01", "name": "软件开发工程师", "skill_ids": old}],
            "ontology_version": "v0",
            "current_period": "2024Q4",
        },
    )
    assert res.status_code == 200
    body = res.json()
    assert "publish_queue" in body
    assert "watch_zone" in body
    assert body["publish_queue"] or body["watch_zone"]
