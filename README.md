# Cold Email Tracker

Personal dashboard for internship cold outreach: paste emails → map to companies → fill one template → send through Gmail on a throttled queue → track replies. See [PLAN.md](PLAN.md) for the full design and build phases.

**Status:** Phases 1–3 are built: backend, dashboard, and Gmail sending (local). Deploying (Phase 4) is next.

## Local development

Requirements: Docker, [uv](https://docs.astral.sh/uv/) (Python 3.12 is pinned and installed by uv).

```bash
cp .env.example .env              # dev defaults: local Postgres, AUTH_DISABLED=true
docker compose up -d --wait       # Postgres 17 on localhost:5433 (set POSTGRES_PORT to change)

cd backend
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --port 8000
```

API docs: http://localhost:8000/docs

In a second terminal, the dashboard (needs Node 20+):

```bash
cd frontend
cp .env.example .env.local        # points at the API on localhost:8000; Supabase left blank = no login
npm install
npm run dev                       # http://localhost:3000
```

`AUTH_DISABLED=true` is a dev-only bypass. The app refuses to start with it when `ENV=prod`. With auth on, every endpoint except `/health` needs a Supabase access token for `ALLOWED_EMAIL`. Tokens are checked against the project's JWKS (`SUPABASE_URL`), or against `SUPABASE_JWT_SECRET` for projects on the legacy shared secret.

### Connect Gmail (one-time Google Cloud setup)

The app sends through the Gmail API with the `gmail.send` permission only (it can't read your mail).

1. Go to https://console.cloud.google.com, sign in with the Gmail you'll send from, and **create a project** (e.g. "Cold Email Tracker").
2. **APIs & Services → Library →** search "Gmail API" → **Enable**.
3. **Google Auth Platform** (formerly "OAuth consent screen") **→ Get started:** app name "Cold Email Tracker", your Gmail as support and contact email, audience **External**. Create.
4. **Data Access → Add or remove scopes:** add `.../auth/gmail.send`, plus `openid` and `.../auth/userinfo.email`. Save.
5. **Audience → Publish app**, so the status says **In production**. In "Testing", Google expires the connection after 7 days. Because the app isn't verified by Google, you'll click through a "Google hasn't verified this app" warning when connecting (Advanced → Go to Cold Email Tracker). That's expected for a personal app.
6. **Clients → Create client →** type **Web application**. Under **Authorized redirect URIs** add `http://localhost:8000/gmail/callback` (and the production one in Phase 4). Create.
7. Copy the **Client ID** and **Client secret** into `.env` as `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET`, and make sure `TOKEN_ENCRYPTION_KEY` is set (`.env.example` shows how to generate one). Restart the backend.
8. In the dashboard: **Settings → Connect Gmail.**

If the connection ever stops working, sending pauses (nothing is marked failed) and the dashboard shows **Reconnect Gmail**.

### Sending

- **Send now** (contacts page, or the contact drawer) sends one email immediately. It ignores the send window but respects the daily limit.
- **Queue** (select contacts, then Queue) hands them to the sender, which sends one per run, oldest first, only inside the send window and under the daily limit.
- Run the sender locally:

  ```bash
  cd backend
  uv run python -m app.worker --once        # one run: sends at most one email
  uv run python -m app.worker --every 15    # keep running, every 15 minutes
  ```

  In production (Phase 4) a scheduler runs it every 15 minutes.

### Tests and checks

```bash
cd backend && uv run pytest
cd frontend && npm run lint && npm run typecheck && npm run build
```

API tests use a separate `cold_email_test` database on the same Postgres (created automatically and rebuilt by running the Alembic migrations). Override it with `TEST_DATABASE_URL`. Parser and templating tests need no database.

### Try the main flow with curl

```bash
API=localhost:8000; J='Content-Type: application/json'
ROWS=$(curl -s -X POST $API/parse -H "$J" -d '{"text":"Jane Doe <jane.doe@stripe.com>, jsmith@ramp.com"}')
echo "$ROWS"                                   # preview rows with flags; nothing saved yet
curl -s -X POST $API/contacts/import -H "$J" -d "{\"rows\": $ROWS}"
curl -s -X POST $API/templates -H "$J" \
  -d '{"name":"Main","subject":"Internship at [Company]","body":"Hi [Name],\n\n..."}'
curl -s "$API/contacts" | jq '.items[] | {id, email, status}'
curl -s $API/contacts/1/preview                # exact subject/body/attachment name + problems
```

## Dashboard pages

- **Dashboard:** this week's sends, companies, replies, reply rate, a sends-per-day chart, recent activity, and warnings (Gmail not connected, no resume, no template, stuck sends).
- **Import:** paste text or upload a CSV, fix names and companies in the preview, then import the checked rows. Renaming a company updates every row from that domain that had the same guess.
- **Contacts:** search, filter by status, bulk delete. Click an email to edit the contact and see the exact email it would receive.
- **Companies:** contact counts per status; click a name to rename it.
- **Template:** subject and body editor with token buttons and a live preview against any contact.
- **Settings:** resume upload, sender name, filename pattern, daily limit, send window, timezone.

## Layout

```
backend/app/
  parser.py       paste-box parsing (pure): emails, domain → company, name guessing, flags
  templating.py   [Company]/[Name]/[FullName]/[Title] filling + validation, resume filename (pure)
  services.py     DB logic shared by routers / worker: company resolution, import, status changes
  routers/        parse, contacts, companies, templates, settings (+ resume upload), stats, send, gmail_auth
  gmail.py        OAuth flow, MIME building, sending; errors split into not-sent vs. unclear
  worker.py       process_queue(): claim one queued contact atomically and send it
  crypto.py       encrypts the Gmail refresh token at rest
  models.py       SQLAlchemy models; alembic/ holds the migrations
  auth.py         Supabase JWT check + single-email allowlist
  storage.py      resume storage (local folder now, Supabase Storage in Phase 4)
  data/first_names.txt   names used to recognise local parts like "sarah@"
frontend/src/
  app/            one folder per page (import, contacts, companies, templates, settings, login)
  components/     app components; components/ui/ is shadcn/ui (Base UI flavour)
  lib/api.ts      typed API client (adds the Supabase token when login is on)
```

## Notes on behaviour

- **Company names:** a domain resolves through domain aliases first, then a company with that exact domain, then a company with the same name key (so `amazon.co.uk` finds the company stored as `amazon.com`). If neither matches, the key is title-cased. If you change a company name in the preview, the import saves it and adds a domain alias so the correction sticks.
- **Flags:** `personal_email`, `generic_inbox`, `needs_name`, `already_contacted` (status beyond `new`), `already_imported` (already in the table as `new`; import will skip it).
- **One email per address, ever:** once someone has been sent an email (or marked sent, replied or bounced), nothing can queue or send to them again, and they can't be deleted, so re-importing them is skipped. If Gmail doesn't clearly confirm a send (timeout, server error), the contact stays in `sending`, is shown as stuck, and is never retried automatically. Requeueing it asks you to check Gmail's Sent folder first.
- **Templates:** there is always exactly one default template. A missing first name is fine: `[Name]` becomes "there". Rendering fails, listing every problem, if `[Company]` or `[Title]` is used without a value, or any unknown `[...]` / `{...}` placeholder is left.
- **Manual status changes** (`PATCH /contacts/{id}`) can set `queued`, `sent`, `replied`, `bounced` or `failed`. A contact can only be queued from `new` or `failed`, so nothing already sent gets queued again. `requeue` is only for `failed` contacts, or ones stuck in `sending` for over 30 minutes. `unqueue` takes a queued contact back to `new`.
