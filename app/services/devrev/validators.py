"""Validation helpers for DevRev payloads."""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


EXTERNAL_REF_MAX = 512
TITLE_MAX = 256
BODY_MAX = 65536


class DevRevTicketCreateRequest(BaseModel):
    # Allow forward-compatible extra keys (e.g. tenant custom date fields).
    model_config = ConfigDict(extra="allow")

    type: str = "ticket"
    title: str = Field(..., min_length=1, max_length=TITLE_MAX)
    body: str = Field(default="", max_length=BODY_MAX)
    applies_to_part: str = Field(..., min_length=1)
    priority: str | None = None
    external_ref: str | None = Field(default=None, max_length=EXTERNAL_REF_MAX)
    owned_by: list[str] | None = None
    tags: list[dict[str, str]] | None = None
    group: str | None = None
    severity: str | None = None
    custom_fields: dict[str, Any] | None = None

    @field_validator("severity")
    @classmethod
    def validate_severity(cls, v: str | None) -> str | None:
        if v is None:
            return v
        allowed = {"blocker", "high", "medium", "low"}
        if v not in allowed:
            raise ValueError(f"severity must be one of {allowed}")
        return v

    @field_validator("priority")
    @classmethod
    def validate_priority(cls, v: str | None) -> str | None:
        if v is None:
            return v
        allowed = {"p0", "p1", "p2", "p3"}
        if v not in allowed:
            raise ValueError(f"priority must be one of {allowed}")
        return v

    @field_validator("external_ref")
    @classmethod
    def sanitize_external_ref(cls, v: str | None) -> str | None:
        if v is None:
            return v
        cleaned = re.sub(r"[^\w\-.:]+", "_", v)[:EXTERNAL_REF_MAX]
        return cleaned


class DevRevTicketUpdateRequest(BaseModel):
    id: str
    title: str | None = Field(default=None, max_length=TITLE_MAX)
    body: str | None = Field(default=None, max_length=BODY_MAX)
    priority: str | None = None
    tags: list[dict[str, str]] | None = None
