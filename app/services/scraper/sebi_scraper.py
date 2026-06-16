"""SEBI listing page scraper using Playwright + BeautifulSoup."""

from __future__ import annotations

import re
import time
from urllib.parse import urljoin

import structlog
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

from app.core.config import get_settings  # noqa: E402 — used in scrape_latest
from app.schemas.notification import ScrapedNotification
from app.services.dedup.engine import hash_content, hash_url
from app.services.scraper.date_extractor import normalize_notification_date
from app.services.scraper.extractor import extract_pdf_text

logger = structlog.get_logger(__name__)

BASE_URL = "https://www.sebi.gov.in"


class SEBIScraper:
    """Scrape latest SEBI notifications from the public listing page."""

    TYPE_KEYWORDS = {
        "circular": "circular",
        "order": "order",
        "notice": "notice",
        "press release": "press_release",
        "article": "article",
        "guideline": "guideline",
    }

    def __init__(self, listing_url: str | None = None) -> None:
        settings = get_settings()
        self.listing_url = listing_url or settings.sebi_listing_url

    def fetch_listing_html(self) -> str:
        """Fetch the listing page with retries and a relaxed wait strategy.

        `networkidle` is fragile on SEBI (long-polling widgets keep the network
        busy and the wait times out). We try `domcontentloaded` first, then fall
        back, and retry the whole thing a few times before giving up.
        """
        settings = get_settings()
        attempts = max(1, settings.scrape_max_attempts)
        timeout = settings.scrape_nav_timeout_ms
        last_error: Exception | None = None

        for attempt in range(1, attempts + 1):
            try:
                with sync_playwright() as p:
                    browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
                    page = browser.new_page()
                    try:
                        page.goto(
                            self.listing_url,
                            wait_until="domcontentloaded",
                            timeout=timeout,
                        )
                        # Best-effort settle; don't fail the scrape if it times out.
                        try:
                            page.wait_for_selector("table tr", timeout=15_000)
                        except Exception:
                            pass
                        html = page.content()
                    finally:
                        browser.close()
                if html and "<table" in html.lower():
                    return html
                last_error = RuntimeError("listing page had no table content")
                logger.warning(
                    "listing_fetch_no_table", attempt=attempt, attempts=attempts
                )
            except Exception as exc:  # noqa: BLE001 — retry on any nav error
                last_error = exc
                logger.warning(
                    "listing_fetch_attempt_failed",
                    attempt=attempt,
                    attempts=attempts,
                    error=str(exc)[:200],
                )
            time.sleep(2 * attempt)

        logger.error("listing_fetch_failed", error=str(last_error)[:300])
        return ""

    def scrape_latest(self, *, limit: int | None = None) -> list[ScrapedNotification]:
        if limit is None:
            limit = get_settings().sebi_scrape_limit
        html = self.fetch_listing_html()
        soup = BeautifulSoup(html, "lxml")
        items: list[ScrapedNotification] = []

        for row in soup.select("table tr"):
            cells = row.find_all("td")
            if len(cells) < 2:
                continue
            link = cells[-1].find("a") or row.find("a")
            if not link or not link.get("href"):
                continue

            href = link["href"]
            url = urljoin(BASE_URL, href)
            title = link.get_text(strip=True) or "Untitled"
            date_text = cells[0].get_text(strip=True) if cells else None
            ntype = self._infer_type(title, url)

            items.append(
                ScrapedNotification(
                    title=title,
                    url=url,
                    published_date=date_text,
                    notification_type=ntype,
                    url_hash=hash_url(url),
                )
            )
            if len(items) >= limit:
                break

        if not items:
            items = self._fallback_parse(soup)

        logger.info("sebi_scrape_complete", count=len(items))
        return items

    def _fetch_page_html(self, url: str) -> str:
        """Fetch a detail page with retries; returns '' on persistent failure."""
        settings = get_settings()
        attempts = max(1, settings.scrape_max_attempts)
        timeout = settings.scrape_nav_timeout_ms
        for attempt in range(1, attempts + 1):
            try:
                with sync_playwright() as p:
                    browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
                    page = browser.new_page()
                    try:
                        page.goto(url, wait_until="domcontentloaded", timeout=timeout)
                        return page.content()
                    finally:
                        browser.close()
            except Exception as exc:  # noqa: BLE001 — retry slow/blocked detail pages
                logger.warning(
                    "detail_fetch_attempt_failed",
                    url=url,
                    attempt=attempt,
                    attempts=attempts,
                    error=str(exc)[:160],
                )
                time.sleep(2 * attempt)
        return ""

    def enrich_content(self, item: ScrapedNotification) -> ScrapedNotification:
        """Fetch detail page body and PDF text."""
        detail_html = self._fetch_page_html(item.url)
        if not detail_html:
            logger.warning("detail_fetch_failed", url=item.url)
            return item

        soup = BeautifulSoup(detail_html, "lxml")
        body_text = self._extract_clean_body(soup)

        pdf_urls: list[str] = []
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if href.lower().endswith(".pdf") or ".pdf" in href.lower():
                pdf_urls.append(urljoin(BASE_URL, href))

        item.pdf_urls = pdf_urls[:5]
        pdf_texts = [extract_pdf_text(u) for u in item.pdf_urls]
        combined = body_text + "\n\n" + "\n\n".join(t for t in pdf_texts if t)
        item.body_text = combined[:120_000]
        item.content_hash = hash_content(item.body_text)
        item.published_date = normalize_notification_date(
            listing_date=item.published_date,
            url=item.url,
            body_text=item.body_text,
        )
        return item

    # Chrome/boilerplate that leaks into SEBI page text if not stripped.
    _CHROME_SELECTORS = (
        "script", "style", "noscript", "nav", "header", "footer",
        "#Header", "#Footer", "#header", "#footer", ".header", ".footer",
        ".navbar", ".nav", ".menu", ".breadcrumb", ".sidebar", ".social",
        "#leftMenu", "#LeftColumn", "#RightColumn", ".skip-link",
    )
    _CONTENT_SELECTORS = (
        "#MiddleColumn", "#PrintPage", ".panel-body", ".content-area",
        ".content", "article", "main", "#content",
    )
    # Nav phrases that signal we grabbed chrome instead of the notification.
    _CHROME_MARKERS = (
        "skip to main content", "investor website", "about sebi",
        "securities appellate tribunal", "organisation structure",
    )

    def _extract_clean_body(self, soup) -> str:
        """Return notification text with site chrome/nav/scripts stripped.

        For a compliance tool the body feeds the LLM, so leaking the SEBI menu
        ("Skip to main content / ABOUT SEBI / ...") both wastes tokens and
        degrades analysis. We remove known chrome, prefer a content container,
        and fall back to the largest text block if needed.
        """
        for sel in self._CHROME_SELECTORS:
            for el in soup.select(sel):
                el.decompose()

        candidate = None
        for sel in self._CONTENT_SELECTORS:
            el = soup.select_one(sel)
            if el:
                text = el.get_text("\n", strip=True)
                if len(text) > 120:
                    candidate = text
                    break

        if not candidate:
            # Fall back to the largest <div>/<td> text block (the notification body).
            blocks = []
            for el in soup.find_all(["div", "td", "section"]):
                t = el.get_text("\n", strip=True)
                if t:
                    blocks.append(t)
            candidate = max(blocks, key=len) if blocks else soup.get_text("\n", strip=True)

        # Drop residual nav lines and collapse whitespace.
        lines = []
        for line in candidate.splitlines():
            s = line.strip()
            if not s:
                continue
            low = s.lower()
            if any(m in low for m in self._CHROME_MARKERS):
                continue
            # Single-letter vertical-menu artifacts ("I N V E S T O R").
            if len(s) <= 2 and s.isalpha():
                continue
            lines.append(s)
        cleaned = "\n".join(lines)
        return re.sub(r"\n{3,}", "\n\n", cleaned).strip()

    def _infer_type(self, title: str, url: str) -> str:
        combined = f"{title} {url}".lower()
        for keyword, ntype in self.TYPE_KEYWORDS.items():
            if keyword in combined:
                return ntype
        return "notification"

    def _fallback_parse(self, soup: BeautifulSoup) -> list[ScrapedNotification]:
        items: list[ScrapedNotification] = []
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if "sebiweb" not in href and "legal" not in href:
                continue
            url = urljoin(BASE_URL, href)
            title = a.get_text(strip=True)
            if len(title) < 10:
                continue
            items.append(
                ScrapedNotification(
                    title=title,
                    url=url,
                    notification_type=self._infer_type(title, url),
                    url_hash=hash_url(url),
                )
            )
            if len(items) >= 20:
                break
        return items
