"""RegOps OS multi-agent coordinator."""

from __future__ import annotations

import time
import uuid

import structlog
from sqlalchemy.orm import Session

from app.agents.applicability import ApplicabilityAgent
from app.agents.classification import ClassificationAgent
from app.agents.context import RegOpsContext
from app.agents.executive_escalation import ExecutiveEscalationAgent
from app.agents.historical_correlation import HistoricalCorrelationAgent
from app.agents.ingestion import IngestionAgent
from app.agents.knowledge_graph import KnowledgeGraphAgent
from app.agents.obligation_extraction import ObligationExtractionAgent
from app.agents.organizational_memory import OrganizationalMemoryAgent
from app.agents.risk_analysis import RiskAnalysisAgent
from app.agents.workflow_orchestration import WorkflowOrchestrationAgent
from app.collaboration.approvals import CollaborationService
from app.core.config import get_settings
from app.domain.regulators.registry import get_regulator
from app.events.emitter import IntelligenceEmitter
from app.explainability.engine import ExplainabilityEngine
from app.governance.audit import AuditService
from app.intelligence.strategic import StrategicInterpreter
from app.models.analysis_result import AnalysisResult
from app.models.notification import Notification
from app.models.processing_log import ProcessingLog
from app.observability.metrics import ObservabilityService
from app.predictive.engine import PredictiveComplianceEngine
from app.schemas.analysis import RegulatoryAnalysisOutput
from app.schemas.notification import ScrapedNotification
from app.services.pipeline.backlog import (
    load_backlog_for_ingestion,
    load_backlog_for_workflow,
    notification_to_scraped,
)

logger = structlog.get_logger(__name__)


