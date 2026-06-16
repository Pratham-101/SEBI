"""RBI regulator plugin stub — ready for implementation."""

from __future__ import annotations

from app.domain.regulators.base import RegulatorPlugin, RegulatorProfile
from app.schemas.notification import ScrapedNotification


class RBIRegulatorPlugin(RegulatorPlugin):
    """Placeholder until RBI listing scraper is implemented."""

    @property
    def profile(self) -> RegulatorProfile:
        return RegulatorProfile(
            code="RBI",
            name="Reserve Bank of India",
            jurisdiction="IN",
            listing_url="https://www.rbi.org.in/",
        )

    def scrape_latest(self, *, limit: int) -> list[ScrapedNotification]:
        return []

    def enrich_content(self, item: ScrapedNotification) -> ScrapedNotification:
        return item
