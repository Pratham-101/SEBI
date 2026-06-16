"""RegOps Command Center — aggregated operational intelligence API."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.briefings.generator import BriefingGenerator
from app.collaboration.approvals import CollaborationService
from app.core.database import get_db
from app.correlation.cross_regulator import CrossRegulatorCorrelation
from app.explainability.engine import ExplainabilityEngine
from app.exposure.scoring import ExposureScoringEngine
from app.intelligence.executive import ExecutiveIntelligenceEngine
from app.knowledge.graph import KnowledgeGraphService
from app.models.analysis_result import AnalysisResult
from app.models.escalation_record import EscalationRecord
from app.models.notification import Notification
from app.models.obligation import Obligation
from app.models.ticket import Ticket
from app.models.workflow_state import WorkflowState
from app.observability.metrics import ObservabilityService
from app.obligations.lifecycle import ObligationLifecycle
from app.sla.engine import SlaEngine

router = APIRouter(prefix="/command-center", tags=["command-center"])


@router.get("/dashboard")
def dashboard(db: Session = Depends(get_db)) -> dict:
    """Single payload for Command Center UI."""
    notifications = (
        db.query(Notification)
        .order_by(Notification.created_at.desc())
        .limit(25)
        .all()
    )
    feed = []
    for n in notifications:
        ticket = (
            db.query(Ticket)
            .filter(Ticket.notification_id == n.id)
            .order_by(Ticket.id.desc())
            .first()
        )
        analysis = (
            db.query(AnalysisResult)
            .filter(AnalysisResult.notification_id == n.id)
            .order_by(AnalysisResult.id.desc())
            .first()
        )
        ob_count = (
            db.query(Obligation).filter(Obligation.notification_id == n.id).count()
        )
        feed.append(
            {
                "id": n.id,
                "title": n.title,
                "regulator": getattr(n, "regulator_code", "SEBI"),
                "state": n.processing_state,
                "published_date": n.published_date,
                "url": n.url,
                "devrev_ticket": ticket.devrev_display_id if ticket else None,
                "priority": analysis.priority if analysis else None,
                "risk_score": analysis.risk_score if analysis else None,
                "obligations_count": ob_count,
            }
        )

    war_rooms = (
        db.query(WorkflowState)
        .filter(WorkflowState.workflow_type == "war_room")
        .order_by(WorkflowState.updated_at.desc())
        .limit(10)
        .all()
    )

    escalations = (
        db.query(EscalationRecord)
        .filter(EscalationRecord.status == "active")
        .order_by(EscalationRecord.created_at.desc())
        .limit(15)
        .all()
    )

    obligations = ObligationLifecycle(db).list_open(limit=30)
    briefing = BriefingGenerator(db).generate(period="daily")
    exposure = ExposureScoringEngine(db).enterprise_scores()
    executive = ExecutiveIntelligenceEngine(db).generate()
    cross_reg = CrossRegulatorCorrelation(db).fuse_signals()
    observability = ObservabilityService(db).dashboard()
    sla = SlaEngine(db).dashboard()
    pending_approvals = CollaborationService(db).pending()

    from app.intelligence.heatmap import PressureHeatmap
    from app.intelligence.narrator import OperationalNarrator
    from app.intelligence.timeline import IntelligenceTimeline

    return {
        "narrator": OperationalNarrator(db).generate_brief(),
        "timeline": IntelligenceTimeline(db).recent(limit=40),
        "heatmap": PressureHeatmap(db).generate(),
        "live_feed": feed,
        "war_rooms": [
            {
                "id": w.id,
                "notification_id": w.notification_id,
                "stage": w.current_stage,
                "work_id": w.devrev_parent_work_id,
            }
            for w in war_rooms
        ],
        "obligations": obligations,
        "escalations": [
            {
                "id": e.id,
                "level": e.escalation_level,
                "reason": e.reason[:200],
                "notification_id": e.notification_id,
            }
            for e in escalations
        ],
        "briefing": briefing,
        "exposure": exposure,
        "executive_intelligence": executive,
        "cross_regulator": cross_reg,
        "observability": observability,
        "sla": sla,
        "pending_approvals": pending_approvals,
        "predictive_alerts": briefing.get("trend_analysis", {}),
        "team_workload": briefing.get("compliance_bottlenecks", []),
    }


@router.get("/graph/full")
def full_graph(db: Session = Depends(get_db), limit: int = Query(default=80, le=200)) -> dict:
    from app.models.regulatory_entity import RegulatoryEntity
    from app.models.regulatory_relationship import RegulatoryRelationship

    nodes = db.query(RegulatoryEntity).order_by(RegulatoryEntity.id.desc()).limit(limit).all()
    node_ids = {n.id for n in nodes}
    edges = (
        db.query(RegulatoryRelationship)
        .filter(
            RegulatoryRelationship.source_entity_id.in_(node_ids),
            RegulatoryRelationship.target_entity_id.in_(node_ids),
        )
        .all()
    )
    return {
        "nodes": [
            {"id": n.id, "label": n.title[:60], "type": n.entity_type, "regulator": n.regulator_code}
            for n in nodes
        ],
        "edges": [
            {"source": e.source_entity_id, "target": e.target_entity_id, "type": e.relationship_type}
            for e in edges
        ],
    }


@router.get("/explain/{notification_id}")
def explanations(notification_id: int, db: Session = Depends(get_db)) -> dict:
    return {"explanations": ExplainabilityEngine(db).get_for_notification(notification_id)}


@router.get("/timeline")
def timeline(limit: int = 80, db: Session = Depends(get_db)) -> dict:
    from app.intelligence.timeline import IntelligenceTimeline

    return {"events": IntelligenceTimeline(db).recent(limit=limit)}


@router.get("/narrator")
def narrator(db: Session = Depends(get_db)) -> dict:
    from app.intelligence.narrator import OperationalNarrator

    return OperationalNarrator(db).generate_brief()


@router.get("/heatmap")
def heatmap(db: Session = Depends(get_db)) -> dict:
    from app.intelligence.heatmap import PressureHeatmap

    return PressureHeatmap(db).generate()


@router.post("/investigate")
def investigate(
    notification_id: int | None = None,
    query: str | None = None,
    db: Session = Depends(get_db),
) -> dict:
    from app.intelligence.investigator import RegulatoryInvestigator

    return RegulatoryInvestigator(db).investigate(
        notification_id=notification_id, query=query
    )


@router.get("/twin")
def digital_twin(db: Session = Depends(get_db)) -> dict:
    from app.twin.model import EnterpriseDigitalTwin

    return EnterpriseDigitalTwin(db).snapshot()


@router.get("/twin/simulate")
def twin_simulate(days: int = 30, db: Session = Depends(get_db)) -> dict:
    from app.twin.model import EnterpriseDigitalTwin

    return EnterpriseDigitalTwin(db).simulate_future(days=days)


@router.get("/consensus/{notification_id}")
def consensus(notification_id: int, db: Session = Depends(get_db)) -> dict:
    from app.agents.consensus.specialists import ConsensusCouncil
    from app.models.analysis_result import AnalysisResult
    from app.schemas.analysis import RegulatoryAnalysisOutput

    ar = (
        db.query(AnalysisResult)
        .filter(AnalysisResult.notification_id == notification_id)
        .order_by(AnalysisResult.id.desc())
        .first()
    )
    if not ar:
        return {"error": "no_analysis"}
    analysis = RegulatoryAnalysisOutput.model_validate_json(ar.structured_output)
    return ConsensusCouncil().deliberate(analysis)


@router.get("/replay")
def replay(
    regulator_code: str = "SEBI",
    months: int = 12,
    theme: str | None = None,
    db: Session = Depends(get_db),
) -> dict:
    from app.intelligence.replay import IntelligenceReplay

    return IntelligenceReplay(db).replay(
        regulator_code=regulator_code, months=months, theme_filter=theme
    )


@router.get("/strategic/{notification_id}")
def strategic(notification_id: int, db: Session = Depends(get_db)) -> dict:
    from app.intelligence.strategic import StrategicInterpreter
    from app.models.analysis_result import AnalysisResult
    from app.models.notification import Notification
    from app.schemas.analysis import RegulatoryAnalysisOutput

    ar = (
        db.query(AnalysisResult)
        .filter(AnalysisResult.notification_id == notification_id)
        .order_by(AnalysisResult.id.desc())
        .first()
    )
    n = db.get(Notification, notification_id)
    if not ar:
        return {"error": "no_analysis"}
    analysis = RegulatoryAnalysisOutput.model_validate_json(ar.structured_output)
    reg = getattr(n, "regulator_code", "SEBI") if n else "SEBI"
    return StrategicInterpreter().interpret(analysis, regulator_code=reg)


@router.get("/simulation-lab/{notification_id}")
def simulation_lab(notification_id: int, days: int = 30, db: Session = Depends(get_db)) -> dict:
    from app.models.analysis_result import AnalysisResult
    from app.schemas.analysis import RegulatoryAnalysisOutput
    from app.simulation.engine import SimulationEngine
    from app.predictive.engine import PredictiveComplianceEngine

    ar = (
        db.query(AnalysisResult)
        .filter(AnalysisResult.notification_id == notification_id)
        .order_by(AnalysisResult.id.desc())
        .first()
    )
    if not ar:
        return {"error": "no_analysis"}
    analysis = RegulatoryAnalysisOutput.model_validate_json(ar.structured_output)
    predictions = PredictiveComplianceEngine(db).assess(
        notification_id=notification_id,
        regulator_code="SEBI",
        analysis=analysis,
        historical_memories=[],
    )
    base = SimulationEngine(db).simulate_ignored(
        analysis=analysis, predictions=predictions, days_ignored=days
    )
    return {"simulation": base, "predictions": predictions}
