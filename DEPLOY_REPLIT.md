# Deploying on Replit (pilot)

This service must run **always-on** (an in-process scheduler scrapes SEBI every
few minutes). On Replit that means a **Reserved VM Deployment**, *not* Autoscale
— Autoscale sleeps when idle and your cron stops. Your $20 Core plan includes
Reserved VM credits.

> One Replit deployment = one bank (one tenant). Run several banks as separate
> deployments, each with its own secrets + database. See "Multi-tenant" below.

---

## 1. Get the code onto Replit

Either:
- **Import from GitHub** (Replit → Create → Import from GitHub), or
- Create a blank Python Repl and upload the project folder.

Replit auto-detects Python. Pin the version: create/confirm `.replit` and
`replit.nix` as below.

---

## 2. External Postgres (required — do NOT use SQLite on Replit)

Replit storage is ephemeral; SQLite **will lose data** on every redeploy. Use a
free managed Postgres:

1. Create a free database at [neon.tech](https://neon.tech) (or Supabase).
2. Copy the connection string. **Replit reserves `DATABASE_URL`** and blocks you
   from setting it, so use **`APP_DATABASE_URL`** instead — the app prefers it.
   You can paste Neon's URL exactly as given (`postgresql://...`); it is
   auto-rewritten to the `postgresql+psycopg2://...` driver form internally.
   ```
   APP_DATABASE_URL=postgresql://USER:PASSWORD@HOST/DBNAME?sslmode=require
   ```
3. Each bank/tenant gets its **own** Neon database → full data isolation.

Tables are auto-created on startup (`init_db` runs `create_all` + the light
column migration), so no manual migration step is needed for the pilot.

---

## 3. Secrets (Replit → Tools → Secrets)

Add these as Secrets (NOT in code). Minimum for a Groq + DevRev pilot:

| Secret | Value |
|--------|-------|
| `LLM_PROVIDER` | `groq` |
| `GROQ_API_KEY` | your `gsk_...` key |
| `GROQ_MODEL` | `llama-3.1-8b-instant` |
| `DEVREV_API_TOKEN` | the bank's DevRev PAT |
| `DEVREV_DEFAULT_PART_ID` | the bank's part DON |
| `DEVREV_GROUP_*` | the 6 group DONs (run `scripts/list_devrev_groups.py`) |
| `APP_DATABASE_URL` | the Neon URL from step 2 (NOT `DATABASE_URL` — Replit reserves it) |
| `USE_SYNC_PIPELINE` | `true` (no Celery/Redis on Replit) |
| `AI_VERIFY_HIGH_CRITICAL` | `false` (free tier can't afford the 2nd call) |
| `GROQ_MAX_BODY_CHARS` | `5000` |
| `SLACK_WEBHOOK_URL` | (recommended) for scrape-failure alerts |
| `TENANT` | (multi-tenant only) the tenant id, e.g. `hdfc` |

`REDIS_URL` / `CELERY_*` are unused when `USE_SYNC_PIPELINE=true`.

---

## 4. Playwright / Chromium

The scraper uses headless Chromium. Add system libs via `replit.nix` (below) and
install the browser once in the deployment build/run:

```
pip install -r requirements.txt
python -m playwright install chromium
```

Chromium is heavy on a small Reserved VM — keep `SCRAPE_MAX_ATTEMPTS=3` and
`CRON_INTERVAL_MINUTES` at 5+ so a slow scrape doesn't overlap the next tick.

---

## 5. Run command

```
python -m playwright install chromium && uvicorn app.main:app --host 0.0.0.0 --port 8080
```

Replit routes external traffic to the port your app binds. Bind `0.0.0.0` and the
port from `$PORT` if Replit sets it (8080 is the common default).

---

## 6. Verify after deploy

1. Open `/health` → should return status + scheduler config.
2. `POST /trigger/manual-run?sync=true` → forces one pipeline run now.
3. Check `/audit-logs` and your DevRev workspace for the created ticket.
4. Confirm the scheduler is alive: the log shows `scheduler_started` on boot and
   a pipeline run every `CRON_INTERVAL_MINUTES`.

---

## 7. Multi-tenant (several banks)

Each bank = its own Reserved VM deployment:
1. Create `data/tenants/<bank>.json` (copy `data/tenants/example.json`), fill the
   bank's DevRev creds/groups + paths to its org profile and roster.
2. Set the deployment's `TENANT=<bank>` secret and a bank-specific `DATABASE_URL`.
3. Deploy. Tickets are tagged `tenant:<bank>` for traceability.

Because each tenant has a separate process **and** database, there is no
cross-bank data leakage.

---

## Notes / limits for the pilot

- **Keep it warm:** Reserved VM stays on; if you ever use Autoscale instead, the
  scheduler will not run between requests — don't.
- **Scrape alerts:** set `SLACK_WEBHOOK_URL` so the dead-man's-switch can warn you
  if SEBI changes layout or blocks the scraper (0 rows → alert).
- **Free Groq quota** resets daily on the same key; a busy day may hit the
  per-minute limit and back off automatically.
