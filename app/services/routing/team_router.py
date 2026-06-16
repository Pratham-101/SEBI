"""Intelligent team routing for regulatory notifications."""

from __future__ import annotations

import re
from dataclasses import dataclass

import structlog

from app.schemas.analysis import RegulatoryAnalysisOutput

logger = structlog.get_logger(__name__)

# Canonical DevRev routing teams (only valid targets)
TEAM_LEGAL = "Legal Team"
TEAM_COMPLIANCE = "Compliance Team"
TEAM_FINANCE = "Finance Team"
TEAM_OPERATIONS = "Operations Team"
TEAM_INFOSEC = "InfoSec Team"
TEAM_EXECUTIVE = "Executive Leaders Team"

CANONICAL_TEAMS = [
    TEAM_LEGAL,
    TEAM_COMPLIANCE,
    TEAM_FINANCE,
    TEAM_OPERATIONS,
    TEAM_INFOSEC,
    TEAM_EXECUTIVE,
]

TEAM_TAG_SLUGS: dict[str, str] = {
    TEAM_LEGAL: "legal",
    TEAM_COMPLIANCE: "compliance",
    TEAM_FINANCE: "finance",
    TEAM_OPERATIONS: "operations",
    TEAM_INFOSEC: "infosec",
    TEAM_EXECUTIVE: "executive",
}

# Alias map: lowercase key -> canonical team name
TEAM_ALIASES: dict[str, str] = {
    "legal": TEAM_LEGAL,
    "legal team": TEAM_LEGAL,
    "compliance": TEAM_COMPLIANCE,
    "compliance team": TEAM_COMPLIANCE,
    "finance": TEAM_FINANCE,
    "finance team": TEAM_FINANCE,
    "operations": TEAM_OPERATIONS,
    "operations team": TEAM_OPERATIONS,
    "surveillance/operations team": TEAM_OPERATIONS,
    "surveillance team": TEAM_OPERATIONS,
    "infosec": TEAM_INFOSEC,
    "infosec team": TEAM_INFOSEC,
    "security team": TEAM_INFOSEC,
    "it/security team": TEAM_INFOSEC,
    "it security team": TEAM_INFOSEC,
    "cybersecurity team": TEAM_INFOSEC,
    "risk team": TEAM_COMPLIANCE,
    "investor relations": TEAM_COMPLIANCE,
    "investor relations team": TEAM_COMPLIANCE,
    "executive leadership": TEAM_EXECUTIVE,
    "executive leaders team": TEAM_EXECUTIVE,
    "executive team": TEAM_EXECUTIVE,
}

ROUTING_RULES: list[tuple[re.Pattern[str], list[str]]] = [
    (re.compile(r"\b(aml|kyc|onboard|fpi|pan\b|customer due diligence)\b", re.I), [TEAM_COMPLIANCE]),
    (re.compile(r"\b(penalt|enforcement|adjudication|litigation|appeal|order)\b", re.I), [TEAM_LEGAL]),
    (re.compile(r"\b(mutual fund|amc|nav|disclosure|securities|ipo|udrhp)\b", re.I), [TEAM_FINANCE]),
    (re.compile(r"\b(cyber|infosec|security breach|it security|cscrf)\b", re.I), [TEAM_INFOSEC]),
    (re.compile(r"\b(surveillance|governance|risk management|internal control)\b", re.I), [TEAM_COMPLIANCE]),
    (re.compile(r"\b(workflow|process|operational|sop|implementation)\b", re.I), [TEAM_OPERATIONS]),
    (re.compile(r"\b(investor|shareholder|ir\b|press release)\b", re.I), [TEAM_COMPLIANCE]),
]

PRIORITY_OWNER_TEAM: dict[str, str] = {
    "CRITICAL": TEAM_LEGAL,
    "HIGH": TEAM_COMPLIANCE,
    "MEDIUM": TEAM_COMPLIANCE,
    "LOW": TEAM_OPERATIONS,
}


def normalize_team(name: str) -> str:
    """Map any AI or rule-suggested team name to one of the 6 canonical teams."""
    if not name or not name.strip():
        return TEAM_COMPLIANCE

    cleaned = " ".join(name.strip().split())
    key = cleaned.lower()

    if cleaned in CANONICAL_TEAMS:
        return cleaned

    if key in TEAM_ALIASES:
        return TEAM_ALIASES[key]

    for alias, canonical in TEAM_ALIASES.items():
        if alias in key or key in alias:
            return canonical

    for canonical in CANONICAL_TEAMS:
        if canonical.lower() in key or key in canonical.lower():
            return canonical

    logger.warning("team_normalization_fallback", original=name, fallback=TEAM_COMPLIANCE)
    return TEAM_COMPLIANCE


def team_to_tag_slug(team: str) -> str:
    canonical = normalize_team(team)
    return TEAM_TAG_SLUGS.get(canonical, "compliance")


@dataclass
class RoutingDecision:
    primary_team: str
    teams_to_notify: list[str]
    devrev_group_name: str
    severity: str
    escalation_tags: list[str]


class TeamRouter:
    """Rule-enhanced routing layered on top of AI team classification."""

    def route(
        self,
        analysis: RegulatoryAnalysisOutput,
        *,
        title: str,
        body_text: str,
    ) -> RoutingDecision:
        text = f"{title}\n{body_text}\n{' '.join(analysis.related_themes)}"
        rule_teams: set[str] = set()

        for pattern, teams in ROUTING_RULES:
            if pattern.search(text):
                rule_teams.update(teams)

        ai_teams = {normalize_team(t) for t in (analysis.teams_to_notify or analysis.affected_teams)}
        merged = sorted(rule_teams | ai_teams)

        if not merged:
            merged = [TEAM_COMPLIANCE]

        primary = normalize_team(analysis.suggested_owner_team)
        if primary not in CANONICAL_TEAMS:
            primary = normalize_team(PRIORITY_OWNER_TEAM.get(analysis.priority, TEAM_COMPLIANCE))

        if analysis.requires_executive_escalation or analysis.priority == "CRITICAL":
            if TEAM_EXECUTIVE not in merged:
                merged.append(TEAM_EXECUTIVE)

        if analysis.compliance_exposure.lower().startswith("high"):
            if TEAM_COMPLIANCE not in merged:
                merged.insert(0, TEAM_COMPLIANCE)

        merged = sorted(set(normalize_team(t) for t in merged))

        severity = self._map_severity(analysis.priority)
        escalation_tags: list[str] = []

        if analysis.requires_executive_escalation:
            escalation_tags.extend(["executive-attention", "urgent-review"])
        if analysis.priority in ("CRITICAL", "HIGH"):
            escalation_tags.append(f"priority-{analysis.priority.lower()}")

        return RoutingDecision(
            primary_team=primary,
            teams_to_notify=merged,
            devrev_group_name=primary,
            severity=severity,
            escalation_tags=escalation_tags,
        )

    @staticmethod
    def _map_severity(priority: str) -> str:
        return {
            "CRITICAL": "blocker",
            "HIGH": "high",
            "MEDIUM": "medium",
            "LOW": "low",
        }.get(priority.upper(), "medium")
