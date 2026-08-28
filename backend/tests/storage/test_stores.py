from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, date, datetime

from app.domain.models import Evidence, Posting, SkillObservation, Snapshot, Source, TextSpan
from app.domain.normalization import normalize_title, period_from_date
from app.storage.change_log import ChangeLogEntry, ChangeLogStore
from app.storage.evidence import PgEvidenceStore
from app.storage.observations import ObservationStore
from app.storage.postings import PgPostingStore
from app.storage.snapshots import PgSnapshotStore


class ScriptedCursor:
    def __init__(self, results: list) -> None:
        self.results = list(results)
        self.queries: list[tuple[str, object]] = []
        self._current = None
        self._i = -1

    def execute(self, sql: str, params=None) -> None:
        self.queries.append((" ".join(sql.split()), params))
        self._i += 1
        self._current = self.results[self._i] if self._i < len(self.results) else None

    def fetchone(self):
        current = self._current
        if isinstance(current, list):
            return current[0] if current else None
        return current

    def fetchall(self):
        current = self._current
        if current is None:
            return []
        if isinstance(current, list):
            return current
        return [current]

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class FakeConn:
    def __init__(self, cursor: ScriptedCursor) -> None:
        self._cursor = cursor
        self.commits = 0
        self.rollbacks = 0
        self.closed = False

    def cursor(self):
        return self._cursor

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


class FakePool:
    def __init__(self, cursor: ScriptedCursor) -> None:
        self.cursor = cursor
        self.conn = FakeConn(cursor)

    @contextmanager
    def connection(self):
        try:
            yield self.conn
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise


def _snapshot() -> Snapshot:
    return Snapshot(
        id="mohrss:abc",
        source_id="mohrss",
        fetched_at=datetime(2026, 8, 1, tzinfo=UTC),
        url="http://example.test",
        content_hash="hash1",
        payload={"acb22a": "Java"},
    )


def test_snapshot_insert_never_updates():
    cur = ScriptedCursor([{"id": "mohrss:abc"}])
    store = PgSnapshotStore(FakePool(cur))
    assert store.save(_snapshot()) == "mohrss:abc"
    sql = cur.queries[0][0]
    assert "INSERT INTO snapshots" in sql
    assert "DO NOTHING" in sql
    assert "UPDATE" not in sql


def test_snapshot_conflict_returns_existing_id():
    cur = ScriptedCursor([None, {"id": "existing"}])
    store = PgSnapshotStore(FakePool(cur))
    assert store.save(_snapshot()) == "existing"
    assert "SELECT id FROM snapshots" in cur.queries[1][0]


def test_snapshot_exists_and_iter():
    cur = ScriptedCursor(
        [
            {"x": 1},
            [
                {
                    "id": "mohrss:abc",
                    "source_id": "mohrss",
                    "fetched_at": datetime(2026, 8, 1, tzinfo=UTC),
                    "url": None,
                    "content_hash": "h",
                    "payload": {"k": 1},
                }
            ],
        ]
    )
    store = PgSnapshotStore(FakePool(cur))
    assert store.exists("h") is True
    items = list(store.iter_by_source("mohrss"))
    assert items[0].payload == {"k": 1}


def test_snapshot_exists_false():
    cur = ScriptedCursor([None])
    assert PgSnapshotStore(FakePool(cur)).exists("nope") is False


def test_ensure_source():
    cur = ScriptedCursor([None])
    PgSnapshotStore(FakePool(cur)).ensure_source(
        Source(id="mohrss", name="人社部", license="public")
    )
    assert "INSERT INTO sources" in cur.queries[0][0]


def test_posting_upsert_computes_period_and_normalized_title():
    cur = ScriptedCursor([{"id": "p1"}])
    posting = Posting(
        id="p1",
        source_id="mohrss",
        snapshot_id="s1",
        title="Java开发工程师",
        company="示例",
        city="北京市",
        published_at=date(2026, 7, 1),
        boilerplate_spans=[(0, 4)],
    )
    store = PgPostingStore(FakePool(cur))
    assert store.upsert(posting) == "p1"
    params = cur.queries[0][1]
    assert "java开发" in params
    assert "2026Q3" in params
    sql = cur.queries[0][0]
    assert "ON CONFLICT (id) DO UPDATE" in sql


