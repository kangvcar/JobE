"""前端页面形状的聚合路由。模块原语路由原样保留。"""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile

from app.config import get_settings
from app.domain.models import Role
from app.graph.repository import Neo4jGraphRepository
from app.graph.session import Neo4jExecutor, create_driver
from app.pages.models import (
    CandidateCard,
    DiagnoseResult,
    EvidenceDetail,
    GraphPayload,
    GraphView,
    MarketOverview,
    MeHome,
    ReviewItem,
    RoleDetail,
    SkillDetail,
)
from app.pages.service import PageService
from app.storage.documents import PgDocumentStore
from app.storage.evidence import PgEvidenceStore
from app.storage.observations import ObservationStore
from app.storage.pool import PgPool

router = APIRouter(tags=["pages"])


@lru_cache
def _driver():
    return create_driver()


@lru_cache
def _pool() -> PgPool:
    return PgPool()


@lru_cache
def get_page_service() -> PageService:
    executor = Neo4jExecutor(_driver())
    repo = Neo4jGraphRepository(executor, get_settings().ontology_version)
    pool = _pool()
    return PageService(
        repo,
        ObservationStore(pool),
        PgEvidenceStore(pool),
        PgDocumentStore(pool),
    )


PageDep = Annotated[PageService, Depends(get_page_service)]


@router.get("/api/match/me", response_model=MeHome)
def me_home(
    svc: PageDep,
    profile_id: str | None = None,
    role_id: str | None = None,
) -> MeHome:
    return svc.me_home(profile_id, role_id)


@router.get("/api/graph/overview", response_model=GraphPayload)
def graph_overview(svc: PageDep, view: GraphView = "stack") -> GraphPayload:
    return svc.graph_overview(view)


@router.get("/api/graph/roles", response_model=list[Role])
def list_roles(svc: PageDep) -> list[Role]:
    return svc.list_roles()


@router.get("/api/graph/roles/{role_id}", response_model=RoleDetail)
def role_detail(role_id: str, svc: PageDep) -> RoleDetail:
    payload = svc.role_detail(role_id)
    if payload is None:
        raise HTTPException(status_code=404, detail="岗位不存在")
    return payload


@router.get("/api/graph/skills/{skill_id}", response_model=SkillDetail)
def skill_detail(skill_id: str, svc: PageDep) -> SkillDetail:
    payload = svc.skill_detail(skill_id)
    if payload is None:
        raise HTTPException(status_code=404, detail="技能点不存在")
    return payload


@router.get("/api/graph/candidates", response_model=list[CandidateCard])
def candidates(svc: PageDep) -> list[CandidateCard]:
    return svc.candidates()


@router.get("/api/graph/evidence/{evidence_id}", response_model=EvidenceDetail)
def evidence_one(evidence_id: str, svc: PageDep) -> EvidenceDetail:
    item = svc.evidence_detail(evidence_id)
    if item is None:
        raise HTTPException(status_code=404, detail="证据不存在")
    return item


@router.get("/api/graph/evidence", response_model=list[EvidenceDetail])
def evidence_batch(svc: PageDep, ids: str = Query(default="")) -> list[EvidenceDetail]:
    wanted = [x for x in ids.split(",") if x]
    return svc.evidence_batch(wanted)


@router.get("/api/evolution/market", response_model=MarketOverview)
def market(svc: PageDep) -> MarketOverview:
    return svc.market()


@router.get("/api/review/queue", response_model=list[ReviewItem])
def review_queue() -> list[ReviewItem]:
    return []


@router.post("/api/review/{item_id}/decide", response_model=list[ReviewItem])
def decide_review(item_id: str, body: dict) -> list[ReviewItem]:
    return []


@router.get("/api/match/cases/{case_id}")
def diagnose_case(case_id: str) -> DiagnoseResult:
    raise HTTPException(status_code=404, detail="演示案例只在前端 mock 中提供")


@router.post("/api/match/resume")
async def diagnose_resume(file: UploadFile = File(...), role_id: str | None = None) -> dict:  # noqa: B008
    raise HTTPException(
        status_code=501,
        detail="简历诊断需要大模型密钥；请先在「我」页选择岗位查看市场升值与图谱",
    )
