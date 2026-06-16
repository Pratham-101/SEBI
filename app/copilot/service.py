"""RegOps AI Copilot with ticket lookup, SEBI search, and web fallback."""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
from difflib import SequenceMatcher

import structlog
from openai import OpenAI
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.copilot.web_search import search_web
from app.models.analysis_result import AnalysisResult
from app.models.notification import Notification
from app.models.ticket import Ticket
from app.schemas.analysis import RegulatoryAnalysisOutput

logger = structlog.get_logger(__name__)

TICKET_ID_RE = re.compile(r"\bTKT-\d+\b", re.IGNORECASE)
NOTIFICATION_HINTS = re.compile(
    r"\b(sebi|publish|circular|notification|order|ruling|adjudication|"
    r"framework|guideline|recent|this week|last week|today|yesterday)\b",
    re.IGNORECASE,
)
STOP_WORDS = {
    "what", "when", "where", "which", "about", "tell", "give", "does", "did",
    "have", "has", "the", "this", "that", "with", "from", "into", "your", "our",
    "sebi", "publish", "published", "anything", "recent", "recently", "please",
    "summarize", "summary", "ticket", "regarding", "related",
}


class RegOpsCopilot:
    def __init__(self, db: Session) -> None:
        self._db = db
        self._settings = get_settings()
        from app.services.ai.client import build_llm_client

        self._openai = build_llm_client()

    def answer(self, question: str, *, regulator_code: str | None = None) -> dict:
        q = question.strip()
        if not q:
            return self._empty_response("Please enter a question.")

        mode = self._classify_mode(q)
        if mode == "ticket":
            return self._answer_ticket(q, regulator_code=regulator_code)
        if mode == "notification":
            return self._answer_notification(q, regulator_code=regulator_code)
        return self._answer_general(q, regulator_code=regulator_code)

    def _classify_mode(self, question: str) -> str:
        if TICKET_ID_RE.search(question):
            return "ticket"
        lower = question.lower()
        if any(k in lower for k in ("ticket", "tkt-", "work item")) and any(
            k in lower for k in ("about", "summarize", "summary", "what is", "tell me")
        ):
            return "ticket"
        if NOTIFICATION_HINTS.search(question):
            return "notification"
        return "general"

    def _answer_ticket(self, question: str, *, regulator_code: str | None) -> dict:
        ticket_refs: list[dict] = []
        sebi_sources: list[dict] = []
        context_blocks: list[str] = []

        ticket = self._resolve_ticket(question)
        if not ticket:
            return self._empty_response(
                "I could not find a matching DevRev ticket. "
                "Try including the display ID (e.g. TKT-82) or part of the ticket title."
            )

        notification = self._db.get(Notification, ticket.notification_id)
        analysis = self._latest_analysis(ticket.notification_id)

        ticket_url = self._ticket_url(ticket.devrev_display_id or "")
        ticket_refs.append(
            {
                "display_id": ticket.devrev_display_id or "",
                "url": ticket_url,
                "title": notification.title if notification else ticket.external_ref,
            }
        )

        if notification and notification.url:
            sebi_sources.append({"title": notification.title, "url": notification.url})

        context_blocks.append(
            f"Ticket: {ticket.devrev_display_id}\n"
            f"Priority: {ticket.priority}\n"
            f"Assigned team: {ticket.assigned_team or 'unknown'}\n"
            f"Status: {ticket.status}\n"
        )
        if notification:
            context_blocks.append(
                f"Notification title: {notification.title}\n"
                f"Published: {notification.published_date or 'unknown'}\n"
                f"Type: {notification.notification_type}\n"
            )
        if analysis:
            context_blocks.append(
                f"Executive summary: {analysis.executive_summary}\n"
                f"Domain: {analysis.regulatory_domain}\n"
                f"Compliance exposure: {analysis.compliance_exposure}\n"
            )
            if analysis.actionable_insights:
                insights = "\n".join(f"- {i.action} ({i.owner_team})" for i in analysis.actionable_insights[:5])
                context_blocks.append(f"Actionable insights:\n{insights}\n")

        answer = self._synthesize(
            question=question,
            context="\n".join(context_blocks),
            instruction="Answer using the ticket and SEBI notification context. Be concise and operational.",
        )
        return {
            "answer": answer,
            "ticket_references": ticket_refs,
            "sebi_sources": sebi_sources,
            "web_sources": [],
            "used_web_search": False,
        }

    def _answer_notification(self, question: str, *, regulator_code: str | None) -> dict:
        keywords = self._extract_keywords(question)
        since = self._parse_since_date(question)
        query = self._db.query(Notification)
        if regulator_code:
            query = query.filter(Notification.regulator_code == regulator_code.upper())

        if since:
            query = query.filter(Notification.created_at >= since)

        if keywords:
            clauses = []
            for kw in keywords[:6]:
                pattern = f"%{kw}%"
                clauses.append(or_(Notification.title.ilike(pattern), Notification.body_text.ilike(pattern)))
            query = query.filter(or_(*clauses))

        notifications = query.order_by(Notification.created_at.desc()).limit(8).all()
        if not notifications:
            return self._answer_general(question, regulator_code=regulator_code, prefer_web=True)

        ticket_refs: list[dict] = []
        sebi_sources: list[dict] = []
        context_blocks: list[str] = []

        for n in notifications:
            sebi_sources.append({"title": n.title, "url": n.url})
            ticket = (
                self._db.query(Ticket)
                .filter(Ticket.notification_id == n.id)
                .order_by(Ticket.id.desc())
                .first()
            )
            if ticket and ticket.devrev_display_id:
                ticket_refs.append(
                    {
                        "display_id": ticket.devrev_display_id,
                        "url": self._ticket_url(ticket.devrev_display_id),
                        "title": n.title,
                    }
                )
            analysis = self._latest_analysis(n.id)
            summary = analysis.executive_summary if analysis else (n.body_text or "")[:400]
            context_blocks.append(
                f"Title: {n.title}\n"
                f"Published: {n.published_date or 'unknown'}\n"
                f"URL: {n.url}\n"
                f"Summary: {summary}\n"
                f"Ticket: {ticket.devrev_display_id if ticket else 'none yet'}\n"
            )

        answer = self._synthesize(
            question=question,
            context="\n\n---\n\n".join(context_blocks),
            instruction=(
                "Answer using matched SEBI notifications. "
                "Mention whether a DevRev ticket exists for each relevant item."
            ),
        )
        return {
            "answer": answer,
            "ticket_references": ticket_refs,
            "sebi_sources": sebi_sources,
            "web_sources": [],
            "used_web_search": False,
        }

    def _answer_general(
        self,
        question: str,
        *,
        regulator_code: str | None,
        prefer_web: bool = False,
    ) -> dict:
        local_hits = self._search_local(question, regulator_code=regulator_code)
        web_sources: list[dict] = []
        used_web = False

        if local_hits and not prefer_web:
            context = json.dumps(local_hits, indent=2)[:6000]
            answer = self._synthesize(
                question=question,
                context=context,
                instruction="Answer from local RegOps data when sufficient; note gaps clearly.",
            )
            ticket_refs = local_hits.get("ticket_references", [])
            sebi_sources = local_hits.get("sebi_sources", [])
            return {
                "answer": answer,
                "ticket_references": ticket_refs,
                "sebi_sources": sebi_sources,
                "web_sources": [],
                "used_web_search": False,
            }

        web_sources = search_web(question, max_results=5)
        used_web = bool(web_sources)
        citations = "\n".join(f"- {s['title']}: {s['url']}" for s in web_sources)
        answer = self._synthesize(
            question=question,
            context=citations or "No web results returned.",
            instruction=(
                "Answer the regulatory question using the web sources. "
                "Cite sources inline where helpful. If uncertain, say so."
            ),
        )
        return {
            "answer": answer,
            "ticket_references": [],
            "sebi_sources": [],
            "web_sources": web_sources,
            "used_web_search": used_web,
        }

    def _resolve_ticket(self, question: str) -> Ticket | None:
        match = TICKET_ID_RE.search(question)
        if match:
            display_id = match.group(0).upper()
            ticket = (
                self._db.query(Ticket)
                .filter(Ticket.devrev_display_id.ilike(display_id))
                .order_by(Ticket.id.desc())
                .first()
            )
            if ticket:
                return ticket

        return self._fuzzy_ticket_by_title(question)

    def _fuzzy_ticket_by_title(self, question: str) -> Ticket | None:
        keywords = self._extract_keywords(question)
        if not keywords:
            return None

        tickets = (
            self._db.query(Ticket, Notification)
            .join(Notification, Ticket.notification_id == Notification.id)
            .order_by(Ticket.id.desc())
            .limit(200)
            .all()
        )
        best_score = 0.0
        best_ticket: Ticket | None = None
        probe = " ".join(keywords).lower()

        for ticket, notification in tickets:
            title = (notification.title or "").lower()
            score = SequenceMatcher(None, probe, title).ratio()
            for kw in keywords:
                if kw in title:
                    score += 0.15
            if score > best_score:
                best_score = score
                best_ticket = ticket

        return best_ticket if best_score >= 0.35 else None

    def _latest_analysis(self, notification_id: int) -> RegulatoryAnalysisOutput | None:
        row = (
            self._db.query(AnalysisResult)
            .filter(AnalysisResult.notification_id == notification_id)
            .order_by(AnalysisResult.id.desc())
            .first()
        )
        if not row:
            return None
        try:
            return RegulatoryAnalysisOutput.model_validate_json(row.structured_output)
        except Exception:
            return None

    def _search_local(self, question: str, *, regulator_code: str | None) -> dict | None:
        keywords = self._extract_keywords(question)
        if not keywords:
            return None

        query = self._db.query(Notification)
        if regulator_code:
            query = query.filter(Notification.regulator_code == regulator_code.upper())

        clauses = []
        for kw in keywords[:5]:
            pattern = f"%{kw}%"
            clauses.append(or_(Notification.title.ilike(pattern), Notification.body_text.ilike(pattern)))
        notifications = query.filter(or_(*clauses)).order_by(Notification.created_at.desc()).limit(3).all()
        if not notifications:
            return None

        ticket_refs: list[dict] = []
        sebi_sources: list[dict] = []
        snippets: list[str] = []
        for n in notifications:
            sebi_sources.append({"title": n.title, "url": n.url})
            ticket = (
                self._db.query(Ticket)
                .filter(Ticket.notification_id == n.id)
                .order_by(Ticket.id.desc())
                .first()
            )
            if ticket and ticket.devrev_display_id:
                ticket_refs.append(
                    {
                        "display_id": ticket.devrev_display_id,
                        "url": self._ticket_url(ticket.devrev_display_id),
                        "title": n.title,
                    }
                )
            snippets.append(n.title)

        return {
            "snippets": snippets,
            "ticket_references": ticket_refs,
            "sebi_sources": sebi_sources,
        }

    def _extract_keywords(self, question: str) -> list[str]:
        tokens = re.findall(r"[a-zA-Z0-9][a-zA-Z0-9\-]{2,}", question.lower())
        out: list[str] = []
        for t in tokens:
            if t in STOP_WORDS:
                continue
            if t not in out:
                out.append(t)
        return out[:8]

    def _parse_since_date(self, question: str) -> datetime | None:
        lower = question.lower()
        now = datetime.utcnow()
        if "this week" in lower:
            return now - timedelta(days=7)
        if "last week" in lower:
            return now - timedelta(days=14)
        if "today" in lower:
            return now - timedelta(days=1)
        if "yesterday" in lower:
            return now - timedelta(days=2)
        month_match = re.search(
            r"\b(january|february|march|april|may|june|july|august|"
            r"september|october|november|december)\s+(\d{1,2})\b",
            lower,
        )
        if month_match:
            try:
                dt = datetime.strptime(f"{month_match.group(1)} {month_match.group(2)}", "%B %d")
                dt = dt.replace(year=now.year)
                return dt - timedelta(days=1)
            except ValueError:
                return None
        return None

    def _ticket_url(self, display_id: str) -> str:
        base = (self._settings.devrev_workspace_url or "").rstrip("/")
        if base and display_id:
            return f"{base}/works/{display_id}"
        return ""

    def _synthesize(self, *, question: str, context: str, instruction: str) -> str:
        if not self._openai:
            return f"{instruction}\n\nContext:\n{context[:2000]}"

        try:
            response = self._openai.chat.completions.create(
                model=self._settings.active_llm_model,
                temperature=0.2,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are RegOps Copilot for SEBI regulatory operations. "
                            "Answer clearly for compliance and legal teams."
                        ),
                    },
                    {
                        "role": "user",
                        "content": f"{instruction}\n\nQuestion: {question}\n\nContext:\n{context}",
                    },
                ],
            )
            return (response.choices[0].message.content or "").strip()
        except Exception as exc:
            logger.warning("copilot_synthesis_failed", error=str(exc))
            return context[:1500]

    @staticmethod
    def _empty_response(message: str) -> dict:
        return {
            "answer": message,
            "ticket_references": [],
            "sebi_sources": [],
            "web_sources": [],
            "used_web_search": False,
        }
