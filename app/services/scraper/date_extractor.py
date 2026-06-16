"""Extract publication dates from SEBI listings and detail pages."""

from __future__ import annotations

import re

MONTH_MAP = {
    "jan": "January",
    "feb": "February",
    "mar": "March",
    "apr": "April",
    "may": "May",
    "jun": "June",
    "jul": "July",
    "aug": "August",
    "sep": "September",
    "oct": "October",
    "nov": "November",
    "dec": "December",
}

DATE_PATTERNS = [
    re.compile(
        r"\b(\d{1,2})[-\s](Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*[-\s,]*(\d{4})\b",
        re.I,
    ),
    re.compile(r"\b(\d{1,2})\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})\b", re.I),
    re.compile(r"\bdated\s+(\d{1,2})[-\s](\w+)[-\s,]*(\d{4})\b", re.I),
]


def extract_date_from_url(url: str) -> str | None:
    """Parse month-year from SEBI URL paths like /may-2026/."""
    m = re.search(
        r"/(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*-(\d{4})/",
        url,
        re.I,
    )
    if m:
        month = MONTH_MAP.get(m.group(1).lower()[:3], m.group(1).title())
        return f"{month} {m.group(2)}"
    return None


def extract_date_from_text(text: str) -> str | None:
    """Find the first plausible publication date in page text."""
    for pattern in DATE_PATTERNS:
        match = pattern.search(text[:5000])
        if match:
            groups = match.groups()
            if len(groups) == 3:
                return f"{groups[0]} {groups[1]} {groups[2]}"
    return None


def normalize_notification_date(
    *,
    listing_date: str | None,
    url: str,
    body_text: str = "",
) -> str:
    """Best-effort notification date for ticket display."""
    if listing_date and listing_date.strip() and listing_date.lower() != "unknown":
        return listing_date.strip()

    from_page = extract_date_from_text(body_text)
    if from_page:
        return from_page

    from_url = extract_date_from_url(url)
    if from_url:
        return from_url

    return "Date not available on source — verify on SEBI website"
