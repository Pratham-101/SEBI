"""Pydantic schemas for AI regulatory intelligence."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field, field_validator


class PriorityLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class ImportantDate(BaseModel):
    """A labeled regulatory date extracted from source material."""

    label: str = Field(..., min_length=2, max_length=80)
    date_text: str = Field(..., min_length=2, max_length=120)
    source_basis: str = Field(
        default="",
        description="Brief quote or reference from source supporting this date",
    )


class ActionableInsight(BaseModel):
    """Operationally executable insight with optional team mapping."""

    action: str = Field(..., min_length=15, max_length=500)
    owner_team: str = Field(..., min_length=2, max_length=64)
    urgency: str = Field(default="standard", max_length=32)
    dependencies: str = Field(default="", max_length=300)


class RegulatoryAnalysisOutput(BaseModel):
    """Structured regulatory operations intelligence from OpenAI."""

    ticket_title: str = Field(..., min_length=3, max_length=240)
    executive_summary: str = Field(..., min_length=80)
    notification_type: str
    regulatory_domain: str = Field(
        ...,
        description="e.g. mutual-funds, fpi-onboarding, enforcement, surveillance",
    )
    priority: str
    compliance_risk: str = Field(..., min_length=20)
    operational_risk: str = Field(..., min_length=20)
    operational_impact_analysis: str = Field(..., min_length=40)
    risk_assessment: str = Field(..., min_length=40)
    legal_exposure: str = Field(..., min_length=10)
    compliance_exposure: str = Field(..., min_length=10)
    reporting_burden: str = Field(..., min_length=10)
    reputational_impact: str = Field(..., min_length=10)
    affected_teams: list[str] = Field(default_factory=list, min_length=1)
    teams_to_notify: list[str] = Field(default_factory=list, min_length=1)
    suggested_owner_team: str = Field(..., min_length=2, max_length=64)
    actionable_insights: list[ActionableInsight] = Field(..., min_length=4, max_length=8)
    immediate_actions: list[str] = Field(default_factory=list, min_length=1, max_length=6)
    important_dates: list[ImportantDate] = Field(default_factory=list)
    deadlines: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    key_regulatory_changes: list[str] = Field(..., min_length=1)
    facts_from_source: list[str] = Field(..., min_length=1)
    inferences: list[str] = Field(default_factory=list)
    related_themes: list[str] = Field(default_factory=list)
    requires_immediate_attention: bool = False
    requires_executive_escalation: bool = False
    confidence_score: float = Field(..., ge=0.0, le=1.0)

    # Backward-compatible alias used by older code paths
    @property
    def action_items(self) -> list[str]:
        return [i.action for i in self.actionable_insights]

    @field_validator("priority")
    @classmethod
    def normalize_priority(cls, v: str) -> str:
        upper = v.strip().upper()
        allowed = {p.value for p in PriorityLevel}
        if upper not in allowed:
            return PriorityLevel.MEDIUM.value
        return upper

    @field_validator("affected_teams", "teams_to_notify")
    @classmethod
    def normalize_teams(cls, v: list[str]) -> list[str]:
        return [t.strip() for t in v if t.strip()]
