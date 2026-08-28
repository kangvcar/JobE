"""进程内连接池。未引入 psycopg_pool，用队列做最小封装。"""

from __future__ import annotations

import queue
import threading
from collections.abc import Iterator
from contextlib import contextmanager

import psycopg
from psycopg.rows import dict_row

from app.config import get_settings


class PgPool:
    def __init__(self, dsn: str | None = None, max_size: int = 8) -> None:
        self._dsn = dsn or get_settings().postgres_dsn
        self._max_size = max_size
        self._idle: queue.SimpleQueue[psycopg.Connection] = queue.SimpleQueue()
        self._created = 0
        self._lock = threading.Lock()

    def _acquire(self) -> psycopg.Connection:
        try:
            return self._idle.get_nowait()
        except queue.Empty:
            pass
        with self._lock:
            if self._created < self._max_size:
                conn = psycopg.connect(self._dsn, row_factory=dict_row)
                self._created += 1
                return conn
        return self._idle.get()

    def _release(self, conn: psycopg.Connection) -> None:
        if conn.closed:
            with self._lock:
                self._created = max(0, self._created - 1)
            return
        self._idle.put(conn)

    @contextmanager
    def connection(self) -> Iterator[psycopg.Connection]:
        conn = self._acquire()
        try:
            yield conn
            conn.commit()
        except Exception:
            if not conn.closed:
                conn.rollback()
            raise
        finally:
            self._release(conn)

    def close(self) -> None:
        while True:
            try:
                conn = self._idle.get_nowait()
            except queue.Empty:
                break
            conn.close()
