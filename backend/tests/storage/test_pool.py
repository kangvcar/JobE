from __future__ import annotations

from app.storage.pool import PgPool


def test_pool_reuses_idle_connection(monkeypatch):
    created: list[object] = []

    class FakeConn:
        closed = False

        def commit(self):
            return None

        def rollback(self):
            return None

        def close(self):
            self.closed = True

    def connect(dsn, row_factory=None):
        conn = FakeConn()
        created.append(conn)
        return conn

    monkeypatch.setattr("app.storage.pool.psycopg.connect", connect)
    pool = PgPool("postgresql://example", max_size=2)
    with pool.connection() as conn:
        assert conn is created[0]
    with pool.connection() as conn:
        assert conn is created[0]
    assert len(created) == 1
    pool.close()
    assert created[0].closed is True


def test_pool_rollback_on_error(monkeypatch):
    class FakeConn:
        closed = False
        rollbacks = 0

        def commit(self):
            return None

        def rollback(self):
            self.rollbacks += 1

        def close(self):
            self.closed = True

    monkeypatch.setattr(
        "app.storage.pool.psycopg.connect", lambda dsn, row_factory=None: FakeConn()
    )
    pool = PgPool("postgresql://example", max_size=1)
    try:
        with pool.connection():
            raise RuntimeError("boom")
    except RuntimeError:
        pass
    with pool.connection() as conn:
        assert conn.rollbacks == 1
