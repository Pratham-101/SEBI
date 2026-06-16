# Onboarding a new bank (tenant)

Each bank = its own deployment (own Reserved VM + own Neon database + own config).
There is no customer yet — this is the checklist for when the first one signs.

## Per-bank config files (the two that are NOT in git)

`data/` is gitignored (so PATs/secrets never get committed) AND Replit storage is
ephemeral. So for every bank deployment you must create these two files in that
bank's Repl, and re-create them if the Repl is rebuilt:

### 1. `data/roster.json` — WHO gets the ticket
Maps the bank's real DevRev people to teams + expertise. Without it, tickets are
assigned to a team only (`assignee: null`) — person-level assignment can't work.
Get the DevRev user DONs with `python scripts/list_devrev_users.py`.

### 2. `data/org_profile.json` — DOES the notification apply to this bank
Describes the bank's SEBI registrations / business lines / products. Drives the
applicability gate that filters out irrelevant SEBI items. Without it, the gate is
off and EVERY scraped item becomes a ticket.

Templates: `data/tenants/example.json` (tenant), and the roster/profile shapes are
in `app/services/routing/assignment.py` and `app/services/routing/applicability.py`.

## Full onboarding steps (per bank)

1. New Replit **Reserved VM** deployment from the repo.
2. New **Neon** database; set `APP_DATABASE_URL` secret (Replit reserves DATABASE_URL).
3. Get the bank's DevRev: PAT, default part DON, the 6 group DONs
   (`scripts/list_devrev_groups.py`), optional default owner.
4. Set secrets: `LLM_PROVIDER=groq`, `GROQ_API_KEY`, `USE_SYNC_PIPELINE=true`,
   `AI_VERIFY_HIGH_CRITICAL=false`, `GROQ_MAX_BODY_CHARS=5000`, DevRev creds,
   `SLACK_WEBHOOK_URL` (for scrape-failure alerts), and `TENANT=<bank>` if using
   the tenant file under `data/tenants/`.
5. Create `data/roster.json` and `data/org_profile.json` for the bank (see above).
6. Run `scripts/sync_roster.py`, then `POST /trigger/manual-run?sync=true` to verify
   a real ticket lands in the bank's DevRev with the right group + a real assignee.

## TODO when first real bank signs
- Make the app auto-seed roster/org_profile from committed `.example` templates on
  startup, so they survive Replit redeploys without manual re-creation.
