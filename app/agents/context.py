"""Shared execution context passed through RegOps multi-agent pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field

from app.schemas.analysis import RegulatoryAnalysisOutput
from app.schemas.notification import ScrapedNotification
from app.services.routing.assignment import AssignmentDecision
from app.services.routing.escalation import EscalationPlan
from app.services.routing.team_router import RoutingDecision


@dataclass
class RegOpsContext:
    trace_id: str
    regulator_code: str
    item: ScrapedNotification
    notification_id: int | None = None
    analysis: RegulatoryAnalysisOutput | None = None
    raw_analysis: str = ""
    governance_approved: bool = True
    governance_reasons: list[str] = field(default_factory=list)
    applicability_score: float = 1.0
    applicable: bool = True
    not_applicable_reason: str = ""
    routing: RoutingDecision | None = None
    assignment: AssignmentDecision | None = None
    escalation: EscalationPlan | None = None
    related_notifications: list[dict] = field(default_factory=list)
    historical_memories: list[dict] = field(default_factory=list)
    obligations: list[dict] = field(default_factory=list)
    predictions: dict = field(default_factory=dict)
    knowledge_graph: dict = field(default_factory=dict)
    devrev_work_id: str = ""
    devrev_display_id: str = ""
    subtask_ids: list[str] = field(default_factory=list)
    war_room: dict = field(default_factory=dict)
    intel_metadata: dict = field(default_factory=dict)
    stats: dict = field(default_factory=dict)
