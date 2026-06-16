"""Cross-regulator signal fusion."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models.analysis_result import AnalysisResult
from app.models.notification import Notification


class CrossRegulatorCorrelation:
    def __init__(self, db: Session) -> None:
        self._db = db

    def fuse_signals(self, *, days: int = 14) -> dict:
        since = datetime.now(timezone.utc) - timedelta(days=days)
        notifications = (
            self._db.query(Notification)
            .filter(Notification.created_at >= since)
            .all()
        )

        themes_by_regulator: dict[str, list[str]] = defaultdict(list)
        for n in notifications:
            code = getattr(n, "regulator_code", None) or "SEBI"
            ar = (
                self._db.query(AnalysisResult)
                .filter(AnalysisResult.notification_id == n.id)
                .order_by(AnalysisResult.id.desc())
                .first()
            )
            if ar and ar.structured_output:
                import json

                try:
                    data = json.loads(ar.structured_output)
                    for theme in data.get("related_themes", [])[:3]:
                        themes_by_regulator[code].append(theme.lower())
                except json.JSONDecodeError:
                    pass

        overlapping = self._find_overlaps(themes_by_regulator)
        sector_pressure = len(overlapping) / max(len(themes_by_regulator), 1)

        return {
            "period_days": days,
            "regulators_active": list(themes_by_regulator.keys()),
            "overlapping_themes": overlapping,
            "sector_wide_pressure_index": round(min(1.0, sector_pressure), 3),
            "emerging_governance_trends": self._top_trends(themes_by_regulator),
            "signal_fusion_summary": (
                f"{len(overlapping)} cross-regulator theme overlaps detected "
                f"across {len(themes_by_regulator)} regulators."
            ),
        }

    def _find_overlaps(self, themes_by_regulator: dict[str, list[str]]) -> list[dict]:
        all_themes: dict[str, set[str]] = defaultdict(set)
        for reg, themes in themes_by_regulator.items():
            for t in themes:
                all_themes[t].add(reg)

        return [
            {"theme": theme, "regulators": sorted(regs)}
            for theme, regs in all_themes.items()
            if len(regs) >= 2
        ][:15]

    def _top_trends(self, themes_by_regulator: dict[str, list[str]]) -> list[str]:
        counts: dict[str, int] = defaultdict(int)
        for themes in themes_by_regulator.values():
            for t in themes:
                counts[t] += 1
        return [t for t, _ in sorted(counts.items(), key=lambda x: -x[1])[:10]]
