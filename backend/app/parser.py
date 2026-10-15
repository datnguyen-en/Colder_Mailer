"""Paste-box parser: messy text in, preview rows out.

Pure functions only: no DB, no network. Known company mappings are passed in.
"""

import csv
import io
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import TypeVar
from urllib.parse import unquote

import tldextract

PERSONAL_EMAIL = "personal_email"
GENERIC_INBOX = "generic_inbox"
NEEDS_NAME = "needs_name"

# Bundled public-suffix snapshot; never fetches over the network.
_extract = tldextract.TLDExtract(suffix_list_urls=(), cache_dir=None)

EMAIL_RE = re.compile(
    r"[A-Za-z0-9._%+'-]+@(?:[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?\.)+[A-Za-z]{2,24}"
)
# Text right before an email that looks like `Name <` or `"Last, First" <mailto:`.
_DISPLAY_RE = re.compile(r'(?:"([^"]*)"|([^<>,;:@\n\r\t"]*))\s*<\s*(?:mailto:)?$', re.IGNORECASE)

# Personal providers, matched on the registrable domain's name so country
# variants (yahoo.co.uk, hotmail.fr) are covered too.
PERSONAL_KEYS = frozenset({
    "gmail", "googlemail", "outlook", "hotmail", "live", "msn", "yahoo", "ymail",
    "icloud", "me", "mac", "proton", "protonmail", "pm", "aol", "gmx", "mail", "qq",
})

ROLE_INBOXES = frozenset({
    "careers", "career", "jobs", "job", "recruiting", "recruitment", "recruiter", "talent",
    "hr", "info", "hello", "hi", "contact", "team", "admin", "noreply", "no-reply", "no_reply",
    "donotreply", "do-not-reply", "support", "hiring", "internships", "internship",
    "university", "campus", "newgrad", "people", "office", "help", "inquiries", "enquiries",
    "sales", "press", "marketing", "privacy", "legal", "billing", "webmaster", "postmaster",
})
# Role words that also show up glued into one token, e.g. "amazoncareers@".
_ROLE_SUBSTRINGS = ("careers", "recruiting", "noreply", "donotreply", "talentacquisition")

_HONORIFICS = frozenset({"mr", "mrs", "ms", "miss", "dr", "prof"})
_SUFFIXES = frozenset({"jr", "sr", "ii", "iii", "iv", "phd", "md", "mba"})
# Prose that can sit right before `<email>`: "Or <...>", "please contact Jane <...>".
_PROSE_WORDS = frozenset({
    "or", "and", "to", "at", "cc", "bcc", "from", "email", "contact", "reach", "please",
    "me", "us", "via", "by", "with", "out", "write",
})

V = TypeVar("V")


@dataclass
class PreviewRow:
    email: str
    first_name: str | None
    last_name: str | None
    domain: str
    company_name: str | None
    title: str | None = None
    flags: list[str] = field(default_factory=list)


@lru_cache
def first_names() -> frozenset[str]:
    path = Path(__file__).parent / "data" / "first_names.txt"
    words: set[str] = set()
    for line in path.read_text().splitlines():
        if not line.startswith("#"):
            words.update(line.split())
    return frozenset(words)


# --- domains -----------------------------------------------------------------


def split_domain(host: str) -> tuple[str, str] | None:
    """`jobs.amazon.co.uk` -> ("amazon.co.uk", "amazon"). None if no valid suffix."""
    ext = _extract(host.lower())
    if not ext.domain or not ext.suffix:
        return None
    return f"{ext.domain}.{ext.suffix}", ext.domain


def company_key(domain: str) -> str:
    parts = split_domain(domain)
    return parts[1] if parts else domain.lower()


def is_personal_domain(domain: str) -> bool:
    parts = split_domain(domain)
    if not parts:
        return False
    registrable, key = parts
    suffix = registrable[len(key) + 1:]
    academic = suffix == "edu" or suffix.endswith(".edu") or suffix.startswith(("edu.", "ac."))
    return key in PERSONAL_KEYS or academic


