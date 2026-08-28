"""审核与简历解析的最小可用路由。前端用证据接口做原文高亮。"""

from __future__ import annotations

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from app.domain.models import PublishState
from app.extraction.deps import get_deps
from app.extraction.layout import parse_document
from app.extraction.locator import CanonicalSpanLocator
from app.extraction.resume import extract_resume
from app.extraction.reviewer import LLMReviewer
from app.extraction.store import AliasDecision

router = APIRouter(prefix="/api/review", tags=["review"])


class DecisionIn(BaseModel):
    accept: bool
    decided_by: str
    skill_id: str | None = None
    note: str = ""


class EvidenceOut(BaseModel):
    id: str
    source_id: str
    quote: str
    confidence: float
    doc_id: str
    start: int
    end: int
    page_index: int | None = None
    bbox: tuple[float, float, float, float] | None = None


class UnverifiedOut(BaseModel):
    id: str
    kind: str
    claim: str
    evidence_ids: list[str]
    payload: dict = Field(default_factory=dict)
    doc_id: str | None = None


@router.post("/resumes")
async def upload_resume(file: UploadFile = File(...)) -> dict:  # noqa: B008
    deps = get_deps()
    data = await file.read()
    if not data:
        raise HTTPException(400, "空文件")
    try:
        parsed = parse_document(data, file.filename or "resume.txt")
    except RuntimeError as exc:
        raise HTTPException(400, str(exc)) from exc
    doc = deps.store.save_parsed(parsed, kind="resume")
    locator = CanonicalSpanLocator(deps.store)
    result = await extract_resume(
        doc,
        llm=deps.llm,
        locator=locator,
        store=deps.store,
        vocab=deps.skill_vocab(),
    )
    return {
        "doc_id": doc.id,
        "profile_id": result.profile.id,
        "skills": [s.model_dump() for s in result.profile.skills],
        "fields": [
            {
                "name": f.name,
                "value": f.value,
                "start": f.span.start,
                "end": f.span.end,
                "page_index": f.span.page_index,
                "bbox": f.span.bbox,
            }
            for f in result.fields
        ],
        "candidates": [
            {
                "surface_form": c.surface_form,
                "quote": c.quote,
                "start": c.span.start,
                "end": c.span.end,
            }
            for c in result.candidates
        ],
        "discarded": result.discarded,
        "backend": parsed.backend_name,
    }


@router.get("/unverified")
def list_unverified() -> dict:
    items = [
        UnverifiedOut(
            id=c.id,
            kind=c.kind,
            claim=c.text,
            evidence_ids=c.evidence_ids,
            payload=c.payload,
            doc_id=c.doc_id,
        )
        for c in get_deps().store.unverified()
    ]
    return {"items": [i.model_dump() for i in items]}


@router.post("/unverified/{item_id}/decide")
def decide(item_id: str, body: DecisionIn) -> dict:
    store = get_deps().store
    if item_id not in store.claims:
        raise HTTPException(404, "待确认条目不存在")
    state = PublishState.PUBLISHED if body.accept else PublishState.REJECTED
    claim = store.decide(
        item_id,
        state,
        payload={"decided_by": body.decided_by, "note": body.note, "skill_id": body.skill_id},
    )
    if body.accept and body.skill_id and claim.kind in {"new_skill", "alias", "skill"}:
        store.put_alias(
            AliasDecision(
                surface_form=claim.text,
                skill_id=body.skill_id,
                decided_by=body.decided_by,
                confidence=1.0,
            )
        )
    return {"id": claim.id, "state": claim.state.value}


@router.get("/claims/{claim_id}/evidence")
def claim_evidence(claim_id: str) -> dict:
    """一条结论的全部证据，供前端在原文上高亮。"""
    store = get_deps().store
    claim = store.claims.get(claim_id)
    if claim is None:
        raise HTTPException(404, "结论不存在")
    items = store.get_many(claim.evidence_ids)
    out = [
        EvidenceOut(
            id=e.id,
            source_id=e.source_id,
            quote=e.quote,
            confidence=e.confidence,
            doc_id=e.span.doc_id,
            start=e.span.start,
            end=e.span.end,
            page_index=e.span.page_index,
            bbox=e.span.bbox,
        )
        for e in items
    ]
    return {
        "claim_id": claim.id,
        "claim": claim.text,
        "kind": claim.kind,
        "state": claim.state.value,
        "evidence": [e.model_dump() for e in out],
    }


@router.post("/claims/{claim_id}/review")
async def auto_review(claim_id: str) -> dict:
    """用 AI 审核员判断结论是否被其证据支持。不产生新结论。"""
    deps = get_deps()
    claim = deps.store.claims.get(claim_id)
    if claim is None:
        raise HTTPException(404, "结论不存在")
    evidence = deps.store.get_many(claim.evidence_ids)
    outcome = await LLMReviewer(deps.reviewer_llm).review(claim.text, evidence)
    return outcome.model_dump()
