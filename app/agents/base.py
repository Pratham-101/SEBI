"""Base agent contract for RegOps OS."""

from __future__ import annotations

from abc import ABC, abstractmethod

from sqlalchemy.orm import Session

from app.agents.context import RegOpsContext


class BaseAgent(ABC):
    name: str = "base"

    def __init__(self, db: Session) -> None:
        self._db = db

    @abstractmethod
    def run(self, ctx: RegOpsContext) -> RegOpsContext:
        ...
