---
name: contact-finder
description: Use when finding recruiter or engineer email addresses for the cold email tracker with the Hunter.io API — building the Hunter contact finder, choosing search filters, or deciding which Hunter calls to make on a limited free-tier credit budget.
---

# Contact Finder (Hunter.io, free tier)

Goal: turn a list of target companies into a few **high-quality** contacts per company for `contacts.csv`, using as few Hunter credits as possible. The free plan has about **50 credits/month**, so every call must count.

## 1. Check the budget first (free call)

Before any paid call, hit `GET https://api.hunter.io/v2/account?api_key=...`. It returns remaining searches/verifications and costs nothing. Stop and report if the remaining budget is below what the run needs. Pricing and quotas change — confirm current credit costs at https://hunter.io/api-documentation/v2 rather than trusting numbers in this file.

## 2. Cache everything, never pay twice

- Store every raw response in `cache/hunter/<endpoint>/<key>.json` (key = domain, or `domain_first_last`).
- Check the cache before every request. Cached results stay valid for 30 days.
- Before searching a company, check the `contacts` table — if that company already has enough contacts, skip it.

## 3. Pick the cheapest call for what you know

| What you have | Call | Why |
|---|---|---|
| A person's name + company domain (found manually on Apollo free / LinkedIn) | `email-finder` (`domain`, `first_name`, `last_name`) | Most precise; Hunter doesn't charge when no email is found |
| Only a company | `domain-search` with filters (below) | One request returns several people |
| An email with low confidence | `email-verifier` | Costs less than a search, but only use it when needed |

Resolve the company domain yourself (e.g. `stripe.com`) instead of passing `company=` — fewer wrong matches. Watch for companies whose careers or recruiting team uses a different domain.

## 4. Domain-search filters that save credits

Always narrow the search instead of pulling everyone:

- `type=personal` — skip generic inboxes like `info@` / `jobs@`
- `department=hr` for recruiters, or `department=it` for engineers and engineering managers (run the HR query first; it's usually the better target)
- `seniority=senior` (managers) or `junior` (recent-grad engineers who often forward referrals)
- `required_field=full_name,position` — only people you can address by name with a known title
- `limit` = just what you need (2–5); don't fetch extra rows you won't email

Verify parameter names against the current docs before first use.

## 5. Who to target (ranked)

1. University / campus / early-career recruiter
2. Technical recruiter or talent acquisition partner
3. Engineering manager on a team that matches my background (AI, backend)
4. Software engineer who is a UMass alum or a recent grad (warmer, more likely to refer)

Skip: executives, sales, marketing, generic HR operations.

For big tech (Meta, Google, etc.), recruiter inboxes are flooded — prefer engineering managers and alumni engineers there. Mid-size companies and startups reply much more often per email sent, so weight the target list toward them.

## 6. Quality filter before writing a row

- `confidence >= 85` → accept without verifying
- `70–84` → verify only if budget allows; otherwise skip
- `< 70` or verifier says `undeliverable` / `risky` → drop
- Require a first name (the template needs `{first_name}`) — split from `full_name` if needed

## 7. Output

Insert results through the tracker's import path (same logic as `POST /contacts/import`) so company mapping, alias memory, and dedupe stay in one place. Each new contact gets `status = new`, `source = hunter`, plus `title`. Store Hunter's `confidence` in the import detail / `send_events` note. Dedupe on lowercase email against all existing contacts — never re-add someone already queued, sent, or replied.

## 8. End-of-run report

Print: credits used this run, credits remaining (from `/account`), contacts added per company, companies skipped and why, and any cache hits that saved credits.