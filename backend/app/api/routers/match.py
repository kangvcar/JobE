"""人岗匹配路由：诊断、学习路径、反向推荐。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.domain.models import LearningPath, SkillProfile
from app.matching.service import (
    MatchingNotConfiguredError,
    MatchingService,
    RoleNotFoundError,
    get_matching_service,
)
from app.matching.types import Diagnosis, RoleRecommendation

router = APIRouter(prefix="/api/match", tags=["match"])


class DiagnoseRequest(BaseModel):
    profile: SkillProfile
    role_id: str
    period: str | None = None


class PathRequest(BaseModel):
    profile: SkillProfile
    role_id: str
    period: str | None = None


class DiscoverRequest(BaseModel):
    profile: SkillProfile
    top_k: int = Field(default=5, ge=1, le=50)
    period: str | None = None


class DiscoverResponse(BaseModel):
    items: list[RoleRecommendation]


def _service() -> MatchingService:
    try:
        return get_matching_service()
    except MatchingNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail="匹配服务尚未注入") from exc


ServiceDep = Annotated[MatchingService, Depends(_service)]


@router.post("/diagnose", response_model=Diagnosis)
async def diagnose(body: DiagnoseRequest, svc: ServiceDep) -> Diagnosis:
    try:
        return await svc.diagnose(body.profile, body.role_id, body.period)
    except RoleNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"岗位不存在: {exc.role_id}") from exc


@router.post("/path", response_model=LearningPath)
async def learning_path(body: PathRequest, svc: ServiceDep) -> LearningPath:
    try:
        return await svc.learning_path(body.profile, body.role_id, body.period)
    except RoleNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"岗位不存在: {exc.role_id}") from exc


@router.post("/discover", response_model=DiscoverResponse)
def discover(body: DiscoverRequest, svc: ServiceDep) -> DiscoverResponse:
    return DiscoverResponse(items=svc.discover(body.profile, top_k=body.top_k, period=body.period))
