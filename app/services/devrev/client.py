"""DevRev REST API client with retries and structured logging."""

from __future__ import annotations

from typing import Any

import httpx
import structlog
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.core.config import get_settings

logger = structlog.get_logger(__name__)


class DevRevAPIError(Exception):
    """Raised when DevRev returns a non-success response."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        response_body: Any = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body


class DevRevClient:
    """Low-level HTTP client for api.devrev.ai."""

    def __init__(
        self,
        *,
        api_token: str | None = None,
        base_url: str | None = None,
        timeout: float | None = None,
    ) -> None:
        settings = get_settings()
        self._api_token = api_token or settings.devrev_api_token
        self._base_url = (base_url or settings.devrev_base_url).rstrip("/")
        self._timeout = timeout or float(settings.devrev_timeout_seconds)

    @property
    def headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    @retry(
        retry=retry_if_exception_type((httpx.TransportError, DevRevAPIError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True,
    )
    def request(
        self,
        method: str,
        endpoint: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Execute a DevRev API call. Endpoints use dot notation, e.g. works.create."""
        url = f"{self._base_url}/{endpoint.lstrip('/')}"
        log = logger.bind(method=method, endpoint=endpoint)

        with httpx.Client(timeout=self._timeout) as client:
            response = client.request(
                method,
                url,
                headers=self.headers,
                params=params,
                json=json_body,
            )

        log = log.bind(status_code=response.status_code)

        if response.status_code == 429:
            log.warning("devrev_rate_limited")
            raise DevRevAPIError(
                "DevRev rate limit exceeded",
                status_code=429,
                response_body=self._safe_json(response),
            )

        if response.status_code >= 400:
            body = self._safe_json(response)
            log.error("devrev_api_error", response_body=body)
            raise DevRevAPIError(
                f"DevRev API error: {response.status_code}",
                status_code=response.status_code,
                response_body=body,
            )

        if json_body and endpoint in ("works.create", "works.update"):
            preview = json_body.get("body")
            if preview:
                log.info(
                    "devrev_payload",
                    operation=endpoint,
                    body_preview=str(preview)[:500],
                )

        if not response.content:
            log.info("devrev_api_success", empty_body=True)
            return {}

        data = response.json()
        log.info("devrev_api_success")
        return data

    def get(self, endpoint: str, *, params: dict[str, Any] | None = None) -> dict[str, Any]:
        return self.request("GET", endpoint, params=params)

    def post(self, endpoint: str, *, json_body: dict[str, Any]) -> dict[str, Any]:
        return self.request("POST", endpoint, json_body=json_body)

    @staticmethod
    def _safe_json(response: httpx.Response) -> Any:
        try:
            return response.json()
        except Exception:
            return {"raw": response.text[:2000]}

    def verify_connectivity(self) -> dict[str, Any]:
        """Validate token by fetching current dev user."""
        return self.get("dev-users.self")

    def list_parts(self, *, limit: int = 50) -> dict[str, Any]:
        return self.get("parts.list", params={"limit": limit})
