"""AI output validation and hallucination guardrails."""

from __future__ import annotations

import re

from pydantic import ValidationError

from app.core.config import get_settings
from app.schemas.analysis import PriorityLevel, RegulatoryAnalysisOutput


class GovernanceResult:
    def __init__(
        self,
        *,
        approved: bool,
        requires_human_review: bool,
        escalated: bool,
        reasons: list[str],
        analysis: RegulatoryAnalysisOutput | None = None,
    ) -> None:
        self.approved = approved
        self.requires_human_review = requires_human_review
        self.escalated = escalated
        self.reasons = reasons
        self.analysis = analysis


class AIOutputValidator:
    """Validate structured AI output against source content."""

    DATE_PATTERN = re.compile(
        r"\b(\d{1,2}[-/]\d{1,2}[-/]\d{2,4}|\d{1,2}\s+\w+\s+\d{4}|may\s+\d{4})\b",
        re.I,
    )

    def validate(
        self,
        analysis: RegulatoryAnalysisOutput,
        *,
        source_text: str,
    ) -> GovernanceResult:
        settings = get_settings()
        reasons: list[str] = []
        source_lower = (source_text or "").lower()

        if analysis.confidence_score < settings.human_review_confidence_threshold:
            reasons.append("confidence_below_human_review_threshold")

        if analysis.confidence_score < settings.ai_confidence_threshold:
            reasons.append("confidence_below_auto_approval_threshold")

        if len(analysis.facts_from_source) < 1:
            reasons.append("missing_source_facts")

        cited = 0
        for d in analysis.important_dates:
            if d.date_text.lower() not in source_lower and not self._date_in_source(
                d.date_text, source_text
            ):
                reasons.append(f"unverified_date:{d.label[:30]}")
            # Citation grounding: the verbatim source_basis quote must be present.
            basis = (d.source_basis or "").strip().lower()
            if basis and basis in source_lower:
                cited += 1

        # If too few dates carry a verifiable citation, flag for human review.
        if analysis.important_dates:
            ratio = cited / len(analysis.important_dates)
            if ratio < settings.citation_min_supported_ratio:
                reasons.append(f"weak_citations:{cited}/{len(analysis.important_dates)}")

        for deadline in analysis.deadlines:
            if deadline.lower() in ("none", "n/a", "not specified"):
                continue
            if deadline.lower() not in source_lower and not self._date_in_source(
                deadline, source_text
            ):
                reasons.append(f"unverified_deadline:{deadline[:40]}")

        if analysis.priority == PriorityLevel.CRITICAL.value:
            critical_keywords = (
                "penalty",
                "enforcement",
                "order",
                "deadline",
                "immediate",
                "fine",
                "prohibition",
            )
            if not any(kw in source_lower for kw in critical_keywords):
                if analysis.confidence_score < 0.85:
                    reasons.append("critical_priority_without_source_support")

        if len(analysis.inferences) > 8:
            reasons.append("excessive_inferences")

        unverified = [r for r in reasons if r.startswith("unverified_")]
        weak_citation = [r for r in reasons if r.startswith("weak_citations")]
        requires_human = (
            analysis.confidence_score < settings.human_review_confidence_threshold
            or analysis.requires_immediate_attention
            or bool(unverified)
            or bool(weak_citation)
            or len(analysis.inferences) > 5
        )

        escalated = (
            analysis.requires_executive_escalation
            or analysis.priority in (PriorityLevel.CRITICAL.value, PriorityLevel.HIGH.value)
        )

        approved = (
            analysis.confidence_score >= settings.ai_confidence_threshold
            and not unverified
            and not weak_citation
        )

        return GovernanceResult(
            approved=approved,
            requires_human_review=requires_human,
            escalated=escalated,
            reasons=reasons,
            analysis=analysis,
        )

    @staticmethod
    def _date_in_source(deadline: str, source: str) -> bool:
        for match in AIOutputValidator.DATE_PATTERN.findall(source):
            if match.lower() in deadline.lower():
                return True
        return False

    @staticmethod
    def parse_structured(data: dict) -> RegulatoryAnalysisOutput:
        try:
            return RegulatoryAnalysisOutput.model_validate(data)
        except ValidationError as exc:
            raise ValueError(f"Invalid AI schema: {exc}") from exc
