"""技能观测值。role_id 为空时写入空串，以迁就 PRIMARY KEY 的 NOT NULL。"""

from __future__ import annotations

from collections.abc import Iterable

from app.config import get_settings
from app.domain.models import SkillObservation
from app.storage.pool import PgPool

UPSERT_OBS = """
INSERT INTO skill_observations (
    skill_id, role_id, period, weight, posting_count, total_postings, ontology_version
) VALUES (%s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (skill_id, role_id, period, ontology_version) DO UPDATE SET
    weight = EXCLUDED.weight,
    posting_count = EXCLUDED.posting_count,
    total_postings = EXCLUDED.total_postings
"""

SELECT_OBS = """
SELECT skill_id, role_id, period, weight, posting_count, total_postings, ontology_version
FROM skill_observations
WHERE skill_id = %s AND period = %s AND ontology_version = %s
"""

SELECT_OBS_ROLE = SELECT_OBS + " AND role_id = %s"

ITER_PERIOD = """
SELECT skill_id, role_id, period, weight, posting_count, total_postings, ontology_version
FROM skill_observations
WHERE period = %s
"""

ITER_ALL = """
SELECT skill_id, role_id, period, weight, posting_count, total_postings, ontology_version
FROM skill_observations
ORDER BY period, skill_id, role_id
"""

ITER_SKILL = """
SELECT skill_id, role_id, period, weight, posting_count, total_postings, ontology_version
FROM skill_observations
WHERE skill_id = %s AND ontology_version = %s
ORDER BY period
"""


def _role_key(role_id: str | None) -> str:
    return role_id or ""


def _row_to_obs(row: dict) -> SkillObservation:
    role = row["role_id"]
    return SkillObservation(
        role_id=role or None,
        skill_id=row["skill_id"],
        period=row["period"],
        weight=row["weight"],
        posting_count=row["posting_count"],
        total_postings=row["total_postings"],
        ontology_version=row["ontology_version"],
    )


class ObservationStore:
    def __init__(self, pool: PgPool) -> None:
        self._pool = pool

    def put(self, observation: SkillObservation) -> None:
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    UPSERT_OBS,
                    (
                        observation.skill_id,
                        _role_key(observation.role_id),
                        observation.period,
                        observation.weight,
                        observation.posting_count,
                        observation.total_postings,
                        observation.ontology_version,
                    ),
                )

    def get(
        self,
        skill_id: str,
        period: str,
        *,
        role_id: str | None = None,
        ontology_version: str | None = None,
    ) -> list[SkillObservation]:
        # 不写死 "v0"：真实数据标的是 ontology/VERSION 里的版本，写死会静默查出零行。
        ontology_version = ontology_version or get_settings().ontology_version
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                if role_id is not None:
                    cur.execute(
                        SELECT_OBS_ROLE,
                        (skill_id, period, ontology_version, _role_key(role_id)),
                    )
                else:
                    cur.execute(SELECT_OBS, (skill_id, period, ontology_version))
                rows = cur.fetchall()
        return [_row_to_obs(row) for row in rows]

    def iter_for_period(self, period: str) -> Iterable[SkillObservation]:
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(ITER_PERIOD, (period,))
                rows = cur.fetchall()
        for row in rows:
            yield _row_to_obs(row)

    def iter_all(self) -> Iterable[SkillObservation]:
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(ITER_ALL)
                rows = cur.fetchall()
        for row in rows:
            yield _row_to_obs(row)

    def iter_for_skill(
        self, skill_id: str, *, ontology_version: str | None = None
    ) -> Iterable[SkillObservation]:
        ontology_version = ontology_version or get_settings().ontology_version
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(ITER_SKILL, (skill_id, ontology_version))
                rows = cur.fetchall()
        for row in rows:
            yield _row_to_obs(row)
