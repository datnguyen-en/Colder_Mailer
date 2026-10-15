# Cold Email Tracker

Personal dashboard for internship cold outreach: paste emails → map to companies → fill one template → send through Gmail on a throttled queue → track replies. See [PLAN.md](PLAN.md) for the full design and build phases.

**Status:** Phase 1 (backend core, no sending) is built.

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

`AUTH_DISABLED=true` is a dev-only bypass. The app refuses to start with it when `ENV=prod`. With auth on, every endpoint except `/health` needs a Supabase access token for `ALLOWED_EMAIL`. Tokens are checked against the project's JWKS (`SUPABASE_URL`), or against `SUPABASE_JWT_SECRET` for projects on the legacy shared secret.

### Tests

```bash
cd backend
uv run pytest
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

## Layout

```
backend/app/
  parser.py       paste-box parsing (pure): emails, domain → company, name guessing, flags
  templating.py   [Company]/[Name]/[FullName]/[Title] filling + validation, resume filename (pure)
  services.py     DB logic shared by routers / worker: company resolution, import, status changes
  routers/        parse, contacts, companies, templates, settings (+ resume upload), stats
  models.py       SQLAlchemy models; alembic/ holds the migrations
  auth.py         Supabase JWT check + single-email allowlist
  storage.py      resume storage (local folder now, Supabase Storage in Phase 4)
  data/first_names.txt   names used to recognise local parts like "sarah@"
```

## Notes on behaviour

- **Company names:** a domain resolves through domain aliases first, then a company with that exact domain, then a company with the same name key (so `amazon.co.uk` finds the company stored as `amazon.com`). If neither matches, the key is title-cased. If you change a company name in the preview, the import saves it and adds a domain alias so the correction sticks.
- **Flags:** `personal_email`, `generic_inbox`, `needs_name`, `already_contacted` (status beyond `new`), `already_imported` (already in the table as `new`; import will skip it).
- **Templates:** there is always exactly one default template. Rendering fails, listing every problem, if a used token has no value or any unknown `[...]` / `{...}` placeholder is left.
- **Manual status changes** (`PATCH /contacts/{id}`) can set `queued`, `sent`, `replied`, `bounced` or `failed`. A contact can only be queued from `new` or `failed`, so nothing already sent gets queued again. `requeue` is only for `failed` contacts, or ones stuck in `sending` for over 30 minutes.
