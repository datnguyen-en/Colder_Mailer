"""Fill [Company] / [Name] / [FullName] / [Title] tokens. Pure functions.

An email must never go out with an unfilled token, so `render` raises on any
token it can't fill and on any [...] or {...} placeholder it doesn't know.
"""

import re
import unicodedata
from typing import Any, Protocol

TOKEN_RE = re.compile(r"\[([^\[\]\r\n]*)\]")
# Placeholders from other tools ({first_name}, {{company}}) would go out literally.
CURLY_RE = re.compile(r"\{\{?\s*[A-Za-z_]+\s*\}?\}")
KNOWN_TOKENS = ("company", "name", "fullname", "title")


class TemplateLike(Protocol):
    subject: str
    body: str


class TemplateError(ValueError):
    def __init__(self, problems: list[str]):
        self.problems = problems
        super().__init__("; ".join(problems))


def _text(obj: Any, attr: str) -> str:
    value = getattr(obj, attr, None) if obj is not None else None
    return value.strip() if isinstance(value, str) else ""


def token_values(contact: Any, company: Any) -> dict[str, str]:
    first, last = _text(contact, "first_name"), _text(contact, "last_name")
    return {
        "company": _text(company, "name"),
        "name": first,
        "fullname": f"{first} {last}".strip() if first else "",
        "title": _text(contact, "title"),
    }


def render_partial(
    template: TemplateLike, contact: Any, company: Any
) -> tuple[str, str, list[str]]:
    """Fill what can be filled; leave the rest in place and list the problems.
    Used by the live editor preview."""
    values = token_values(contact, company)
    problems: list[str] = []

    def fill(match: re.Match[str]) -> str:
        token = match.group(1)
        key = token.lower()
        if key not in KNOWN_TOKENS:
            problems.append(f"Unknown token [{token}]")
            return match.group(0)
        if not values[key]:
            problems.append(f"[{token}] has no value for this contact")
            return match.group(0)
        return values[key]

    subject = TOKEN_RE.sub(fill, template.subject or "")
    body = TOKEN_RE.sub(fill, template.body or "")
    for text in (template.subject or "", template.body or ""):
        for match in CURLY_RE.finditer(text):
            problems.append(f"Unknown placeholder {match.group(0)}")
    if not subject.strip():
        problems.append("Subject is empty")
    if not body.strip():
        problems.append("Body is empty")
    return subject, body, list(dict.fromkeys(problems))


def render(template: TemplateLike, contact: Any, company: Any) -> tuple[str, str]:
    """(subject, body) with every token filled, or TemplateError."""
    subject, body, problems = render_partial(template, contact, company)
    if problems:
        raise TemplateError(problems)
    return subject, body


def company_slug(name: str | None) -> str:
    """`Jane Street` -> `JaneStreet`, `Société Générale` -> `SocieteGenerale`."""
    ascii_name = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Za-z0-9]", "", ascii_name)


def resume_filename(pattern: str, company_name: str | None) -> str:
    """Fill `{company}` in the filename pattern. With no company, the token and
    the separator before it are dropped (`Eric_Resume.pdf`)."""
    slug = company_slug(company_name)
    if slug:
        name = re.sub(r"\{company\}", slug, pattern, flags=re.IGNORECASE)
    else:
        name = re.sub(r"[ _-]?\{company\}", "", pattern, flags=re.IGNORECASE)
    name = re.sub(r"[^A-Za-z0-9._ -]", "", name).strip(" .") or "Resume"
    if not name.lower().endswith(".pdf"):
        name += ".pdf"
    return name