def resolve(domain: str, aliases: Mapping[str, V], companies: Mapping[str, V]) -> V | None:
    """Find the known company for a registrable domain.

    Priority: alias -> company with that exact domain -> company with the same
    key (amazon.co.uk matches a company stored as amazon.com).
    """
    if domain in aliases:
        return aliases[domain]
    if domain in companies:
        return companies[domain]
    key = company_key(domain)
    for company_domain, value in companies.items():
        if company_key(company_domain) == key:
            return value
    return None


# --- names -------------------------------------------------------------------


def _cap(word: str) -> str:
    """Title-case all-lower/all-upper words; leave mixed case (McDonald) alone."""
    if word.islower() or word.isupper():
        return "-".join(p.capitalize() for p in word.split("-"))
    return word


def _alnum(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def name_from_display(display: str) -> tuple[str, str | None] | None:
    display = display.strip().strip("'\"").strip()
    if not display or "@" in display:
        return None
    if "," in display:  # "Smith, John"
        last, _, first = display.partition(",")
        display = f"{first} {last}"
    display = re.sub(r"\(.*?\)", " ", display)  # "Jane Doe (Recruiting)"
    display = re.split(r"\s[|\-–—]\s", display)[0]  # "Jane Doe | Recruiter"
    words = [w.strip(".") for w in display.split()]
    words = [w for w in words if re.fullmatch(r"[^\W\d_][^\W\d_'’-]*", w)
             and w.lower() not in _PROSE_WORDS]
    if len(words) > 3:  # prose like "Please contact Jane Doe <...>"
        words = words[-2:]
    while words and words[0].lower() in _HONORIFICS:
        words.pop(0)
    while words and words[-1].lower() in _SUFFIXES:
        words.pop()
    if not words:
        return None
    first = _cap(words[0])
    last = _cap(words[-1]) if len(words) > 1 else None
    return first, last


def name_from_local(local: str) -> tuple[str, str | None] | None:
    """Guess a name from the part before @. None when it can't tell."""
    local = local.split("+", 1)[0]
    parts = [re.sub(r"\d+", "", p) for p in re.split(r"[._-]+", local)]
    parts = [p.lower() for p in parts if p]
    if not parts or not all(p.isalpha() for p in parts):
        return None
    if len(parts) == 2 and len(parts[0]) >= 2 and len(parts[1]) >= 2:
        return parts[0].capitalize(), parts[1].capitalize()
    if len(parts) == 3 and len(parts[1]) == 1 and len(parts[0]) >= 2 and len(parts[2]) >= 2:
        return parts[0].capitalize(), parts[2].capitalize()  # john.q.smith
    if parts[0] in first_names():
        return parts[0].capitalize(), None
    return None


def is_generic_inbox(local: str) -> bool:
    local = local.split("+", 1)[0].lower()
    first_token = re.split(r"[._-]+", local)[0]
    return (
        local in ROLE_INBOXES
        or first_token in ROLE_INBOXES
        or any(s in local for s in _ROLE_SUBSTRINGS)
    )


# --- extraction --------------------------------------------------------------


@dataclass
class _Found:
    email: str
    registrable: str
    key: str
    display: str | None


def _clean_email(raw: str) -> tuple[str, str, str] | None:
    """Lowercase, strip stray punctuation, and trim junk glued after the TLD."""
    local, _, host = raw.lower().partition("@")
    local = local.strip(".'-")
    labels = host.split(".")
    while len(labels) >= 2:
        parts = split_domain(".".join(labels))
        if parts:
            return f"{local}@{'.'.join(labels)}", *parts
        labels.pop()  # "amazon.com.thanks" -> "amazon.com"
    return None


def extract(text: str) -> list[_Found]:
    """All unique emails in `text`, in order, with any `Name <email>` display name."""
    text = unquote(text)  # mailto:john%40x.com
    found: dict[str, _Found] = {}
    for m in EMAIL_RE.finditer(text):
        cleaned = _clean_email(m.group(0))
        if not cleaned or not cleaned[0].split("@")[0]:
            continue
        email, registrable, key = cleaned
        before = _DISPLAY_RE.search(text[max(0, m.start() - 120):m.start()])
        display = (before.group(1) or before.group(2)) if before else None
        if email not in found:
            found[email] = _Found(email, registrable, key, display)
        elif display and not found[email].display:
            found[email].display = display  # a later "Name <email>" beats a bare repeat
    return list(found.values())


def build_row(
    found: _Found,
    aliases: Mapping[str, str],
    companies: Mapping[str, str],
    *,
    first: str | None = None,
    last: str | None = None,
    title: str | None = None,
    company_hint: str | None = None,
) -> PreviewRow:
    flags: list[str] = []
    local = found.email.split("@")[0]

    company_name: str | None = None
    if is_personal_domain(found.registrable):
        flags.append(PERSONAL_EMAIL)
    else:
        company_name = (
            resolve(found.registrable, aliases, companies)
            or company_hint
            or found.key.title()
        )

    generic = is_generic_inbox(local)
    if generic:
        flags.append(GENERIC_INBOX)

    if not first and not generic:
        name = None
        if found.display:
            name = name_from_display(found.display)
            # "Stripe <jane@stripe.com>" names the company, not the person.
            company_words = {found.key, _alnum(company_name or "")}
            if name and (_alnum(found.display) in company_words
                         or name[0].lower() in company_words):
                name = None
        first, last = name or name_from_local(local) or (None, None)
    if not first:
        flags.append(NEEDS_NAME)

    return PreviewRow(
        email=found.email,
        first_name=first,
        last_name=last,
        domain=found.registrable,
        company_name=company_name,
        title=title,
        flags=flags,
    )


def parse(
    text: str,
    aliases: Mapping[str, str] | None = None,
    companies: Mapping[str, str] | None = None,
) -> list[PreviewRow]:
    """Messy pasted text -> preview rows.

    `aliases` and `companies` map registrable domains to known company names.
    """
    return [build_row(f, aliases or {}, companies or {}) for f in extract(text)]


_CSV_COLUMNS = {
    "email": ("email", "email address", "work email", "e-mail"),
    "first": ("first name", "first_name", "firstname", "first"),
    "last": ("last name", "last_name", "lastname", "last"),
    "title": ("title", "job title", "position"),
    "company": ("company", "company name", "company name for emails", "organization"),
}


def parse_csv(
    text: str,
    aliases: Mapping[str, str] | None = None,
    companies: Mapping[str, str] | None = None,
) -> list[PreviewRow]:
    """CSV export (Apollo and similar) -> preview rows, using its name/title/company
    columns. Falls back to plain-text parsing if there is no email column."""
    reader = csv.DictReader(io.StringIO(text.lstrip("﻿")))
    headers = {h.strip().lower(): h for h in (reader.fieldnames or []) if h}
    cols = {
        field_: next((headers[c] for c in names if c in headers), None)
        for field_, names in _CSV_COLUMNS.items()
    }
    if not cols["email"]:
        return parse(text, aliases, companies)

    def cell(record: dict[str, str], field_: str) -> str | None:
        col = cols[field_]
        value = (record.get(col) or "").strip() if col else ""
        return value or None

    rows: dict[str, PreviewRow] = {}
    for record in reader:
        found = extract(cell(record, "email") or "")
        if not found or found[0].email in rows:
            continue
        first, last = cell(record, "first"), cell(record, "last")
        rows[found[0].email] = build_row(
            found[0], aliases or {}, companies or {},
            first=_cap(first) if first else None,
            last=_cap(last) if last else None,
            title=cell(record, "title"),
            company_hint=cell(record, "company"),
        )
    return list(rows.values())
