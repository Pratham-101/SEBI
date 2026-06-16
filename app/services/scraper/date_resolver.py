"""Resolve regulatory dates to absolute ISO dates and compute SLA due dates.

Two jobs:
1. Parse absolute date strings ("1 July 2026", "01-Jul-2026", "2026-07-01").
2. Resolve relative expressions ("within 30 days", "within 3 months of this
   circular") against the notification's publication date.

Used by the richer ticket model (SLA due dates) and grounded extraction (turning
the model's relative deadlines into real dates).
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta

from app.services.scraper.date_extractor import DATE_PATTERNS, MONTH_MAP

_MONTH_NAME_TO_NUM = {name.lower(): i for i, name in enumerate(
    ["", "January", "February", "March", "April", "May", "June", "July",
     "August", "September", "October", "November", "December"]
)}
# short forms too
for _short, _full in MONTH_MAP.items():
    _MONTH_NAME_TO_NUM[_short] = _MONTH_NAME_TO_NUM[_full.lower()]

_ISO_RE = re.compile(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b")
_REL_DAYS_RE = re.compile(r"within\s+(\d{1,3})\s+(day|business day|working day)s?", re.I)
_REL_WEEKS_RE = re.compile(r"within\s+(\d{1,2})\s+weeks?", re.I)
_REL_MONTHS_RE = re.compile(r"within\s+(\d{1,2})\s+months?", re.I)


def parse_absolute(text: str | None) -> date | None:
    """Parse an absolute date out of a string. Returns None if not found."""
    if not text:
        return None
    s = text.strip()

    iso = _ISO_RE.search(s)
    if iso:
        try:
            return date(int(iso.group(1)), int(iso.group(2)), int(iso.group(3)))
        except ValueError:
            pass

    for pattern in DATE_PATTERNS:
        m = pattern.search(s)
        if not m:
            continue
        g = m.groups()
        if len(g) != 3:
            continue
        try:
            day = int(g[0])
            month = _MONTH_NAME_TO_NUM.get(g[1].lower()[:3] if len(g[1]) <= 3 else g[1].lower())
            if not month:
                month = _MONTH_NAME_TO_NUM.get(g[1].lower())
            year = int(g[2])
            if month:
                return date(year, month, day)
        except (ValueError, TypeError):
            continue
    return None


def resolve_relative(text: str, *, base: date) -> date | None:
    """Resolve 'within N days/weeks/months' against a base date."""
    if not text:
        return None
    m = _REL_DAYS_RE.search(text)
    if m:
        return base + timedelta(days=int(m.group(1)))
    m = _REL_WEEKS_RE.search(text)
    if m:
        return base + timedelta(weeks=int(m.group(1)))
    m = _REL_MONTHS_RE.search(text)
    if m:
        return base + timedelta(days=int(m.group(1)) * 30)
    return None


def resolve_date(text: str | None, *, base: date | None = None) -> date | None:
    """Best-effort: try absolute first, then relative against `base`."""
    if not text:
        return None
    absolute = parse_absolute(text)
    if absolute:
        return absolute
    if base:
        return resolve_relative(text, base=base)
    return None


def published_to_date(published_date: str | None) -> date | None:
    """Convert a notification's display date string to a date object."""
    return parse_absolute(published_date)


def compute_sla_due_date(
    *,
    deadline_text: str | None,
    published_date: str | None,
    priority: str,
    lead_days_critical: int,
    lead_days_high: int,
    lead_days_default: int,
) -> str | None:
    """ISO due date = regulatory deadline minus a priority-based lead time.

    Falls back to (publication date + lead time) when no deadline is parseable,
    so even deadline-less items get a sensible internal target.
    """
    base = published_to_date(published_date)
    deadline = resolve_date(deadline_text, base=base)

    lead = {
        "CRITICAL": lead_days_critical,
        "HIGH": lead_days_high,
    }.get((priority or "").upper(), lead_days_default)

    if deadline:
        due = deadline - timedelta(days=lead)
        # Never schedule the internal due date in the past relative to publish.
        if base and due < base:
            due = base
        return due.isoformat()

    if base:
        return (base + timedelta(days=lead)).isoformat()
    return None
