"""RegOps OS API — copilot, briefings, graph, obligations, regulators."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.briefings.generator import BriefingGenerator
from app.core.database import get_db
from app.copilot.service import RegOpsCopilot
from app.domain.regulators.registry import list_regulators
from app.knowledge.graph import KnowledgeGraphService
from app.obligations.lifecycle import ObligationLifecycle

router = APIRouter(prefix="/regops", tags=["regops"])


class CopilotRequest(BaseModel):
  question: str = Field(..., min_length=3, max_length=500)
  regulator_code: str | None = None


class CopilotSourceRef(BaseModel):
  title: str
  url: str


class CopilotTicketRef(BaseModel):
  display_id: str
  url: str
  title: str


class CopilotResponse(BaseModel):
  answer: str
  ticket_references: list[CopilotTicketRef] = Field(default_factory=list)
  sebi_sources: list[CopilotSourceRef] = Field(default_factory=list)
  web_sources: list[CopilotSourceRef] = Field(default_factory=list)
  used_web_search: bool = False


@router.get("/regulators")
def regulators() -> dict:
  return {"regulators": list_regulators()}


@router.post("/copilot", response_model=CopilotResponse)
def copilot(body: CopilotRequest, db: Session = Depends(get_db)) -> CopilotResponse:
  result = RegOpsCopilot(db).answer(body.question, regulator_code=body.regulator_code)
  return CopilotResponse.model_validate(result)


@router.get("/briefings/{period}")
def briefing(
  period: str,
  regulator_code: str | None = None,
  db: Session = Depends(get_db),
) -> dict:
  if period not in ("daily", "weekly"):
    period = "daily"
  return BriefingGenerator(db).generate(period=period, regulator_code=regulator_code)


@router.get("/obligations")
def obligations(
  regulator_code: str | None = None,
  status: str | None = Query(default="open"),
  db: Session = Depends(get_db),
) -> dict:
  lifecycle = ObligationLifecycle(db)
  if status == "open":
    items = lifecycle.list_open(regulator_code=regulator_code)
  else:
    items = lifecycle.list_open(regulator_code=regulator_code)
  return {"obligations": items, "count": len(items)}


@router.get("/graph/{notification_id}")
def knowledge_graph(notification_id: int, db: Session = Depends(get_db)) -> dict:
  return KnowledgeGraphService(db).subgraph_for_notification(notification_id)


@router.patch("/obligations/{obligation_id}")
def update_obligation(
  obligation_id: int,
  status: str,
  db: Session = Depends(get_db),
) -> dict:
  from app.sla.engine import SlaEngine

  try:
    result = SlaEngine(db).transition(obligation_id, status, actor="operator")
  except ValueError as e:
    return {"error": str(e)}
  if not result:
    return {"error": "not_found"}
  return result


@router.post("/obligations/{obligation_id}/simulate")
def simulate_ignored(obligation_id: int, days: int = 30, db: Session = Depends(get_db)) -> dict:
  from app.models.analysis_result import AnalysisResult
  from app.models.obligation import Obligation
  from app.simulation.engine import SimulationEngine
  import json

  ob = db.get(Obligation, obligation_id)
  if not ob:
    return {"error": "not_found"}
  ar = (
    db.query(AnalysisResult)
    .filter(AnalysisResult.notification_id == ob.notification_id)
    .order_by(AnalysisResult.id.desc())
    .first()
  )
  if not ar:
    return {"error": "no_analysis"}
  from app.schemas.analysis import RegulatoryAnalysisOutput

  analysis = RegulatoryAnalysisOutput.model_validate_json(ar.structured_output)
  predictions = {"operational_exposure": 0.6, "escalation_probability": 0.4}
  return SimulationEngine(db).simulate_ignored(
    analysis=analysis, predictions=predictions, days_ignored=days
  )


@router.get("/collaboration/pending")
def pending_approvals(db: Session = Depends(get_db)) -> dict:
  from app.collaboration.approvals import CollaborationService

  return {"pending": CollaborationService(db).pending()}


@router.post("/collaboration/{decision_id}/decide")
def decide(
  decision_id: int,
  decision: str,
  notes: str | None = None,
  db: Session = Depends(get_db),
) -> dict:
  from app.collaboration.approvals import CollaborationService

  result = CollaborationService(db).decide(decision_id, decision=decision, notes=notes)
  if not result:
    return {"error": "not_found"}
  return result


@router.get("/exposure")
def exposure(db: Session = Depends(get_db)) -> dict:
  from app.exposure.scoring import ExposureScoringEngine

  return ExposureScoringEngine(db).enterprise_scores()


@router.get("/cross-regulator")
def cross_regulator(db: Session = Depends(get_db)) -> dict:
  from app.correlation.cross_regulator import CrossRegulatorCorrelation

  return CrossRegulatorCorrelation(db).fuse_signals()


@router.get("/executive")
def executive_intel(db: Session = Depends(get_db)) -> dict:
  from app.intelligence.executive import ExecutiveIntelligenceEngine

  return ExecutiveIntelligenceEngine(db).generate()


@router.post("/autonomous/run")
def run_autonomous(db: Session = Depends(get_db)) -> dict:
  from app.orchestration.autonomous import AutonomousOrchestrator

  return AutonomousOrchestrator(db).run_cycle()
