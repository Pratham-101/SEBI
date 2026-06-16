"""Application configuration loaded from environment."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # LLM provider: "openai" or "groq" (Groq is OpenAI-API-compatible).
    llm_provider: str = "openai"

    openai_api_key: str = ""
    openai_model: str = "gpt-4.1"

    # Groq (free tier; OpenAI-compatible endpoint). The free-tier quota resets
    # daily server-side using the SAME static key — no token rotation needed.
    groq_api_key: str = ""
    groq_base_url: str = "https://api.groq.com/openai/v1"
    groq_model: str = "llama-3.1-8b-instant"
    # Free-tier Groq is ~6000 tokens/min. Cap the source body so the request
    # (system prompt + schema + body + output) stays under that limit.
    groq_max_body_chars: int = 7000
    # Max output tokens requested from the LLM analysis call.
    llm_max_output_tokens: int = 1800

    devrev_api_token: str = ""
    devrev_base_url: str = "https://api.devrev.ai"
    devrev_default_part_id: str = ""
    devrev_default_owner_id: str = ""
    devrev_send_priority_field: bool = False
    devrev_workspace_url: str = ""
    devrev_group_legal: str = ""
    devrev_group_compliance: str = ""
    devrev_group_finance: str = ""
    devrev_group_operations: str = ""
    devrev_group_infosec: str = ""
    devrev_group_executive: str = ""
    devrev_webhook_secret: str = ""
    use_sync_pipeline: bool = False

    database_url: str = "postgresql+psycopg2://sebi:sebi@localhost:5432/sebi_regulatory"
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"

    cron_interval_minutes: int = 5
    sebi_listing_url: str = (
        "https://www.sebi.gov.in/sebiweb/home/HomeAction.do?doListingAll=yes"
    )
    sebi_scrape_limit: int = 25
    pipeline_backlog_batch_size: int = 25

    # Scraper reliability
    # How many times to retry the listing fetch before giving up the tick.
    scrape_max_attempts: int = 3
    # Playwright navigation timeout (ms) per attempt.
    scrape_nav_timeout_ms: int = 60_000
    # Dead-man's switch: alert if a scrape returns fewer than this many rows
    # (0 rows almost always means SEBI changed layout or blocked us).
    scrape_min_expected_rows: int = 3
    # Also alert if rows drop below this fraction of the recent rolling average.
    scrape_drop_alert_ratio: float = 0.5

    log_level: str = "INFO"
    environment: str = "development"

    ai_confidence_threshold: float = 0.75
    human_review_confidence_threshold: float = 0.55

    slack_webhook_url: str = ""
    alert_email_to: str = ""

    http_timeout_seconds: int = 60
    devrev_timeout_seconds: int = 30

    app_name: str = "RegOps OS — Regulatory Operations Platform"
    api_prefix: str = "/api/v1"
    active_regulator: str = "SEBI"

    # Set at startup by the tenant loader (data/tenants/<TENANT>.json). When no
    # TENANT env var is set these stay at the single-tenant defaults.
    tenant_id: str = "default"
    tenant_name: str = "default"
    regops_multi_agent: bool = True
    embedding_model: str = "text-embedding-3-small"
    vector_memory_enabled: bool = True

    web_search_provider: str = "duckduckgo"
    web_search_api_key: str = ""

    # Person-level assignment
    assignment_enabled: bool = True
    assignment_roster_path: str = "data/roster.json"
    # Weight the candidate scoring formula: skill x (1-load) x seniority
    assignment_skill_weight: float = 0.5
    assignment_load_weight: float = 0.35
    assignment_seniority_weight: float = 0.15
    # Live open-ticket counts via DevRev works.list (off => DB-only load estimate)
    assignment_use_live_load: bool = True
    # Notify the assignee's manager on CRITICAL tickets
    assignment_notify_manager_on_critical: bool = True

    # Applicability scoring — filter SEBI items irrelevant to the org
    applicability_enabled: bool = True
    applicability_profile_path: str = "data/org_profile.json"
    # Below this score, no ticket is created (item logged as not-applicable)
    applicability_ticket_min_score: float = 0.35

    # Richer ticket model
    # Namespaced tag taxonomy (reg:, domain:, type:, pri:, ...) — safe, on by default
    devrev_namespaced_tags: bool = True
    # Custom fields require tenant schema (works.create custom_fields). Off by default.
    devrev_send_custom_fields: bool = False
    # DevRev due date field name on the work item, e.g. "target_close_date".
    # Off by default; requires the field to exist in the tenant.
    devrev_send_due_dates: bool = False
    devrev_due_date_field: str = "target_close_date"
    # Lead-time (days before the regulatory deadline) the work should close by.
    devrev_sla_lead_days_critical: int = 2
    devrev_sla_lead_days_high: int = 5
    devrev_sla_lead_days_default: int = 10
    # Link related prior tickets with real DevRev links (not just a comment).
    devrev_link_related_tickets: bool = True

    # Grounded AI extraction
    grounded_extraction_enabled: bool = True
    # Run a second verify/critique pass for HIGH/CRITICAL items to catch
    # hallucinations and adjust confidence before a ticket is created.
    ai_verify_high_critical: bool = True
    # Model for the verify pass (defaults to the main model when blank).
    openai_verify_model: str = ""
    # Citations: fraction of important_dates whose source_basis must appear in
    # the source text, else the item is flagged for human review.
    citation_min_supported_ratio: float = 0.5

    @property
    def regops_enabled(self) -> bool:
        return self.regops_multi_agent

    # ----- LLM provider resolution -----------------------------------------

    @property
    def is_groq(self) -> bool:
        return self.llm_provider.strip().lower() == "groq"

    @property
    def active_llm_key(self) -> str:
        return self.groq_api_key if self.is_groq else self.openai_api_key

    @property
    def active_llm_base_url(self):
        # None => the OpenAI SDK uses its default api.openai.com base.
        return self.groq_base_url if self.is_groq else None

    @property
    def active_llm_model(self) -> str:
        return self.groq_model if self.is_groq else self.openai_model

    @property
    def supports_json_schema(self) -> bool:
        """Groq doesn't support OpenAI strict json_schema; use json_object there."""
        return not self.is_groq


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    # Apply per-bank tenant overrides once (no-op when TENANT env var is unset).
    from app.core.tenant import apply_tenant_overrides

    apply_tenant_overrides(settings)
    return settings
