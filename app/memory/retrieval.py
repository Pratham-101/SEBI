"""Retrieve organizational memory for historical reasoning."""

from __future__ import annotations

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.organizational_memory import OrganizationalMemory
from app.models.notification import Notification


class MemoryRetrieval:
  def __init__(self, db: Session) -> None:
    self._db = db

  def find_similar(
    self,
    *,
    regulator_code: str,
    themes: list[str],
    domain: str,
    limit: int = 5,
    query_text: str | None = None,
  ) -> list[dict]:
    if query_text:
      from app.memory.vector import VectorMemoryService

      return VectorMemoryService(self._db).semantic_search(
        query_text, regulator_code=regulator_code, limit=limit
      )
    if not themes and not domain:
      return []

    needles = [t.lower() for t in themes[:8]] + [domain.lower()]
    q = self._db.query(OrganizationalMemory).filter(
      OrganizationalMemory.regulator_code == regulator_code
    )
    clauses = []
    for needle in needles:
      if len(needle) < 3:
        continue
      clauses.append(OrganizationalMemory.theme.ilike(f"%{needle}%"))
      clauses.append(OrganizationalMemory.summary.ilike(f"%{needle}%"))
    if not clauses:
      return []
    rows = (
      q.filter(or_(*clauses))
      .order_by(OrganizationalMemory.created_at.desc())
      .limit(limit)
      .all()
    )
    results = []
    for row in rows:
      title = ""
      if row.notification_id:
        n = self._db.get(Notification, row.notification_id)
        title = n.title if n else ""
      results.append(
        {
          "memory_id": row.id,
          "memory_type": row.memory_type,
          "theme": row.theme,
          "summary": row.summary[:400],
          "outcome": row.outcome,
          "notification_id": row.notification_id,
          "title": title,
          "historical_note": (
            f"This resembles prior activity on '{row.theme}' "
            f"(outcome: {row.outcome or 'unknown'})."
          ),
        }
      )
    return results

  def unresolved_risks(self, regulator_code: str | None = None, limit: int = 10) -> list[dict]:
    q = self._db.query(OrganizationalMemory).filter(
      OrganizationalMemory.memory_type == "risk_signal",
      OrganizationalMemory.outcome.in_(["elevated", "open", "delayed"]),
    )
    if regulator_code:
      q = q.filter(OrganizationalMemory.regulator_code == regulator_code)
    rows = q.order_by(OrganizationalMemory.created_at.desc()).limit(limit).all()
    return [
      {
        "id": r.id,
        "theme": r.theme,
        "summary": r.summary[:300],
        "notification_id": r.notification_id,
      }
      for r in rows
    ]
