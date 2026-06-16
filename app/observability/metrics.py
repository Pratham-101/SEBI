"""Operational observability and metrics."""

from __future__ import annotations

import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.analysis_result import AnalysisResult
from app.models.processing_log import ProcessingLog
from app.models.ticket import Ticket


class ObservabilityService:
    _pipeline_latencies: list[float] = []
    _ai_latencies: list[float] = []

    def __init__(self, db: Session) -> None:
        self._db = db

    @classmethod
    def record_pipeline_duration(cls, seconds: float) -> None:
        cls._pipeline_latencies.append(seconds)
        cls._pipeline_latencies[:] = cls._pipeline_latencies[-100:]

    @classmethod
    def record_ai_duration(cls, seconds: float) -> None:
        cls._ai_latencies.append(seconds)
        cls._ai_latencies[:] = cls._ai_latencies[-100:]

    def dashboard(self) -> dict:
        since = datetime.now(timezone.utc) - timedelta(hours=24)
        logs = (
            self._db.query(ProcessingLog)
            .filter(ProcessingLog.created_at >= since)
            .all()
        )
        by_stage: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
        for log in logs:
            by_stage[log.stage][log.status] += 1

        tickets_24h = (
            self._db.query(Ticket).filter(Ticket.created_at >= since).count()
        )
        errors_24h = sum(1 for log in logs if log.status == "failed")

        avg_pipeline = (
            sum(self._pipeline_latencies) / len(self._pipeline_latencies)
            if self._pipeline_latencies
            else 0
        )
        avg_ai = (
            sum(self._ai_latencies) / len(self._ai_latencies)
            if self._ai_latencies
            else 0
        )

        return {
            "workflow_analytics": dict(by_stage),
            "tickets_created_24h": tickets_24h,
            "errors_24h": errors_24h,
            "ai_latency_avg_ms": int(avg_ai * 1000),
            "pipeline_latency_avg_ms": int(avg_pipeline * 1000),
            "trace_count_24h": len(logs),
        }
