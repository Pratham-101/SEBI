"""Executive intelligence briefings — daily/weekly summaries."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.memory.retrieval import MemoryRetrieval
from app.models.analysis_result import AnalysisResult
from app.models.escalation_record import EscalationRecord
from app.models.notification import Notification
from app.models.obligation import Obligation
from app.obligations.lifecycle import ObligationLifecycle


class BriefingGenerator:
  def __init__(self, db: Session) -> None:
    self._db = db
    self._obligations = ObligationLifecycle(db)
    self._memory = MemoryRetrieval(db)

  def generate(self, *, period: str = "daily", regulator_code: str | None = None) -> dict:
    days = 1 if period == "daily" else 7
    since = datetime.now(timezone.utc) - timedelta(days=days)

    q = self._db.query(Notification).filter(Notification.created_at >= since)
    if regulator_code:
      q = q.filter(Notification.regulator_code == regulator_code)
    recent = q.order_by(Notification.created_at.desc()).limit(50).all()

    high_risk = (
      self._db.query(AnalysisResult)
      .filter(
        AnalysisResult.created_at >= since,
        AnalysisResult.priority.in_(("HIGH", "CRITICAL")),
      )
      .order_by(AnalysisResult.risk_score.desc().nullslast())
      .limit(10)
      .all()
    )

    open_obligations = self._obligations.list_open(regulator_code=regulator_code, limit=20)
    unresolved_memory = self._memory.unresolved_risks(regulator_code=regulator_code)

    active_escalations = (
      self._db.query(EscalationRecord)
      .filter(EscalationRecord.status == "active")
      .order_by(EscalationRecord.created_at.desc())
      .limit(10)
      .all()
    )

    team_load = (
      self._db.query(Obligation.owner_team, func.count(Obligation.id))
      .filter(Obligation.status.in_(("open", "in_progress")))
      .group_by(Obligation.owner_team)
      .all()
    )

    return {
      "period": period,
      "generated_at": datetime.now(timezone.utc).isoformat(),
      "regulator_code": regulator_code,
      "summary": {
        "new_regulations": len(recent),
        "high_critical_items": len(high_risk),
        "open_obligations": len(open_obligations),
        "active_escalations": len(active_escalations),
        "unresolved_risk_signals": len(unresolved_memory),
      },
      "top_regulatory_risks": [
        {
          "notification_id": r.notification_id,
          "priority": r.priority,
          "risk_score": r.risk_score,
        }
        for r in high_risk
      ],
      "approaching_deadlines": self._obligations.approaching_deadlines()[:10],
      "unresolved_obligations": open_obligations[:15],
      "compliance_bottlenecks": [
        {"team": t, "open_count": c} for t, c in sorted(team_load, key=lambda x: -x[1])
      ],
      "team_overload_indicators": [
        {"team": t, "open_count": c}
        for t, c in team_load
        if c >= 5
      ],
      "trend_analysis": {
        "regulations_ingested": len(recent),
        "war_rooms_active": len(active_escalations),
        "recurring_themes": [m["theme"] for m in unresolved_memory[:5]],
      },
      "recent_titles": [n.title for n in recent[:8]],
    }
