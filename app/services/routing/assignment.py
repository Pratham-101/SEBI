"""Person-level assignment — resolve a ticket/child to a real DevRev user.

Routing (team_router.py) decides WHICH team. This engine decides WHO inside that
team, scoring each candidate by:

    score = skill_match^w_skill * (1 - load)^w_load * seniority_fit^w_sen

where:
- skill_match   = overlap between the regulation's domain/tags and the person's
                  expertise slugs (0..1)
- load          = current open-ticket count / capacity (0..1), live from DevRev
                  works.list when enabled, else estimated from local Ticket rows
- seniority_fit = how well the person's seniority matches the ticket priority
                  (CRITICAL wants senior people; LOW is fine with juniors)

The result carries the chosen owner, a human-readable rationale, and the manager
id for CRITICAL escalation notifies.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import structlog
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.team_member import TeamMember
from app.models.ticket import Ticket
from app.schemas.analysis import RegulatoryAnalysisOutput
from app.services.devrev.client import DevRevAPIError, DevRevClient
from app.services.routing.team_router import normalize_team

logger = structlog.get_logger(__name__)

# Seniority a given priority ideally wants (1..5).
PRIORITY_TARGET_SENIORITY: dict[str, int] = {
    "CRITICAL": 5,
    "HIGH": 4,
    "MEDIUM": 3,
    "LOW": 2,
}


@dataclass
class AssignmentDecision:
    """Outcome of person-level assignment for one work item."""

    user_id: str | None
    display_name: str | None
    team: str
    rationale: str
    manager_user_id: str | None = None
    score: float = 0.0
    runner_up: str | None = None
    candidates_considered: int = 0
    metadata: dict = field(default_factory=dict)

    @property
    def assigned(self) -> bool:
        return bool(self.user_id)


def _expertise_slugs(analysis: RegulatoryAnalysisOutput) -> set[str]:
    """Slugs describing this regulation, used to match member expertise."""
    slugs: set[str] = set()
    domain = (analysis.regulatory_domain or "").strip().lower()
    if domain:
        slugs.add(domain)
        slugs.update(domain.replace("_", "-").split("-"))
    for tag in analysis.tags or []:
        t = tag.strip().lower()
        if not t or t.startswith("don:"):
            continue
        slugs.add(t)
        slugs.update(t.replace("_", "-").split("-"))
    for theme in analysis.related_themes or []:
        slugs.add(theme.strip().lower())
    # Drop noise tokens that match everything.
    slugs.discard("")
    return {s for s in slugs if len(s) >= 3}


class AssignmentEngine:
    """Pick the best individual owner within a routed team."""

    def __init__(self, db: Session, client: DevRevClient | None = None) -> None:
        self._db = db
        self._settings = get_settings()
        self._client = client
        # Cache live DevRev load lookups within a single pipeline tick.
        self._load_cache: dict[str, int] = {}

    # ----- roster loading -------------------------------------------------

    def sync_roster(self, path: str | None = None) -> int:
        """Upsert roster.json into team_members. Returns rows written."""
        roster_path = Path(path or self._settings.assignment_roster_path)
        if not roster_path.is_absolute():
            roster_path = Path.cwd() / roster_path
        if not roster_path.is_file():
            logger.warning("roster_file_missing", path=str(roster_path))
            return 0

        data = json.loads(roster_path.read_text())
        members = data.get("members", [])
        written = 0
        for m in members:
            user_id = (m.get("devrev_user_id") or "").strip()
            if not user_id:
                continue
            row = (
                self._db.query(TeamMember)
                .filter(TeamMember.devrev_user_id == user_id)
                .first()
            )
            if not row:
                row = TeamMember(devrev_user_id=user_id)
                self._db.add(row)
            row.display_name = m.get("display_name", user_id)
            row.email = m.get("email")
            row.team = normalize_team(m.get("team", "Compliance Team"))
            row.expertise_json = json.dumps(
                [str(s).strip().lower() for s in m.get("expertise", [])]
            )
            row.seniority = int(m.get("seniority", 3))
            row.capacity = int(m.get("capacity", 10))
            row.manager_user_id = m.get("manager_user_id")
            row.active = bool(m.get("active", True))
            written += 1
        self._db.commit()
        logger.info("roster_synced", members=written, path=str(roster_path))
        return written

    def _candidates(self, team: str) -> list[TeamMember]:
        return (
            self._db.query(TeamMember)
            .filter(TeamMember.team == team, TeamMember.active.is_(True))
            .all()
        )

    # ----- load estimation ------------------------------------------------

    def _open_load(self, member: TeamMember) -> int:
        """Open-ticket count for a member, live from DevRev or local fallback."""
        if member.devrev_user_id in self._load_cache:
            return self._load_cache[member.devrev_user_id]

        count = 0
        if self._settings.assignment_use_live_load:
            count = self._live_devrev_load(member.devrev_user_id)
        if count == 0:
            # Fall back to (or supplement with) what we know locally.
            count = (
                self._db.query(Ticket)
                .filter(
                    Ticket.assignee_user_id == member.devrev_user_id,
                    Ticket.status.in_(("created", "open", "in_progress")),
                )
                .count()
            )
        self._load_cache[member.devrev_user_id] = count
        return count

    def _live_devrev_load(self, user_id: str) -> int:
        client = self._client or DevRevClient()
        try:
            resp = client.post(
                "works.list",
                json_body={
                    "owned_by": [user_id],
                    "state": ["open"],
                    "limit": 50,
                },
            )
        except (DevRevAPIError, Exception) as exc:  # noqa: BLE001 — degrade gracefully
            logger.warning("live_load_lookup_failed", user_id=user_id, error=str(exc))
            return 0
        return len(resp.get("works", []) or [])

    # ----- scoring --------------------------------------------------------

    def _score(
        self,
        member: TeamMember,
        *,
        wanted: set[str],
        target_seniority: int,
    ) -> tuple[float, dict]:
        try:
            expertise = set(json.loads(member.expertise_json or "[]"))
        except json.JSONDecodeError:
            expertise = set()

        overlap = wanted & expertise
        # Skill: fraction of wanted slugs the person covers, with a small floor
        # so a same-team generalist is still assignable when nothing matches.
        skill = (len(overlap) / len(wanted)) if wanted else 0.0
        skill = max(skill, 0.15)
        skill = min(skill, 1.0)

        load_ratio = self._open_load(member) / max(member.capacity, 1)
        availability = max(0.0, 1.0 - min(load_ratio, 1.0))

        # Seniority fit: 1.0 when exact, decaying with distance. Being too senior
        # is penalized less than being too junior for the priority.
        diff = member.seniority - target_seniority
        if diff >= 0:
            seniority_fit = max(0.4, 1.0 - 0.15 * diff)
        else:
            seniority_fit = max(0.2, 1.0 - 0.3 * abs(diff))

        s = self._settings
        score = (
            (skill ** s.assignment_skill_weight)
            * (max(availability, 0.01) ** s.assignment_load_weight)
            * (seniority_fit ** s.assignment_seniority_weight)
        )
        breakdown = {
            "skill": round(skill, 3),
            "availability": round(availability, 3),
            "seniority_fit": round(seniority_fit, 3),
            "open_load": self._open_load(member),
            "capacity": member.capacity,
            "matched_expertise": sorted(overlap),
        }
        return score, breakdown

    # ----- public API -----------------------------------------------------

    def assign(
        self,
        *,
        analysis: RegulatoryAnalysisOutput,
        team: str,
        owner_team_override: str | None = None,
    ) -> AssignmentDecision:
        """Choose the best individual within `team` for this regulation."""
        canonical = normalize_team(owner_team_override or team)
        if not self._settings.assignment_enabled:
            return AssignmentDecision(
                user_id=None,
                display_name=None,
                team=canonical,
                rationale="Person-level assignment disabled; routed to team only.",
            )

        candidates = self._candidates(canonical)
        if not candidates:
            return AssignmentDecision(
                user_id=None,
                display_name=None,
                team=canonical,
                rationale=(
                    f"No roster members for {canonical}; routed to team group only. "
                    f"Seed data/roster.json and run sync_roster()."
                ),
            )

        wanted = _expertise_slugs(analysis)
        target_seniority = PRIORITY_TARGET_SENIORITY.get(analysis.priority, 3)

        scored = [
            (member, *self._score(member, wanted=wanted, target_seniority=target_seniority))
            for member in candidates
        ]
        scored.sort(key=lambda x: x[1], reverse=True)

        best, best_score, breakdown = scored[0]
        runner_up = scored[1][0].display_name if len(scored) > 1 else None

        rationale = (
            f"Assigned to {best.display_name} ({canonical}, seniority {best.seniority}). "
            f"Skill match {breakdown['skill']} "
            f"(expertise: {', '.join(breakdown['matched_expertise']) or 'general'}), "
            f"availability {breakdown['availability']} "
            f"({breakdown['open_load']}/{breakdown['capacity']} open), "
            f"seniority fit {breakdown['seniority_fit']} for {analysis.priority}."
        )
        if runner_up:
            rationale += f" Runner-up: {runner_up}."

        logger.info(
            "person_assigned",
            team=canonical,
            assignee=best.display_name,
            score=round(best_score, 4),
            priority=analysis.priority,
            **breakdown,
        )

        return AssignmentDecision(
            user_id=best.devrev_user_id,
            display_name=best.display_name,
            team=canonical,
            rationale=rationale,
            manager_user_id=best.manager_user_id,
            score=round(best_score, 4),
            runner_up=runner_up,
            candidates_considered=len(candidates),
            metadata=breakdown,
        )
