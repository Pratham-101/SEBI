# RegOps OS — AI-Native Regulatory Operations Platform

Enterprise-grade **Regulatory Operations Operating System** that ingests multi-regulator feeds (SEBI live; RBI/NSE/BSE/MCA/IRDAI/SEC/FDA via plugin stubs), runs a **nine-agent intelligence pipeline**, maintains **organizational memory** and a **regulatory knowledge graph**, extracts **machine-readable obligations**, and uses **DevRev as the operational command center** (not just a ticket sink).

**DevRev workspace:** [SEBI / HDFC updates](https://app.devrev.ai/hdfc-02/updates)  
**API base (never use app.devrev.ai for APIs):** `https://api.devrev.ai`

---

## Architecture

```mermaid
flowchart TB
    subgraph agents [Nine-Agent RegOps Pipeline]
        A1[Ingestion]
        A2[Classification]
        A3[Organizational Memory]
        A4[Risk Analysis]
        A5[Historical Correlation]
        A6[Obligation Extraction]
        A7[Workflow Orchestration]
        A8[Knowledge Graph]
        A9[Executive Escalation / War Room]
    end
    subgraph stores [Intelligence Stores]
        MEM[(Organizational Memory)]
        KG[(Knowledge Graph)]
        OBL[(Obligations + SLA)]
    end
    DV[DevRev Command Center]
    SCH[APScheduler] --> A1
    A1 --> A2 --> A3 --> A4 --> A5 --> A6 --> A7 --> A8 --> A9
    A3 --> MEM
    A6 --> OBL
    A8 --> KG
    A7 --> DV
    A9 --> DV
```

### Multi-agent pipeline

1. **Regulatory Ingestion** — regulator plugin scrape + dedup + enrich
2. **Classification** — OpenAI structured analysis + governance
3. **Organizational Memory** — retrieve similar past circulars/actions
4. **Risk Analysis** — routing, escalation, risk scoring
5. **Historical Correlation** — link to prior notifications
6. **Obligation Extraction** — machine-readable obligations + SLA rows
7. **Workflow Orchestration** — DevRev tickets, subtasks, command-center overlays
8. **Knowledge Graph** — regulation/team/obligation entities and edges
9. **Executive Escalation** — war room for HIGH/CRITICAL items

### Advanced cycle: alert → applicable? → analysed → owned ticket

Four upgrades deepen the end-to-end loop from "scrape and file a ticket" to
"file an accurate, owned, dated ticket only when it concerns us":

1. **Applicability gate** (`services/routing/applicability.py`, runs before the
   AI call) — scores each SEBI item against an org profile
   (`data/org_profile.json`: intermediary types, business lines, products).
   Items below `APPLICABILITY_TICKET_MIN_SCORE` are logged `not_applicable` and
   never reach the LLM, cutting noise and spend. No-signal items err toward
   processing (a missed obligation costs more than an extra ticket).

2. **Grounded extraction** (`services/ai/analyzer.py`) — every extracted date
   must carry a **verbatim source quote** in `source_basis`. HIGH/CRITICAL items
   get a **second adversarial verify pass** that can only *lower* confidence or
   *downgrade* priority and strips dates whose citation isn't in the source. The
   governance validator (`governance/validator.py`) flags weakly-cited items for
   human review.

3. **Person-level assignment** (`services/routing/assignment.py`) — after the
   team is routed, an `AssignmentEngine` picks the best *individual* from
   `data/roster.json` by `skill × availability × seniority`, using live open-
   ticket counts from DevRev `works.list`. Sets `owned_by` on the parent ticket
   and on each child action item, and notifies the manager on CRITICAL. Seed the
   roster with `scripts/list_devrev_users.py` then `scripts/sync_roster.py`.

4. **Richer tickets** (`services/devrev/mapping.py`, `date_resolver.py`) —
   namespaced tags (`reg:sebi`, `domain:mutual-funds`, `pri:p1`, `team:…`,
   `deadline:…`), an internal **SLA due date** computed as
   `regulatory deadline − priority lead time`, optional custom fields, and child
   tickets with a real owner, due date, and a "Definition of done" checklist.

Custom fields (`DEVREV_SEND_CUSTOM_FIELDS`) and due dates
(`DEVREV_SEND_DUE_DATES`) require matching schema in your DevRev tenant, so they
are **off by default**; everything else works out of the box.

### RegOps API (`/api/v1/regops`)

| Endpoint | Purpose |
|----------|---------|
| `POST /copilot` | Natural-language queries (“What did we do last time?”) |
| `GET /briefings/{daily\|weekly}` | Executive intelligence summaries |
| `GET /obligations` | Open obligations |
| `GET /graph/{notification_id}` | Knowledge subgraph |
| `GET /regulators` | Active regulator plugins |

---

## Folder structure

```
sebi-regulatory-intelligence-agent/
├── app/
│   ├── main.py                 # FastAPI + scheduler lifespan
│   ├── core/                   # config, logging, database
│   ├── api/routes/             # REST endpoints
│   ├── models/                 # SQLAlchemy ORM
│   ├── schemas/                # Pydantic DTOs
│   ├── governance/             # sanitizer, validator, audit
│   ├── services/
│   │   ├── devrev/             # client, tickets, mapping, validators
│   │   ├── scraper/            # SEBI scraper + PDF extract
│   │   ├── ai/                 # OpenAI analyzer
│   │   ├── dedup/              # hash-based dedup
│   │   ├── pipeline/           # orchestrator
│   │   └── notifications/      # Slack alerts
│   ├── workers/                # Celery tasks
│   └── scheduler/              # APScheduler cron
├── scripts/
│   └── verify_devrev.py        # **Run this first**
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
└── .env.example
```

---

## Prerequisites

- Python 3.11+
- Docker & Docker Compose (recommended)
- DevRev Personal Access Token (PAT) with work create permissions
- OpenAI API key
- A DevRev **Part** (product/capability) ID for `applies_to_part`

---

## Step 1 — DevRev verification (required first)

```bash
cd sebi-regulatory-intelligence-agent
cp .env.example .env
# Edit .env:
#   DEVREV_API_TOKEN=<your PAT>
#   DEVREV_BASE_URL=https://api.devrev.ai

python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium

python scripts/verify_devrev.py
```

The script will:

1. Call `GET https://api.devrev.ai/dev-users.self` with `Authorization: Bearer <token>`
2. List parts if `DEVREV_DEFAULT_PART_ID` is missing
3. Create a test ticket via `POST https://api.devrev.ai/works.create`

Copy the suggested `DEVREV_DEFAULT_PART_ID` into `.env` and re-run until ticket creation succeeds.

### DevRev PAT setup

1. Open DevRev → Settings → API / Personal Access Tokens
2. Create a token scoped for work items (create/update/list)
3. Never commit `.env` — only `.env.example` is tracked

---

## Environment variables

| Variable | Required | Description |
|----------|----------|-------------|
| `OPENAI_API_KEY` | Yes | OpenAI API key |
| `OPENAI_MODEL` | No | Default `gpt-4.1` |
| `DEVREV_API_TOKEN` | Yes | Bearer PAT |
| `DEVREV_BASE_URL` | No | Default `https://api.devrev.ai` |
| `DEVREV_DEFAULT_PART_ID` | Yes | Part DON id for tickets |
| `DEVREV_DEFAULT_OWNER_ID` | No | Optional owner dev-user id |
| `DATABASE_URL` | Yes | PostgreSQL SQLAlchemy URL |
| `REDIS_URL` | Yes | Redis URL |
| `CELERY_BROKER_URL` | Yes | Celery broker |
| `CELERY_RESULT_BACKEND` | Yes | Celery results |
| `CRON_INTERVAL_MINUTES` | No | Default `5` |
| `SEBI_LISTING_URL` | No | SEBI listing page URL |
| `AI_CONFIDENCE_THRESHOLD` | No | Auto-approve threshold (0.75) |
| `HUMAN_REVIEW_CONFIDENCE_THRESHOLD` | No | Human review (0.55) |
| `SLACK_WEBHOOK_URL` | No | Escalation alerts |

---

## Local development

```bash
# Terminal 1 — infrastructure
docker compose up -d postgres redis

# Update .env for local ports:
# DATABASE_URL=postgresql+psycopg2://sebi:sebi@localhost:5434/sebi_regulatory
# REDIS_URL=redis://localhost:6381/0

# Terminal 2 — API
uvicorn app.main:app --reload --port 8020

# Terminal 3 — Celery
celery -A app.workers.celery_app worker --loglevel=info
```

---

## Docker (full stack)

```bash
cp .env.example .env
# Fill secrets + DEVREV_DEFAULT_PART_ID

docker compose up --build
```

Services:

| Service | Port | Role |
|---------|------|------|
| `app` | 8020 | FastAPI + APScheduler |
| `postgres` | 5434 | Persistence |
| `redis` | 6381 | Broker |
| `celery_worker` | — | Async pipeline |

---

## Cron / scheduling

`APScheduler` runs inside the FastAPI process every `CRON_INTERVAL_MINUTES` (default 5). Each tick enqueues `sebi.run_pipeline` on Celery so scraping/AI do not block the API.

Manual trigger:

```bash
curl -X POST "http://localhost:8020/trigger/manual-run"
# Sync (dev only):
curl -X POST "http://localhost:8020/trigger/manual-run?sync=true"
```

---

## Governance

| Control | Implementation |
|---------|----------------|
| Hallucination prevention | Prompt rules + deadline must appear in source |
| Confidence validation | `< 0.55` → human review; `< 0.75` → no auto-ticket |
| Prompt injection | `governance/sanitizer.py` strips scripts/injection phrases |
| JSON schema | OpenAI `json_schema` + Pydantic `RegulatoryAnalysisOutput` |
| Risk escalation | CRITICAL/HIGH + immediate flag → Slack (if configured) |
| Audit | `audit_logs` table for every pipeline run and ticket |
| Retries | Tenacity on DevRev HTTP; Celery task retries |

---

## AI structured output

```json
{
  "ticket_title": "SEBI revises mutual fund disclosure norms",
  "executive_summary": "...",
  "notification_type": "circular",
  "priority": "HIGH",
  "compliance_risk": "...",
  "operational_risk": "...",
  "affected_teams": ["Compliance", "Finance"],
  "action_items": ["Update disclosure templates by ..."],
  "deadlines": ["Not specified in source"],
  "tags": ["mutual-funds", "disclosure"],
  "key_regulatory_changes": ["..."],
  "requires_immediate_attention": false,
  "confidence_score": 0.82
}
```

### Priority rules

- **CRITICAL** — enforcement, penalties, legal deadlines, immediate compliance
- **HIGH** — policy/operational impact
- **MEDIUM** — informational with some impact
- **LOW** — low operational significance

DevRev mapping: `CRITICAL→p0`, `HIGH→p1`, `MEDIUM→p2`, `LOW→p3`

---

## API documentation

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Liveness |
| GET | `/notifications` | List tracked notifications |
| GET | `/tickets` | List DevRev ticket records |
| GET | `/audit-logs` | Governance audit trail |
| POST | `/trigger/manual-run` | Enqueue pipeline |

Interactive docs: `http://localhost:8020/docs`

---

## DevRev ticket format

**Title:** `[PRIORITY] Regulatory Update Title`  
**Body:** Markdown sections — Executive Summary, Metadata, Changes, Teams, Actions, Deadlines, Risks, Source URL  
**Dedup:** `external_ref=sebi:<url_hash>` — skips if work already exists

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| `401` on DevRev | Regenerate PAT; confirm `Bearer` header |
| `applies_to_part required` | Set `DEVREV_DEFAULT_PART_ID` from `verify_devrev.py` |
| Playwright timeout | SEBI may be slow; retry; check network |
| OpenAI schema errors | Ensure model supports `json_schema` (gpt-4.1+) |
| Duplicate tickets | Check `external_ref` in DevRev; DB `url_hash` unique |
| Celery not processing | Worker running? Redis reachable? |

---

## Future roadmap

- [ ] Semantic similarity search (pgvector / Redis vector)
- [ ] Historical intelligence search API
- [ ] Multi-regulator plugin interface (RBI, IRDAI)
- [ ] Trend analysis dashboard
- [ ] Email alerts (SMTP)
- [ ] Prometheus `/metrics` exporter
- [ ] Alembic migrations (currently `create_all` on startup)

---

## DevRev Copilot (/ask via webhook)

DevRev's native "Ask me anything" surface does not expose a public API to register custom knowledge sources without building a [DevRev Snap-in](https://developer.devrev.ai/snapin-development/references/event-sources). The supported workaround in this repo is a **timeline comment slash command** wired through a DevRev webhook.

### How it works

1. User posts a comment on any DevRev ticket: `/ask what is TKT-84 about`
2. DevRev sends a `timeline_entry_created` webhook to `POST /api/v1/devrev/webhook`
3. RegOps Copilot (`app/copilot/service.py`) resolves the question (ticket lookup, SEBI search, or web fallback)
4. The bot replies as a timeline comment with ticket links and SEBI source URLs

### Setup

1. Expose your API (e.g. ngrok): `https://your-host/api/v1/devrev/webhook`
2. In DevRev: **Settings > Webhooks** > create webhook for `timeline_entry_created`
3. Set `DEVREV_WEBHOOK_SECRET` in `.env` and configure the same secret in DevRev
4. Set `DEVREV_WORKSPACE_URL` for clickable ticket links in answers

### Manual test (no webhook)

```bash
curl -X POST http://127.0.0.1:8020/api/v1/regops/copilot \
  -H 'Content-Type: application/json' \
  -d '{"question":"what is CSCRF"}'
```

### Group IDs

```bash
python scripts/list_devrev_groups.py
```

Copy the six `DEVREV_GROUP_*` values into `.env`.

---

## Security

- Secrets only in `.env` (gitignored)
- Logs redact tokens (never log `DEVREV_API_TOKEN`)
- HTTP timeouts on all external calls
- Input sanitization before LLM prompts

---

## License

Internal / enterprise use — configure per your organization.
