"""LLM client factory — resolves OpenAI or Groq from settings.

Groq exposes an OpenAI-compatible REST API, so the same `openai` SDK works by
pointing `base_url` at Groq and using the Groq key. The only behavioural
difference we care about is structured output: OpenAI supports strict
`json_schema`, Groq only `json_object` — callers check settings.supports_json_schema.
"""

from __future__ import annotations

import structlog
from openai import OpenAI

from app.core.config import get_settings

logger = structlog.get_logger(__name__)


def build_llm_client() -> OpenAI | None:
    """Return an OpenAI-SDK client bound to the active provider, or None."""
    settings = get_settings()
    key = settings.active_llm_key
    if not key:
        return None
    kwargs: dict = {"api_key": key}
    base_url = settings.active_llm_base_url
    if base_url:
        kwargs["base_url"] = base_url
    logger.info("llm_client_built", provider=settings.llm_provider, model=settings.active_llm_model)
    return OpenAI(**kwargs)


def active_model() -> str:
    return get_settings().active_llm_model
