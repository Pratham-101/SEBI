"""SEBI regulator plugin — wraps existing scraper."""

from __future__ import annotations

from app.domain.regulators.base import RegulatorPlugin, RegulatorProfile
from app.schemas.notification import ScrapedNotification
from app.services.scraper.sebi_scraper import SEBIScraper


class SEBIRegulatorPlugin(RegulatorPlugin):
    def __init__(self) -> None:
        self._scraper = SEBIScraper()

    @property
    def profile(self) -> RegulatorProfile:
        return RegulatorProfile(
            code="SEBI",
            name="Securities and Exchange Board of India",
            jurisdiction="IN",
            listing_url=self._scraper.listing_url,
            default_part_hint="OTHERS",
        )

    def scrape_latest(self, *, limit: int) -> list[ScrapedNotification]:
        items = self._scraper.scrape_latest(limit=limit)
        for item in items:
            item.regulator_code = "SEBI"
        return items

    def enrich_content(self, item: ScrapedNotification) -> ScrapedNotification:
        return self._scraper.enrich_content(item)
