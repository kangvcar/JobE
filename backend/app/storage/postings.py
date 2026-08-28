"""职位仓储。title_normalized / period 在写入时按 domain.normalization 的规则计算。"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from psycopg.types.json import Jsonb

from app.domain.models import Posting
from app.domain.normalization import normalize_title, period_from_date
from app.storage.pool import PgPool

UPSERT_POSTING = """
INSERT INTO postings (
    id, source_id, snapshot_id, title, title_normalized, company, city,
    published_at, updated_at, period, description, occupation_code,
    salary_min, salary_max, duplicate_of, boilerplate_spans
) VALUES (
    %s, %s, %s, %s, %s, %s, %s,
    %s, %s, %s, %s, %s,
    %s, %s, %s, %s
)
ON CONFLICT (id) DO UPDATE SET
    snapshot_id = EXCLUDED.snapshot_id,
    title = EXCLUDED.title,
    title_normalized = EXCLUDED.title_normalized,
    company = EXCLUDED.company,
    city = EXCLUDED.city,
    published_at = EXCLUDED.published_at,
    updated_at = EXCLUDED.updated_at,
    period = EXCLUDED.period,
    description = EXCLUDED.description,
    occupation_code = EXCLUDED.occupation_code,
    salary_min = EXCLUDED.salary_min,
    salary_max = EXCLUDED.salary_max,
    duplicate_of = EXCLUDED.duplicate_of,
    boilerplate_spans = EXCLUDED.boilerplate_spans
RETURNING id
"""

UPSERT_POSTING_BATCH = """
INSERT INTO postings (
    id, source_id, snapshot_id, title, title_normalized, company, city,
    published_at, updated_at, period, description, occupation_code,
    salary_min, salary_max, duplicate_of, boilerplate_spans
) VALUES (
    %s, %s, %s, %s, %s, %s, %s,
    %s, %s, %s, %s, %s,
    %s, %s, %s, %s
)
ON CONFLICT (id) DO UPDATE SET
    snapshot_id = EXCLUDED.snapshot_id,
    title = EXCLUDED.title,
    title_normalized = EXCLUDED.title_normalized,
    company = EXCLUDED.company,
    city = EXCLUDED.city,
    published_at = EXCLUDED.published_at,
    updated_at = EXCLUDED.updated_at,
    period = EXCLUDED.period,
    description = EXCLUDED.description,
    occupation_code = EXCLUDED.occupation_code,
    salary_min = EXCLUDED.salary_min,
    salary_max = EXCLUDED.salary_max,
    duplicate_of = EXCLUDED.duplicate_of,
    boilerplate_spans = EXCLUDED.boilerplate_spans
"""

ITER_PERIOD = """
SELECT id, source_id, snapshot_id, title, company, city, published_at, updated_at,
       description, occupation_code, salary_min, salary_max, duplicate_of,
       boilerplate_spans
FROM postings
WHERE period = %s AND duplicate_of IS NULL
ORDER BY published_at NULLS LAST
"""

COUNT_PERIOD = """
SELECT COUNT(*) AS n FROM postings
WHERE period = %s AND duplicate_of IS NULL
"""

ITER_ALL = """
SELECT id, source_id, snapshot_id, title, company, city, published_at, updated_at,
       description, occupation_code, salary_min, salary_max, duplicate_of,
       boilerplate_spans
FROM postings
WHERE duplicate_of IS NULL
ORDER BY published_at NULLS LAST
"""

COUNT_ALL = """
SELECT COUNT(*) AS n FROM postings
"""


def _spans(value: object) -> list[tuple[int, int]]:
    if not value:
        return []
    return [(int(a), int(b)) for a, b in value]


def _row_to_posting(row: dict) -> Posting:
    return Posting(
        id=row["id"],
        source_id=row["source_id"],
        snapshot_id=row["snapshot_id"],
        title=row["title"],
        company=row["company"],
        city=row["city"],
        published_at=row["published_at"],
        updated_at=row["updated_at"],
        description=row["description"],
        occupation_code=row["occupation_code"],
        salary_min=row["salary_min"],
        salary_max=row["salary_max"],
        duplicate_of=row["duplicate_of"],
        boilerplate_spans=_spans(row["boilerplate_spans"]),
    )


class PgPostingStore:
    def __init__(self, pool: PgPool) -> None:
        self._pool = pool

    def upsert(self, posting: Posting) -> str:
        period = period_from_date(posting.published_at or posting.updated_at)
        spans = [list(s) for s in posting.boilerplate_spans]
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    UPSERT_POSTING,
                    (
                        posting.id,
                        posting.source_id,
                        posting.snapshot_id,
                        posting.title,
                        normalize_title(posting.title),
                        posting.company,
                        posting.city,
                        posting.published_at,
                        posting.updated_at,
                        period,
                        posting.description,
                        posting.occupation_code,
                        posting.salary_min,
                        posting.salary_max,
                        posting.duplicate_of,
                        Jsonb(spans),
                    ),
                )
                row = cur.fetchone()
                return row["id"] if row else posting.id

    def upsert_many(self, postings: Sequence[Posting]) -> int:
        if not postings:
            return 0
        rows = [
            (
                posting.id,
                posting.source_id,
                posting.snapshot_id,
                posting.title,
                normalize_title(posting.title),
                posting.company,
                posting.city,
                posting.published_at,
                posting.updated_at,
                period_from_date(posting.published_at or posting.updated_at),
                posting.description,
                posting.occupation_code,
                posting.salary_min,
                posting.salary_max,
                posting.duplicate_of,
                Jsonb([list(s) for s in posting.boilerplate_spans]),
            )
            for posting in postings
        ]
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.executemany(UPSERT_POSTING_BATCH, rows)
        return len(postings)

    def iter_for_period(self, period: str) -> Iterable[Posting]:
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(ITER_PERIOD, (period,))
                rows = cur.fetchall()
        for row in rows:
            yield _row_to_posting(row)

    def count_for_period(self, period: str) -> int:
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(COUNT_PERIOD, (period,))
                row = cur.fetchone()
                return int(row["n"]) if row else 0

    def iter_all(self) -> Iterable[Posting]:
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(ITER_ALL)
                rows = cur.fetchall()
        for row in rows:
            yield _row_to_posting(row)

    def count_all(self) -> int:
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(COUNT_ALL)
                row = cur.fetchone()
                return int(row["n"]) if row else 0
