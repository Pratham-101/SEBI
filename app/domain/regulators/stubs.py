"""Stub regulator plugins for multi-regulator expansion."""

from __future__ import annotations

from app.domain.regulators.base import RegulatorPlugin, RegulatorProfile
from app.schemas.notification import ScrapedNotification


def _stub(code: str, name: str, url: str) -> RegulatorPlugin:
  class _Plugin(RegulatorPlugin):
    @property
    def profile(self) -> RegulatorProfile:
      return RegulatorProfile(code=code, name=name, jurisdiction="IN", listing_url=url)

    def scrape_latest(self, *, limit: int) -> list[ScrapedNotification]:
      return []

    def enrich_content(self, item: ScrapedNotification) -> ScrapedNotification:
      return item

  return _Plugin()


NSEPlugin = _stub("NSE", "National Stock Exchange of India", "https://www.nseindia.com/")
BSEPlugin = _stub("BSE", "Bombay Stock Exchange", "https://www.bseindia.com/")
MCAPlugin = _stub("MCA", "Ministry of Corporate Affairs", "https://www.mca.gov.in/")
IRDAIPlugin = _stub("IRDAI", "Insurance Regulatory Authority", "https://irdai.gov.in/")
SECPlugin = _stub("SEC", "U.S. Securities and Exchange Commission", "https://www.sec.gov/")
FDAPlugin = _stub("FDA", "U.S. Food and Drug Administration", "https://www.fda.gov/")
