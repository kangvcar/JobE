"""图谱查询 HTTP 接口。只暴露前端需要的读模型，不泄漏 Cypher。"""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from app.config import get_settings
from app.domain.models import CompetencyChange
from app.graph.queries import GraphQueryService
from app.graph.repository import Neo4jGraphRepository
from app.graph.session import Neo4jExecutor, create_driver

router = APIRouter(prefix="/api/graph", tags=["graph"])


@lru_cache
def _driver():
    return create_driver()


def get_executor() -> Neo4jExecutor:
    return Neo4jExecutor(_driver())


def get_repository(
    executor: Annotated[Neo4jExecutor, Depends(get_executor)],
) -> Neo4jGraphRepository:
    return Neo4jGraphRepository(executor, get_settings().ontology_version)


def get_query_service(
    executor: Annotated[Neo4jExecutor, Depends(get_executor)],
) -> GraphQueryService:
    return GraphQueryService(executor, get_settings().ontology_version)


def _bad_request(exc: ValueError) -> HTTPException:
    return HTTPException(status_code=400, detail=str(exc))


@router.get("/panorama")
def panorama(
    period: Annotated[str, Query(description="时间片，YYYYQn")],
    svc: Annotated[GraphQueryService, Depends(get_query_service)],
    family_id: Annotated[str | None, Query(description="按岗位族过滤")] = None,
    importance_tier: Annotated[str | None, Query(description="high / medium / low")] = None,
    min_weight: Annotated[float, Query(ge=0.0)] = 0.0,
    limit: Annotated[int, Query(ge=1, le=2000)] = 2000,
    published_only: bool = True,
) -> dict:
    try:
        return svc.panorama(
            period,
            family_id=family_id,
            importance_tier=importance_tier,
            min_weight=min_weight,
            limit=limit,
            published_only=published_only,
        )
    except ValueError as exc:
        raise _bad_request(exc) from exc


@router.get("/snapshot")
def snapshot(
    period: Annotated[str, Query(description="时间片，YYYYQn")],
    repo: Annotated[Neo4jGraphRepository, Depends(get_repository)],
) -> dict:
    try:
        return repo.snapshot_at(period)
    except ValueError as exc:
        raise _bad_request(exc) from exc


@router.get("/diff")
def diff(
    period_a: Annotated[str, Query(description="较早的时间片")],
    period_b: Annotated[str, Query(description="较晚的时间片")],
    repo: Annotated[Neo4jGraphRepository, Depends(get_repository)],
) -> list[CompetencyChange]:
    try:
        return repo.diff(period_a, period_b)
    except ValueError as exc:
        raise _bad_request(exc) from exc


@router.get("/compare-roles")
def compare_roles(
    role_a: Annotated[str, Query()],
    role_b: Annotated[str, Query()],
    period: Annotated[str, Query(description="时间片，YYYYQn")],
    svc: Annotated[GraphQueryService, Depends(get_query_service)],
) -> dict:
    try:
        return svc.compare_roles(role_a, role_b, period)
    except ValueError as exc:
        raise _bad_request(exc) from exc


@router.get("/roles/{role_id}/panorama")
def role_panorama(
    role_id: str,
    svc: Annotated[GraphQueryService, Depends(get_query_service)],
    period: Annotated[str | None, Query(description="时间片，缺省为该岗位最新一期")] = None,
) -> dict:
    try:
        payload = svc.role_panorama(role_id, period)
    except ValueError as exc:
        raise _bad_request(exc) from exc
    if payload is None:
        raise HTTPException(status_code=404, detail="岗位不存在")
    return payload


@router.get("/skills/{skill_id}/cooccurrence")
def skill_cooccurrence(
    skill_id: str,
    svc: Annotated[GraphQueryService, Depends(get_query_service)],
    hops: Annotated[int, Query(ge=1, le=2)] = 1,
    period: Annotated[str | None, Query(description="时间片，缺省为该技能点最新一期")] = None,
) -> dict:
    try:
        payload = svc.skill_cooccurrence(skill_id, hops=hops, period=period)
    except ValueError as exc:
        raise _bad_request(exc) from exc
    if payload.get("skill") is None:
        raise HTTPException(status_code=404, detail="技能点不存在")
    return payload
