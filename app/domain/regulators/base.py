"""Regulator plugin interface for multi-regulator RegOps OS."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from app.schemas.notification import ScrapedNotification


@dataclass
class RegulatorProfile:
    code: str
    name: str
    jurisdiction: str
    listing_url: str
    default_part_hint: str = ""


class RegulatorPlugin(ABC):
    """Plugin contract for regulatory source ingestion."""

    @property
    @abstractmethod
    def profile(self) -> RegulatorProfile:
        ...

    @abstractmethod
    def scrape_latest(self, *, limit: int) -> list[ScrapedNotification]:
        ...

    @abstractmethod
    def enrich_content(self, item: ScrapedNotification) -> ScrapedNotification:
        ...
