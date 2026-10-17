# Colder Mailer — Build Plan

> **For Claude Code:** Read this whole file first. Build **one phase at a time**, in order. After each phase, run that phase's acceptance checks, report results, and **stop and wait** before starting the next phase. Ask before changing any decision in "Stack" or "Data model".

## What it is

A personal web dashboard for internship cold outreach:

1. **Paste box:** paste messy text containing email addresses → it extracts emails, maps each domain to a company, guesses first names, flags problems, and shows an editable preview before saving.
2. **Template:** one email template with `[Company]` and `[Name]` tokens, filled per contact.
3. **Resume:** uploaded once, attached to each email renamed per company (`Eric_Resume_Amazon.pdf`).
4. **Send:** send one email now, or queue many; a scheduled worker sends about 1 every 15 minutes during business hours.
5. **Track:** every contact moves through `new → queued → sending → sent → replied / bounced / failed`, with company and stats views.

Single user (me). It sends from my personal Gmail, so it must be locked behind login.

## Stack

| Layer | Choice | Why |
|---|---|---|
| Frontend | Next.js (App Router, TypeScript), Tailwind, shadcn/ui | Fast to build a clean dashboard |
| Backend | FastAPI (Python 3.12), SQLAlchemy 2, Alembic, Pydantic | Python fits parsing + Gmail work |
| Database | Postgres (Supabase free tier; local Postgres via docker compose for dev) | Relational data, row-level locking for the queue |
| Auth | Supabase Auth (magic link), backend verifies the JWT, allowlist of one email | Single user, minimal setup |
| File storage | Supabase Storage, private bucket (local folder in dev, behind a `storage.py` interface) | Resume never public |
| Email | Gmail API, OAuth web flow, scope `gmail.send` | Returns `threadId` for reply tracking later |
| Sender | `worker.process_queue()` run by AWS Lambda on an EventBridge Scheduler cron | Runs without my laptop |
| Hosting | Frontend on Vercel; API on AWS Lambda (FastAPI + Mangum) via AWS SAM | Free tier, infra as code |
| Secrets | `.env` locally; AWS SSM Parameter Store in prod | No secrets in the repo |

## Repo layout

```
cold-email-tracker/
├── PLAN.md
├── README.md
├── .claude/skills/contact-finder/SKILL.md   # used in Phase 5
├── docker-compose.yml                         # local Postgres
├── .env.example
├── backend/
│   ├── app/
│   │   ├── main.py            # FastAPI app, CORS, routers
│   │   ├── db.py  models.py  schemas.py
│   │   ├── auth.py            # JWT verification + email allowlist
│   │   ├── parser.py          # paste-box logic (pure functions)
│   │   ├── templating.py      # token fill + validation (pure functions)
│   │   ├── gmail.py           # OAuth, build MIME, send
│   │   ├── worker.py          # process_queue()
│   │   ├── storage.py         # resume storage interface
│   │   ├── crypto.py          # encrypt/decrypt Gmail refresh token (Fernet)
│   │   └── routers/           # parse, contacts, companies, templates, send, settings, stats, gmail_auth
│   ├── alembic/
│   ├── tests/
│   └── pyproject.toml
├── frontend/                  # Next.js app
└── infra/
    └── template.yaml          # AWS SAM: API Lambda, worker Lambda, EventBridge schedule
```

## Data model

```
companies
  id, name, domain (unique), notes, created_at

domain_aliases                 -- extra domains for one company, e.g. fb.com -> Meta
  domain (pk), company_id -> companies

contacts
  id, email (unique, lowercase), first_name, last_name, title,
  company_id -> companies (nullable for personal emails),
  source (paste | csv | hunter | manual),
  status (new | queued | sending | sent | replied | bounced | failed),
  queued_at, sent_at, gmail_message_id, gmail_thread_id, error,
  created_at, updated_at

templates
  id, name, subject, body, is_default, updated_at

send_events                    -- append-only history
  id, contact_id -> contacts, event (queued | sent | failed | replied | bounced | requeued),
  detail, created_at

settings                       -- single row
  sender_name, resume_storage_key, resume_filename_pattern ("Eric_Resume_{company}.pdf"),
  daily_limit (25), send_window_start ("09:00"), send_window_end ("16:00"),
  send_days ("Mon-Fri"), timezone ("America/New_York"),
  gmail_address, gmail_refresh_token_encrypted
```

## Core logic specs

### Paste-box parser (`parser.py`, pure, no DB)

