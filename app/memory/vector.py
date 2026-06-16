"""Vector memory — OpenAI embeddings + semantic retrieval."""

from __future__ import annotations

import hashlib
import json
import math

import structlog
from openai import OpenAI
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.memory_embedding import MemoryEmbedding
from app.models.organizational_memory import OrganizationalMemory

logger = structlog.get_logger(__name__)


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


class VectorMemoryService:
    def __init__(self, db: Session) -> None:
        self._db = db
        self._settings = get_settings()
        # Embeddings are OpenAI-only. Groq has no OpenAI-compatible embeddings
        # endpoint, so when the provider isn't OpenAI (or there's no key) we skip
        # vectors entirely and fall back to keyword retrieval.
        use_openai = (
            not self._settings.is_groq and bool(self._settings.openai_api_key)
        )
        self._client = OpenAI(api_key=self._settings.openai_api_key) if use_openai else None
        self._model = getattr(self._settings, "embedding_model", "text-embedding-3-small")

    def embed_text(self, text: str) -> list[float]:
        if not self._client:
            return []
        try:
            resp = self._client.embeddings.create(model=self._model, input=text[:8000])
            return resp.data[0].embedding
        except Exception as exc:  # noqa: BLE001 — degrade to keyword fallback
            logger.warning("embedding_failed_fallback_to_keyword", error=str(exc)[:160])
            return []

    def index_memory(self, memory: OrganizationalMemory) -> None:
        text = f"{memory.theme}\n{memory.summary}"
        content_hash = hashlib.sha256(text.encode()).hexdigest()
        existing = (
            self._db.query(MemoryEmbedding)
            .filter(MemoryEmbedding.content_hash == content_hash)
            .first()
        )
        if existing:
            return
        vec = self.embed_text(text)
        if not vec:
            return
        row = MemoryEmbedding(
            memory_id=memory.id,
            notification_id=memory.notification_id,
            regulator_code=memory.regulator_code,
            content_hash=content_hash,
            embedding_json=json.dumps(vec),
            model=self._model,
        )
        self._db.add(row)
        self._db.commit()

    def semantic_search(
        self,
        query: str,
        *,
        regulator_code: str | None = None,
        limit: int = 8,
    ) -> list[dict]:
        query_vec = self.embed_text(query)
        if not query_vec:
            return self._keyword_fallback(query, regulator_code=regulator_code, limit=limit)

        q = self._db.query(MemoryEmbedding)
        if regulator_code:
            q = q.filter(MemoryEmbedding.regulator_code == regulator_code)
        rows = q.order_by(MemoryEmbedding.id.desc()).limit(500).all()

        scored: list[tuple[float, MemoryEmbedding]] = []
        for row in rows:
            try:
                vec = json.loads(row.embedding_json)
                score = _cosine(query_vec, vec)
                scored.append((score, row))
            except (json.JSONDecodeError, TypeError):
                continue

        scored.sort(key=lambda x: -x[0])
        results = []
        for score, row in scored[:limit]:
            mem = self._db.get(OrganizationalMemory, row.memory_id) if row.memory_id else None
            results.append(
                {
                    "score": round(score, 4),
                    "memory_id": row.memory_id,
                    "notification_id": row.notification_id,
                    "theme": mem.theme if mem else "",
                    "summary": mem.summary[:400] if mem else "",
                    "outcome": mem.outcome if mem else None,
                    "historical_note": (
                        f"Semantically similar ({score:.0%}): {mem.theme if mem else 'prior action'}"
                    ),
                }
            )
        return results

    def _keyword_fallback(
        self, query: str, *, regulator_code: str | None, limit: int
    ) -> list[dict]:
        from app.memory.retrieval import MemoryRetrieval

        words = [w for w in query.lower().split() if len(w) > 3][:5]
        return MemoryRetrieval(self._db).find_similar(
            regulator_code=regulator_code or "SEBI",
            themes=words,
            domain="",
            limit=limit,
        )