def test_posting_iter_and_count_exclude_duplicates():
    row = {
        "id": "p1",
        "source_id": "mohrss",
        "snapshot_id": "s1",
        "title": "Java",
        "company": "示例",
        "city": "北京",
        "published_at": date(2026, 7, 1),
        "updated_at": None,
        "description": None,
        "occupation_code": None,
        "salary_min": 1,
        "salary_max": 2,
        "duplicate_of": None,
        "boilerplate_spans": [[0, 1]],
    }
    cur = ScriptedCursor([[row], {"n": 3}])
    store = PgPostingStore(FakePool(cur))
    items = list(store.iter_for_period("2026Q3"))
    assert items[0].boilerplate_spans == [(0, 1)]
    assert "duplicate_of IS NULL" in cur.queries[0][0]
    assert store.count_for_period("2026Q3") == 3


def test_storage_title_rules_match_collectors():
    assert normalize_title("JAVA 开发") == "java开发"
    assert period_from_date(date(2026, 4, 1)) == "2026Q2"


def test_evidence_save_and_get_many():
    ev = Evidence(
        id="e1",
        source_id="moka",
        posting_id="p1",
        span=TextSpan(doc_id="d1", start=0, end=4, page_index=0, bbox=(1, 2, 3, 4)),
        quote="Java",
        fetched_at=datetime(2026, 8, 1, tzinfo=UTC),
        extractor="rule",
        confidence=0.9,
    )
    cur = ScriptedCursor(
        [
            {"id": "e1"},
            [
                {
                    "id": "e1",
                    "source_id": "moka",
                    "posting_id": "p1",
                    "doc_id": "d1",
                    "span_start": 0,
                    "span_end": 4,
                    "page_index": 0,
                    "bbox": [1, 2, 3, 4],
                    "quote": "Java",
                    "fetched_at": ev.fetched_at,
                    "extractor": "rule",
                    "confidence": 0.9,
                }
            ],
        ]
    )
    store = PgEvidenceStore(FakePool(cur))
    assert store.save(ev) == "e1"
    got = store.get_many(["e1", "missing"])
    assert [g.id for g in got] == ["e1"]
    assert store.get_many([]) == []


def test_change_log_state_query_and_rollback():
    entry = ChangeLogEntry(
        id="c1",
        entity_kind="role",
        entity_id="r1",
        kind="added",
        reason="test",
        occurred_on=date(2026, 8, 1),
        recorded_at=datetime(2026, 8, 1, tzinfo=UTC),
        state="published",
    )
    row = {
        "id": "c1",
        "entity_kind": "role",
        "entity_id": "r1",
        "kind": "added",
        "before": None,
        "after": {"x": 1},
        "reason": "test",
        "evidence_ids": [],
        "occurred_on": date(2026, 8, 1),
        "recorded_at": datetime(2026, 8, 1, tzinfo=UTC),
        "state": "published",
        "reviewed_by": None,
        "rolled_back": False,
    }
    cur = ScriptedCursor([{"id": "c1"}, [row], None])
    store = ChangeLogStore(FakePool(cur))
    assert store.save(entry) == "c1"
    items = list(store.iter_by_state("published"))
    assert items[0].id == "c1"
    store.mark_rolled_back("c1")
    assert "rolled_back = TRUE" in cur.queries[2][0]


def test_observation_store_empty_role_and_get():
    obs = SkillObservation(
        role_id=None,
        skill_id="sk1",
        period="2026Q3",
        weight=0.5,
        posting_count=2,
        total_postings=10,
        ontology_version="v0",
    )
    row = {
        "skill_id": "sk1",
        "role_id": "",
        "period": "2026Q3",
        "weight": 0.5,
        "posting_count": 2,
        "total_postings": 10,
        "ontology_version": "v0",
    }
    cur = ScriptedCursor([None, [row], [row], [row]])
    store = ObservationStore(FakePool(cur))
    store.put(obs)
    assert cur.queries[0][1][1] == ""
    got = store.get("sk1", "2026Q3")
    assert got[0].role_id is None
    assert store.get("sk1", "2026Q3", role_id="r1")[0].skill_id == "sk1"
    assert list(store.iter_for_period("2026Q3"))[0].period == "2026Q3"