class RegOpsCoordinator:
  """Orchestrates the nine-agent RegOps intelligence pipeline."""

  def __init__(self, db: Session) -> None:
    self._db = db
    self._audit = AuditService(db)
    self._memory_agent = OrganizationalMemoryAgent(db)
    self._predictive = PredictiveComplianceEngine(db)
    self._emitter = IntelligenceEmitter(db)

  def run(self, *, trace_id: str | None = None, regulator_code: str | None = None) -> dict:
    trace_id = trace_id or uuid.uuid4().hex
    settings = get_settings()
    regulator = (regulator_code or settings.active_regulator or "SEBI").upper()
    log = logger.bind(trace_id=trace_id, regulator=regulator)
    log.info("regops_pipeline_started")
    start = time.perf_counter()

    stats = {
      "discovered": 0,
      "backlog_ingestion": 0,
      "backlog_workflow": 0,
      "skipped_duplicate": 0,
      "not_applicable": 0,
      "processed": 0,
      "tickets_created": 0,
      "subtasks_created": 0,
      "war_rooms": 0,
      "obligations_extracted": 0,
      "errors": 0,
    }

    plugin = get_regulator(regulator)
    scrape_start = time.perf_counter()
    items = plugin.scrape_latest(limit=settings.sebi_scrape_limit)
    stats["discovered"] = len(items)

    # Dead-man's-switch: record scrape health and alert on silent failures.
    from app.services.scraper.health import record_scrape_health

    try:
      record_scrape_health(
        self._db,
        regulator_code=regulator,
        rows_found=len(items),
        duration_ms=int((time.perf_counter() - scrape_start) * 1000),
      )
    except Exception as exc:  # noqa: BLE001 — health recording must never break the run
      log.warning("scrape_health_record_failed", error=str(exc))

    pre_agents = [
      IngestionAgent(self._db),
      ApplicabilityAgent(self._db),
      ClassificationAgent(self._db),
      self._memory_agent,
      RiskAnalysisAgent(self._db),
      HistoricalCorrelationAgent(self._db),
      ObligationExtractionAgent(self._db),
    ]
    post_ticket_agents = [
      WorkflowOrchestrationAgent(self._db),
      KnowledgeGraphAgent(self._db),
      ExecutiveEscalationAgent(self._db),
    ]

    for item in items:
      item.regulator_code = regulator
      self._process_scraped_item(
        item,
        regulator=regulator,
        trace_id=trace_id,
        stats=stats,
        pre_agents=pre_agents,
        post_ticket_agents=post_ticket_agents,
        log=log,
      )

    backlog_ingestion = load_backlog_for_ingestion(
      self._db, limit=settings.pipeline_backlog_batch_size
    )
    stats["backlog_ingestion"] = len(backlog_ingestion)
    for notification in backlog_ingestion:
      item = notification_to_scraped(notification)
      item.regulator_code = regulator
      self._process_scraped_item(
        item,
        regulator=regulator,
        trace_id=trace_id,
        stats=stats,
        pre_agents=pre_agents,
        post_ticket_agents=post_ticket_agents,
        log=log,
      )

    backlog_workflow = load_backlog_for_workflow(
      self._db, limit=settings.pipeline_backlog_batch_size
    )
    stats["backlog_workflow"] = len(backlog_workflow)
    for notification in backlog_workflow:
      self._process_workflow_backlog(
        notification,
        regulator=regulator,
        trace_id=trace_id,
        stats=stats,
        post_ticket_agents=post_ticket_agents,
        log=log,
      )

    duration_ms = int((time.perf_counter() - start) * 1000)
    ObservabilityService.record_pipeline_duration(duration_ms / 1000.0)
    self._audit.log(
      event_type="regops_pipeline_run",
      entity_type="pipeline",
      entity_id=trace_id,
      outcome="completed",
      payload={**stats, "duration_ms": duration_ms, "regulator": regulator},
      trace_id=trace_id,
    )
    log.info("regops_pipeline_completed", **stats, duration_ms=duration_ms)
    return stats

  def _process_scraped_item(
    self,
    item: ScrapedNotification,
    *,
    regulator: str,
    trace_id: str,
    stats: dict,
    pre_agents: list,
    post_ticket_agents: list,
    log,
  ) -> None:
    try:
      item_stats: dict = {}
      ctx = RegOpsContext(
        trace_id=trace_id,
        regulator_code=regulator,
        item=item,
        stats=item_stats,
      )
      for agent in pre_agents:
        ctx = agent.run(ctx)
        if item_stats.get("skipped_duplicate") or item_stats.get("not_applicable"):
          break

      if item_stats.get("skipped_duplicate"):
        stats["skipped_duplicate"] += 1
        return
      if item_stats.get("not_applicable"):
        stats["not_applicable"] = stats.get("not_applicable", 0) + 1
        return
      if not ctx.analysis:
        return

      self._finish_item(
        ctx,
        item=item,
        regulator=regulator,
        stats=stats,
        item_stats=item_stats,
        post_ticket_agents=post_ticket_agents,
      )
      stats["processed"] += 1

    except Exception as exc:
      stats["errors"] += 1
      log.exception("regops_item_failed", url=item.url, error=str(exc))
      self._log(None, "error", "failed", str(exc), trace_id=trace_id)

  def _process_workflow_backlog(
    self,
    notification: Notification,
    *,
    regulator: str,
    trace_id: str,
    stats: dict,
    post_ticket_agents: list,
    log,
  ) -> None:
    """Resume pipeline for analyzed items that never received a DevRev ticket."""
    try:
      analysis_row = (
        self._db.query(AnalysisResult)
        .filter(AnalysisResult.notification_id == notification.id)
        .order_by(AnalysisResult.id.desc())
        .first()
      )
      if not analysis_row:
        item = notification_to_scraped(notification)
        item.regulator_code = regulator
        self._process_scraped_item(
          item,
          regulator=regulator,
          trace_id=trace_id,
          stats=stats,
          pre_agents=[
            IngestionAgent(self._db),
            ApplicabilityAgent(self._db),
            ClassificationAgent(self._db),
            self._memory_agent,
            RiskAnalysisAgent(self._db),
            HistoricalCorrelationAgent(self._db),
            ObligationExtractionAgent(self._db),
          ],
          post_ticket_agents=post_ticket_agents,
          log=log,
        )
        return

      analysis = RegulatoryAnalysisOutput.model_validate_json(analysis_row.structured_output)
      item = notification_to_scraped(notification)
      item_stats: dict = {}
      ctx = RegOpsContext(
        trace_id=trace_id,
        regulator_code=regulator,
        item=item,
        stats=item_stats,
        notification_id=notification.id,
        analysis=analysis,
      )
      ctx = RiskAnalysisAgent(self._db).run(ctx)
      ctx = HistoricalCorrelationAgent(self._db).run(ctx)
      ctx = ObligationExtractionAgent(self._db).run(ctx)
      if not ctx.routing:
        return
      ctx.predictions = self._predictive.assess(
        notification_id=notification.id,
        regulator_code=regulator,
        analysis=analysis,
        historical_memories=[],
      )
      self._finish_item(
        ctx,
        item=item,
        regulator=regulator,
        stats=stats,
        item_stats=item_stats,
        post_ticket_agents=post_ticket_agents,
        skip_pre_ticket_emit=False,
      )
      stats["processed"] += 1
    except Exception as exc:
      stats["errors"] += 1
      log.exception(
        "regops_workflow_backlog_failed",
        notification_id=notification.id,
        error=str(exc),
      )
      self._log(notification.id, "workflow_backlog", "failed", str(exc), trace_id=trace_id)

  def _finish_item(
    self,
    ctx: RegOpsContext,
    *,
    item: ScrapedNotification,
    regulator: str,
    stats: dict,
    post_ticket_agents: list,
    item_stats: dict | None = None,
    skip_pre_ticket_emit: bool = False,
  ) -> None:
    if not ctx.analysis or not ctx.notification_id:
      return

    if not skip_pre_ticket_emit:
      self._emit(
        "regulation_classified",
        f"AI classified {ctx.analysis.priority} risk",
        f"{ctx.item.title[:120]} — domain {ctx.analysis.regulatory_domain}",
        severity=(
          "critical"
          if ctx.analysis.priority == "CRITICAL"
          else "warning"
          if ctx.analysis.priority == "HIGH"
          else "info"
        ),
        ctx=ctx,
      )

    if not ctx.predictions:
      ctx.predictions = self._predictive.assess(
        notification_id=ctx.notification_id,
        regulator_code=regulator,
        analysis=ctx.analysis,
        historical_memories=ctx.historical_memories,
      )

    explainer = ExplainabilityEngine(self._db)
    explainer.explain_risk(
      notification_id=ctx.notification_id,
      analysis=ctx.analysis,
      predictions=ctx.predictions,
      historical_memories=ctx.historical_memories,
    )
    if ctx.routing:
      explainer.explain_routing(
        notification_id=ctx.notification_id,
        analysis=ctx.analysis,
        routing=ctx.routing,
      )
    if ctx.escalation:
      explainer.explain_escalation(
        notification_id=ctx.notification_id,
        analysis=ctx.analysis,
        escalation=ctx.escalation,
      )

    if ctx.analysis.priority in ("HIGH", "CRITICAL"):
      CollaborationService(self._db).propose(
        notification_id=ctx.notification_id,
        proposal_type="escalation",
        proposal={
          "summary": ctx.analysis.executive_summary[:300],
          "priority": ctx.analysis.priority,
          "regulator_code": regulator,
        },
      )

    for agent in post_ticket_agents:
      ctx = agent.run(ctx)

    if ctx.war_room.get("activated"):
      self._emit(
        "war_room_activated",
        "War room activated",
        f"Coordination room live for {ctx.analysis.priority} regulation.",
        severity="critical",
        ctx=ctx,
      )

    if ctx.escalation and ctx.escalation.requires_executive:
      self._emit(
        "escalation_triggered",
        "Executive escalation triggered",
        ctx.escalation.timeline_note or "Executive path engaged.",
        severity="warning",
        ctx=ctx,
      )

    strategic = StrategicInterpreter().interpret(ctx.analysis, regulator_code=regulator)
    self._emit(
      "strategic_insight",
      "Why this matters",
      strategic.get("why_this_matters", "")[:300],
      severity="info",
      ctx=ctx,
      payload=strategic,
    )

    self._memory_agent.persist(ctx)

    stats["obligations_extracted"] = stats.get("obligations_extracted", 0) + len(ctx.obligations)
    merge_from = item_stats if item_stats is not None else ctx.stats
    stats.update(
      {
        k: stats.get(k, 0) + merge_from.get(k, 0)
        for k in ("tickets_created", "subtasks_created", "war_rooms", "skipped_duplicate")
      }
    )

    if ctx.escalation and ctx.escalation.requires_executive:
      from app.services.notifications.alerts import notify_escalation

      notify_escalation(
        title=item.title, priority=ctx.analysis.priority, url=item.url
      )

  def process_single(self, item: ScrapedNotification, *, trace_id: str | None = None) -> RegOpsContext:
    """Process one notification through full agent chain (manual replay)."""
    trace_id = trace_id or uuid.uuid4().hex
    stats: dict = {}
    ctx = RegOpsContext(
      trace_id=trace_id,
      regulator_code=item.regulator_code,
      item=item,
      stats=stats,
    )
    pre_agents = [
      IngestionAgent(self._db),
      ApplicabilityAgent(self._db),
      ClassificationAgent(self._db),
      self._memory_agent,
      RiskAnalysisAgent(self._db),
      HistoricalCorrelationAgent(self._db),
      ObligationExtractionAgent(self._db),
    ]
    post_ticket_agents = [
      WorkflowOrchestrationAgent(self._db),
      KnowledgeGraphAgent(self._db),
      ExecutiveEscalationAgent(self._db),
    ]
    for agent in pre_agents:
      ctx = agent.run(ctx)
    if ctx.analysis and ctx.notification_id:
      self._finish_item(
        ctx,
        item=item,
        regulator=ctx.regulator_code,
        stats=stats,
        post_ticket_agents=post_ticket_agents,
      )
    return ctx

  def _emit(
    self,
    event_type: str,
    title: str,
    narrative: str,
    *,
    severity: str = "info",
    ctx: RegOpsContext,
    payload: dict | None = None,
  ) -> None:
    self._emitter.emit(
      event_type=event_type,
      title=title,
      narrative=narrative,
      severity=severity,
      regulator_code=ctx.regulator_code,
      notification_id=ctx.notification_id,
      trace_id=ctx.trace_id,
      payload=payload,
    )

  def _log(
    self,
    notification_id: int | None,
    stage: str,
    status: str,
    message: str | None = None,
    *,
    trace_id: str,
  ) -> None:
    self._db.add(
      ProcessingLog(
        notification_id=notification_id,
        stage=stage,
        status=status,
        message=message,
        trace_id=trace_id,
      )
    )
    self._db.commit()
