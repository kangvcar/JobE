"""演化分析最小可用接口。计算在请求体内完成，不连库、不调大模型。"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.config import default_ontology_version
from app.domain.models import Burst, CompetencyChange, LeadLag, SkillObservation
from app.evolution.burst import KleinbergBurstDetector, classify_skill
from app.evolution.cluster import Cooccurrence
from app.evolution.drift import detect_competency_changes
from app.evolution.emerging import (
    EmergingCandidate,
    EmergingDiscoveryResult,
    ExistingRoleSkills,
    OccupationEntry,
    discover_emerging,
)
from app.evolution.inflation import (
    FirmRolePeriod,
    InflationReport,
    PeriodSkillLoad,
    deflate_weights,
    observe_inflation,
)
from app.evolution.leadlag import CcfLeadLagAnalyzer

router = APIRouter(prefix="/api/evolution", tags=["evolution"])


class BurstRequest(BaseModel):
    series: list[SkillObservation]
    source_id: str = "aggregate"


class TrendResponse(BaseModel):
    skill_id: str | None
    label: str
    bursts: list[Burst]
    trend: str
    trend_p_value: float
    slope: float


class LeadLagRequest(BaseModel):
    leading: list[SkillObservation]
    lagging: list[SkillObservation]
    leading_source_id: str
    lagging_source_id: str
    max_lag: int = 8


class InflationRequest(BaseModel):
    loads: list[PeriodSkillLoad]
    ontology_version: str = Field(default_factory=default_ontology_version)
    firm_panel: list[FirmRolePeriod] = Field(default_factory=list)
    observations: list[SkillObservation] = Field(default_factory=list)


class InflationResponse(BaseModel):
    report: InflationReport
    deflated: list[SkillObservation] = Field(default_factory=list)


class ChangeRequest(BaseModel):
    role_id: str
    before: list[SkillObservation]
    after: list[SkillObservation]
    recorded_at: datetime
    evidence_by_skill: dict[str, list[str]] = Field(default_factory=dict)


class EmergingRequest(BaseModel):
    edges: list[Cooccurrence]
    bursts: list[Burst]
    existing_roles: list[ExistingRoleSkills]
    catalog: list[OccupationEntry]
    ontology_version: str
    current_period: str | None = None


class EmergingResponse(BaseModel):
    publish_queue: list[EmergingCandidate]
    watch_zone: list[EmergingCandidate]


@router.post("/skills/trend", response_model=TrendResponse)
def skill_trend(body: BurstRequest) -> TrendResponse:
    detector = KleinbergBurstDetector(source_id=body.source_id)
    result = classify_skill(body.series, detector)
    skill_id = body.series[0].skill_id if body.series else None
    return TrendResponse(
        skill_id=skill_id,
        label=result.label,
        bursts=result.bursts,
        trend=result.trend.trend,
        trend_p_value=result.trend.p_value,
        slope=result.trend.slope,
    )


@router.post("/lead-lag", response_model=LeadLag | None)
def lead_lag(body: LeadLagRequest) -> LeadLag | None:
    analyzer = CcfLeadLagAnalyzer(
        leading_source_id=body.leading_source_id,
        lagging_source_id=body.lagging_source_id,
        max_lag=body.max_lag,
    )
    return analyzer.analyze(body.leading, body.lagging)


@router.post("/inflation", response_model=InflationResponse)
def inflation(body: InflationRequest) -> InflationResponse:
    report = observe_inflation(
        body.loads, ontology_version=body.ontology_version, firm_panel=body.firm_panel
    )
    deflated = deflate_weights(body.observations, report) if body.observations else []
    return InflationResponse(report=report, deflated=deflated)


@router.post("/roles/changes", response_model=list[CompetencyChange])
def role_changes(body: ChangeRequest) -> list[CompetencyChange]:
    return detect_competency_changes(
        body.role_id,
        body.before,
        body.after,
        recorded_at=body.recorded_at,
        evidence_by_skill=body.evidence_by_skill,
    )


@router.post("/emerging", response_model=EmergingResponse)
def emerging(body: EmergingRequest) -> EmergingResponse:
    result: EmergingDiscoveryResult = discover_emerging(
        edges=body.edges,
        bursts=body.bursts,
        existing_roles=body.existing_roles,
        catalog=body.catalog,
        ontology_version=body.ontology_version,
        current_period=body.current_period,
    )
    return EmergingResponse(publish_queue=result.publish_queue, watch_zone=result.watch_zone)
