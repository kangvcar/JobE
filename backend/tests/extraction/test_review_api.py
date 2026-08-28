from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routers.review import router
from app.domain.models import PublishState, TextSpan
from app.extraction.deps import ExtractionDeps, set_deps
from app.extraction.store import ClaimRecord, MemoryExtractionStore, make_evidence, new_id
from tests.extraction.conftest import FIXTURE_DIR, FakeLLM


def _client(store: MemoryExtractionStore, llm: FakeLLM) -> TestClient:
    set_deps(
        ExtractionDeps(
            store=store,
            llm=llm,
            reviewer_llm=FakeLLM(
                {"verdict": "supported", "reason": "ok", "cited_evidence_ids": []}
            ),
            ontology_dir=FIXTURE_DIR,
            ontology_version="v0",
        )
    )
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_upload_resume_and_unverified_queue(store: MemoryExtractionStore):
    llm = FakeLLM(
        [
            {"name": "张三"},
            {"skills": [{"surface_form": "Flink", "quote": "Flink"}]},
            {"skill_id": None, "confidence": 0.1},
        ]
    )
    client = _client(store, llm)
    resp = client.post(
        "/api/review/resumes",
        files={"file": ("cv.txt", "张三\n技能专长\nFlink".encode(), "text/plain")},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["doc_id"]
    assert body["candidates"]

    q = client.get("/api/review/unverified")
    assert q.status_code == 200
    items = q.json()["items"]
    assert items
    item_id = items[0]["id"]

    ev = client.get(f"/api/review/claims/{item_id}/evidence")
    assert ev.status_code == 200
    data = ev.json()
    assert data["evidence"]
    assert "start" in data["evidence"][0]
    assert data["evidence"][0]["quote"]

    decided = client.post(
        f"/api/review/unverified/{item_id}/decide",
        json={"accept": True, "decided_by": "expert", "skill_id": "sk.flink"},
    )
    assert decided.status_code == 200
    assert decided.json()["state"] == "published"
    assert store.get_alias("Flink") is not None

    empty = client.get("/api/review/unverified")
    assert empty.json()["items"] == []


def test_empty_upload_rejected(store: MemoryExtractionStore):
    client = _client(store, FakeLLM())
    resp = client.post("/api/review/resumes", files={"file": ("cv.txt", b"", "text/plain")})
    assert resp.status_code == 400


def test_missing_claim_404(store: MemoryExtractionStore):
    client = _client(store, FakeLLM())
    assert client.get("/api/review/claims/nope/evidence").status_code == 404
    assert (
        client.post(
            "/api/review/unverified/nope/decide",
            json={"accept": False, "decided_by": "x"},
        ).status_code
        == 404
    )


def test_auto_review_endpoint(store: MemoryExtractionStore):
    span = TextSpan(doc_id="d", start=0, end=6)
    ev = make_evidence(source_id="s", span=span, quote="Python", extractor="t", confidence=0.9)
    store.save_evidence(ev)
    cid = new_id()
    store.put_claim(ClaimRecord(id=cid, kind="skill", text="掌握 Python", evidence_ids=[ev.id]))
    client = _client(store, FakeLLM())
    resp = client.post(f"/api/review/claims/{cid}/review")
    assert resp.status_code == 200
    assert resp.json()["verdict"] == "supported"


def test_reject_does_not_publish(store: MemoryExtractionStore):
    store.put_claim(ClaimRecord(id="c1", kind="new_skill", text="Foo", evidence_ids=[]))
    client = _client(store, FakeLLM())
    resp = client.post(
        "/api/review/unverified/c1/decide",
        json={"accept": False, "decided_by": "expert"},
    )
    assert resp.json()["state"] == PublishState.REJECTED.value
    assert store.get_alias("Foo") is None
