"""既有岗位能力变更。"""

from __future__ import annotations

from datetime import UTC, datetime

from app.domain.models import ChangeKind
from app.evolution.drift import detect_competency_changes
from tests.evolution.factories import make_obs


def test_detects_added_removed_modified() -> None:
    before = [
        make_obs("java", "2023Q4", 40, 100, role_id="backend", weight=0.40),
        make_obs("mysql", "2023Q4", 30, 100, role_id="backend", weight=0.30),
        make_obs("redis", "2023Q4", 8, 100, role_id="backend", weight=0.08),
    ]
    after = [
        make_obs("java", "2024Q1", 42, 100, role_id="backend", weight=0.42),
        make_obs("kafka", "2024Q1", 25, 100, role_id="backend", weight=0.25),
        make_obs("redis", "2024Q1", 20, 100, role_id="backend", weight=0.20),
    ]
    recorded = datetime(2024, 4, 1, tzinfo=UTC)
    changes = detect_competency_changes(
        "backend",
        before,
        after,
        recorded_at=recorded,
        evidence_by_skill={"kafka": ["e1"], "mysql": ["e2"], "redis": ["e3"]},
    )
    kinds = {c.competency_id: c.kind for c in changes}
    assert kinds["kafka"] == ChangeKind.ADDED
    assert kinds["mysql"] == ChangeKind.REMOVED
    assert kinds["redis"] == ChangeKind.MODIFIED
    assert "java" not in kinds
    kafka = next(c for c in changes if c.competency_id == "kafka")
    assert kafka.reason
    assert kafka.evidence_ids == ["e1"]
    assert kafka.occurred_on.year == 2024
    assert kafka.recorded_at == recorded


def test_rejects_cross_ontology_version() -> None:
    before = [make_obs("java", "2023Q4", 40, 100, role_id="backend", ontology_version="v0")]
    after = [make_obs("java", "2024Q1", 10, 100, role_id="backend", ontology_version="v1")]
    recorded = datetime(2024, 4, 1, tzinfo=UTC)
    assert detect_competency_changes("backend", before, after, recorded_at=recorded) == []


def test_empty_slices_yield_no_changes() -> None:
    recorded = datetime(2024, 4, 1, tzinfo=UTC)
    assert detect_competency_changes("backend", [], [], recorded_at=recorded) == []
