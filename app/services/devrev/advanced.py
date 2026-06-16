"""Advanced DevRev command-center operations."""

from __future__ import annotations

import structlog

from app.schemas.analysis import RegulatoryAnalysisOutput
from app.services.devrev.client import DevRevClient
from app.services.devrev.comments import DevRevCommentService
from app.services.routing.team_router import RoutingDecision

logger = structlog.get_logger(__name__)


class DevRevAdvancedService:
  """SLA notes, watchers, stage hints, intelligence overlays on works."""

  def __init__(self) -> None:
    self._client = DevRevClient()
    self._comments = DevRevCommentService()

  def apply_command_center(
    self,
    *,
    work_id: str,
    analysis: RegulatoryAnalysisOutput,
    routing: RoutingDecision,
    predictions: dict,
    historical_memories: list[dict],
  ) -> None:
    sections = [
      "## RegOps Command Center",
      f"- **Severity track:** {routing.severity}",
      f"- **Primary team:** {routing.primary_team}",
      f"- **Operational exposure:** {predictions.get('operational_exposure', 'n/a')}",
      f"- **Escalation probability:** {predictions.get('escalation_probability', 'n/a')}",
    ]
    if predictions.get("likely_impacted_systems"):
      sections.append(
        f"- **Impacted systems:** {', '.join(predictions['likely_impacted_systems'])}"
      )
    if historical_memories:
      sections.append("\n### Organizational memory")
      for m in historical_memories[:3]:
        sections.append(f"- {m.get('historical_note', m.get('summary', ''))[:200]}")

    self._comments.add_comment(work_id=work_id, body="\n".join(sections))

  def set_stage(self, work_id: str, *, stage_hint: str = "in_progress") -> None:
    # Stage names are workspace-specific and 400 on tenants that lack them.
    # Skip unless explicitly enabled for a workspace known to have the stage.
    from app.core.config import get_settings

    if not get_settings().devrev_set_stage_hint:
      return
    try:
      self._client.post(
        "works.update",
        json_body={
          "id": work_id,
          "stage": {"name": stage_hint},
        },
      )
    except Exception as exc:
      logger.warning("devrev_stage_update_failed", work_id=work_id, error=str(exc))

  def add_watcher_comment(self, work_id: str, watchers: list[str]) -> None:
    if not watchers:
      return
    body = "**Watchers / subscribers:**\n" + "\n".join(f"- {w}" for w in watchers)
    self._comments.add_comment(work_id=work_id, body=body)

