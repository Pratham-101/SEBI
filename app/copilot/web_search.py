"""Lightweight web search for RegOps Copilot general queries."""

from __future__ import annotations

import re
from html import unescape
from urllib.parse import parse_qs, unquote, urlparse

import httpx
import structlog

from app.core.config import get_settings

logger = structlog.get_logger(__name__)

_RESULT_RE = re.compile(
    r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
    re.IGNORECASE | re.DOTALL,
)
_TAG_RE = re.compile(r"<[^>]+>")


def search_web(query: str, *, max_results: int = 5) -> list[dict[str, str]]:
    """Search the web using configured provider (DuckDuckGo default, SerpAPI optional)."""
    settings = get_settings()
    provider = (settings.web_search_provider or "duckduckgo").strip().lower()

    if provider == "serpapi" and settings.web_search_api_key:
        return _search_serpapi(query, api_key=settings.web_search_api_key, max_results=max_results)

    return _search_duckduckgo(query, max_results=max_results)


def _search_duckduckgo(query: str, *, max_results: int) -> list[dict[str, str]]:
    results: list[dict[str, str]] = []
    try:
        with httpx.Client(timeout=20.0, follow_redirects=True) as client:
            response = client.post(
                "https://html.duckduckgo.com/html/",
                data={"q": query, "b": "", "kl": ""},
                headers={"User-Agent": "RegOpsCopilot/1.0"},
            )
            response.raise_for_status()
            html = response.text
    except Exception as exc:
        logger.warning("copilot_web_search_failed", provider="duckduckgo", error=str(exc))
        return results

    for match in _RESULT_RE.finditer(html):
        href = unescape(match.group(1))
        title = _TAG_RE.sub("", unescape(match.group(2))).strip()
        url = _normalize_ddg_url(href)
        if not url or not title:
            continue
        results.append({"title": title[:240], "url": url})
        if len(results) >= max_results:
            break

    return results


def _normalize_ddg_url(href: str) -> str:
    if href.startswith("//"):
        href = f"https:{href}"
    parsed = urlparse(href)
    if "duckduckgo.com" in parsed.netloc and parsed.path == "/l/":
        target = parse_qs(parsed.query).get("uddg", [""])[0]
        return unquote(target)
    return href


def _search_serpapi(query: str, *, api_key: str, max_results: int) -> list[dict[str, str]]:
    results: list[dict[str, str]] = []
    try:
        with httpx.Client(timeout=20.0) as client:
            response = client.get(
                "https://serpapi.com/search",
                params={"q": query, "api_key": api_key, "engine": "google", "num": max_results},
            )
            response.raise_for_status()
            payload = response.json()
    except Exception as exc:
        logger.warning("copilot_web_search_failed", provider="serpapi", error=str(exc))
        return results

    for item in payload.get("organic_results", [])[:max_results]:
        title = (item.get("title") or "").strip()
        url = (item.get("link") or "").strip()
        if title and url:
            results.append({"title": title[:240], "url": url})
    return results
