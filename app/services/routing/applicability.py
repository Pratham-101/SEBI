"""Applicability scoring — does a SEBI item actually apply to this org?

Runs after ingestion (body text available) and BEFORE the expensive AI
classification call, so irrelevant circulars (e.g. an AMC-only notification for a
firm that isn't an AMC) are filtered cheaply instead of generating ticket noise.

Score is keyword/profile based (0..1):
- exclusion keywords present        -> hard floor toward 0
- high-relevance keyword hits       -> strong positive
- low-relevance keyword hits        -> mild positive
- intermediary/business/product hits-> positive

The org profile lives in data/org_profile.json (see applicability_profile_path).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import structlog

from app.core.config import get_settings

logger = structlog.get_logger(__name__)


@dataclass
class ApplicabilityResult:
    score: float
    applicable: bool
    matched: list[str] = field(default_factory=list)
    excluded_by: list[str] = field(default_factory=list)
    rationale: str = ""


@lru_cache(maxsize=1)
def _load_profile(path: str) -> dict:
    profile_path = Path(path)
    if not profile_path.is_absolute():
        profile_path = Path.cwd() / profile_path
    if not profile_path.is_file():
        logger.warning("org_profile_missing", path=str(profile_path))
        return {}
    return json.loads(profile_path.read_text())


def _hits(haystack: str, needles: list[str]) -> list[str]:
    return [n for n in needles if n and n.lower() in haystack]


class ApplicabilityEngine:
    """Profile-driven relevance gate for incoming regulatory items."""

    def __init__(self) -> None:
        self._settings = get_settings()
        self._profile = _load_profile(self._settings.applicability_profile_path)

    def score(self, *, title: str, body_text: str, notification_type: str = "") -> ApplicabilityResult:
        if not self._settings.applicability_enabled or not self._profile:
            # Gate disabled or no profile -> everything is applicable.
            return ApplicabilityResult(
                score=1.0, applicable=True, rationale="Applicability gate disabled."
            )

        text = f"{title}\n{notification_type}\n{body_text}".lower()
        p = self._profile

        excluded = _hits(text, p.get("exclusion_keywords", []))
        high = _hits(text, p.get("high_relevance_keywords", []))
        low = _hits(text, p.get("low_relevance_keywords", []))
        inter = _hits(text, p.get("intermediary_types", []))
        biz = _hits(text, p.get("business_lines", []))
        prod = _hits(text, p.get("products", []))

        # Weighted, saturating contributions.
        score = 0.0
        score += min(0.6, 0.2 * len(high))
        score += min(0.3, 0.15 * len(inter))
        score += min(0.2, 0.1 * len(biz))
        score += min(0.2, 0.1 * len(prod))
        score += min(0.15, 0.05 * len(low))

        # Exclusions strongly suppress relevance.
        if excluded:
            score *= 0.25

        min_score = self._settings.applicability_ticket_min_score

        # A SEBI item with no positive signal AND no exclusions is treated as
        # weakly applicable (passes the gate). For a compliance system a false
        # negative — silently dropping a real obligation — is far costlier than
        # an extra ticket, so unknowns err toward being processed by the AI.
        if not (high or inter or biz or prod or low) and not excluded:
            score = max(score, min_score)

        score = round(min(1.0, score), 3)
        applicable = score >= min_score

        matched = sorted(set(high + inter + biz + prod + low))
        rationale = (
            f"Applicability {score} (threshold {min_score}). "
            f"Matched: {', '.join(matched) or 'none'}."
        )
        if excluded:
            rationale += f" Exclusions hit: {', '.join(excluded)}."

        return ApplicabilityResult(
            score=score,
            applicable=applicable,
            matched=matched,
            excluded_by=excluded,
            rationale=rationale,
        )