Input: any text. Output: list of preview rows `{email, first_name, last_name, domain, company_name, flags[]}`.

1. Extract emails with a robust regex; handle `Name <email>`, `mailto:`, commas, semicolons, newlines, surrounding punctuation. Lowercase and dedupe within the paste.
2. **Domain → company key** with `tldextract` (registrable domain): `jobs.amazon.com`, `amazon.co.uk` → `amazon`.
3. **Company name**, in priority order: `domain_aliases` → existing `companies.domain` → title-case the key (`amazon` → `Amazon`). The router passes known mappings in; the parser stays pure.
4. **Personal domains** (gmail, googlemail, outlook, hotmail, live, yahoo, icloud, me, proton, aol, and common .edu) → no company, flag `personal_email`.
5. **Role inboxes** (careers, jobs, recruiting, talent, hr, info, hello, contact, team, admin, noreply, no-reply, support) → flag `generic_inbox`.
6. **First name**, in priority order:
   - display name from `Name <email>`
   - local part split on `.` `_` `-`; two alphabetic parts of length ≥ 2 → first + last, title-cased (`john.smith` → John Smith)
   - single token found in a bundled common-first-names list (`sarah` → Sarah)
   - otherwise blank + flag `needs_name` (`jsmith` stays blank)
7. Router adds flag `already_contacted` for emails already in `contacts` with status beyond `new`.

### Import (`POST /contacts/import`)

Takes the edited preview rows. Creates missing companies; if I edited a company name in the preview, save it and add a `domain_aliases` row so the correction is remembered. Skips duplicates, returns created/skipped counts.

### Templating (`templating.py`, pure)

- Tokens: `[Company]`, `[Name]` (first name), `[FullName]`, `[Title]`. Matching is case-insensitive.
- `render(template, contact, company) -> (subject, body)`.
- **Validation:** raise if a used token has no value, or if any `[...]` token remains that isn't recognized. **Never send an email containing an unfilled token.**
- **Missing name is not a blocker** (decided 2026-10-15): `[Name]` / `[FullName]` fall back to "there" ("Hi there,"). The email address is what matters.
- Resume filename: `resume_filename_pattern` with `{company}` = company name stripped to alphanumerics (`Jane Street` → `Eric_Resume_JaneStreet.pdf`).

### Sending

- **Send now:** one contact at a time only. Renders, sends immediately, logs.
- **Queue:** bulk. Sets `status = queued`, `queued_at = now`.
- **Worker `process_queue()`**, triggered every 15 min:
  1. Exit if outside the send window or days (settings timezone).
  2. Exit if sent-today count ≥ `daily_limit`.
  3. **Atomically claim one contact:**
     `UPDATE contacts SET status='sending', updated_at=now() WHERE id = (SELECT id FROM contacts WHERE status='queued' ORDER BY queued_at LIMIT 1 FOR UPDATE SKIP LOCKED) RETURNING *;`
     Two concurrent workers must never claim the same contact.
  4. Render + validate; on validation error → `failed` with the reason.
  5. Build MIME (HTML body with a plain-text alternative and the signature appended, PDF attachment with per-company filename, From = sender name + Gmail address) and send via Gmail API.
  6. Success → `sent`, store `gmail_message_id` and `gmail_thread_id`. Error → `failed` with the message. **No automatic retry** (the email may have gone out); I requeue manually.
  7. Contacts stuck in `sending` for more than 30 min are shown in the UI with a warning; never auto-resent.
- Every status change appends a `send_events` row.

### Gmail connection

- Settings page "Connect Gmail" → OAuth web flow → callback stores the refresh token **encrypted** (`crypto.py`, key from env/SSM) plus the Gmail address.
- README must explain: create a Google Cloud project, enable Gmail API, configure the OAuth consent screen, add redirect URIs for local and prod, and **set the app to "In production"** (refresh tokens for apps in "Testing" expire after 7 days). For personal use I'll click through the "unverified app" warning.
- If the token stops working, the UI shows "Reconnect Gmail" and the worker pauses instead of failing every contact.

## API endpoints

All require a valid Supabase JWT whose email is on the allowlist (except the OAuth callback, which validates `state`).

```
POST   /parse                      {text} -> preview rows (no writes)
POST   /contacts/import            {rows[]} -> {created, skipped}
GET    /contacts                   ?status=&company_id=&q=&page=
PATCH  /contacts/{id}              edit name/title/company/status
DELETE /contacts/{id}
POST   /contacts/{id}/mark-replied
POST   /contacts/{id}/requeue
GET    /contacts/{id}/preview      rendered subject/body/attachment name
GET    /companies                  with contact counts + last contacted
PATCH  /companies/{id}
GET    /templates   POST /templates   PUT /templates/{id}
POST   /templates/preview          {subject, body, contact_id} -> rendered (for live editor)
POST   /send/now                   {contact_id}
POST   /send/queue                 {contact_ids[]}
GET    /settings    PUT /settings
POST   /resume                     multipart PDF upload (max 5 MB, PDF only)
GET    /gmail/status
GET    /gmail/connect   GET /gmail/callback
GET    /stats                      sent today/week, total companies, replies, reply rate, sends per day (30 days)
```

## Frontend pages

- **/login:** magic-link sign-in.
- **/ (Dashboard):** stat cards (sent this week, companies, replies, reply rate), sends-per-day chart, recent activity feed, warnings (Gmail disconnected, stuck sends, no resume uploaded).
- **/import:** large paste box + CSV upload (Apollo export) → **Parse** → editable preview table (email, first name, company, flags as colored badges, include checkbox) → **Import selected**.
- **/contacts:** filterable, searchable table with status badges; bulk select → Queue / Delete; row actions → Send now, Mark replied, Requeue, Preview (drawer showing the exact rendered email and attachment name).
- **/companies:** company list with counts per status and last-contacted date; inline-edit names.
- **/templates:** subject + body editor, token helper buttons, live preview against a selected contact, set default.
- **/settings:** Gmail connect status, resume upload, sender name, filename pattern, daily limit, send window, timezone.

## Phases

### Phase 1: Backend core (no sending)
Models + Alembic migration, docker compose Postgres, parser, templating, import, contacts/companies/templates/settings/stats endpoints, local resume storage. Auth can use a dev bypass flag (`AUTH_DISABLED=true`, refused when `ENV=prod`).

**Checks:** `pytest` passes, including a table-driven parser test with at least 25 messy-input cases (formats, subdomains, country TLDs, personal domains, role inboxes, name patterns, duplicates) and templating tests (missing token, unknown token, case-insensitivity, filename sanitizing). `curl` the parse → import → preview flow end to end.

### Phase 2: Frontend dashboard
All pages wired to the API (sending buttons can be disabled until Phase 3).

**Checks:** `npm run build`, lint, and typecheck pass; I can paste emails, fix a company name, import, edit the template, and see correct previews in the browser.

### Phase 3: Gmail + sending (local)
OAuth connect, token encryption, Send now, queue, `worker.py` with `python -m app.worker --once` for local runs.

**Checks:** tests with mocked Gmail (sent/failed transitions, event log, daily limit, send window); a concurrency test proving two simultaneous `process_queue()` calls never claim the same contact; then I'll send one real email to myself and confirm the attachment name and `threadId` are stored.

### Phase 4: Deploy
Supabase project (DB, Auth, Storage), SAM template (API Lambda via Mangum + worker Lambda + EventBridge Scheduler every 15 min), secrets in SSM, frontend on Vercel, CORS locked to the Vercel domain, real auth on.

**Checks:** deploy from a clean checkout following README only; logged-out requests get 401; a queued test email to myself sends from the cloud worker.

### Phase 5: Later (don't build until asked)
- Hunter contact finder → follow `.claude/skills/contact-finder/SKILL.md`; new contacts land as `new` with source `hunter`.
- Reply and bounce detection: add `gmail.readonly`, poll stored `gmail_thread_id`s.
- AI first line: one LLM call per contact grounded in the company's about page; requires my approval before queueing.
- Reply triage + follow-up workflow (good fit for LangGraph: stateful, branching, human approval).

## Rules for the whole project

- Safe by default: bulk sending only through the throttled queue; every send is logged; nothing is ever resent automatically.
- **One email per address, ever** (decided 2026-10-15): once an address has been sent, replied, or bounced, it can never be queued or sent again (checked in `services.transition`, backed by a unique index allowing one `sent` event per contact). Emailed contacts can't be deleted, so a re-import can't bring them back as new. Requeueing a stuck send requires confirming it isn't in Gmail's Sent folder.
- No secrets, tokens, or resume files in git (`.gitignore` covers `.env`, `credentials*.json`, `token*.json`, uploads).
- Keep `parser.py` and `templating.py` pure and fully unit-tested; they're the core of the app.
- Small, readable code. No extra frameworks beyond the stack above without asking.
