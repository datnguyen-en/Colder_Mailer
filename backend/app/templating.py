"""Fill [Company] / [Name] / [FullName] / [Title] tokens. Pure functions.

An email must never go out with an unfilled token, so `render` raises on any
token it can't fill and on any [...] or {...} placeholder it doesn't know.
A missing name isn't a blocker: [Name] and [FullName] fall back to "there"
("Hi there,"), since the email address is what matters.

The subject is plain text. The body is HTML (see richtext.py): it is sanitized,
the signature is appended, and token values are HTML-escaped as they go in.
"""

import html
import re
import unicodedata
from typing import Any, Protocol

from app import richtext

TOKEN_RE = re.compile(r"\[([^\[\]\r\n]*)\]")
# Placeholders from other tools ({first_name}, {{company}}) would go out literally.
CURLY_RE = re.compile(r"\{\{?\s*[A-Za-z_]+\s*\}?\}")
KNOWN_TOKENS = ("company", "name", "fullname", "title")
NAME_FALLBACK = "there"
TAG_RE = re.compile(r"<[^>]*>")
SIGNATURE_SEPARATOR = "<p>--</p>"


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
        "name": first or NAME_FALLBACK,
        "fullname": f"{first} {last}".strip() if first else NAME_FALLBACK,
        "title": _text(contact, "title"),
    }


def body_html(body: str, signature: str = "") -> str:
    """The sanitized body, with the signature after a "--" line if there is one."""
    html_body = richtext.sanitize(body)
    sig = richtext.sanitize(signature)
    if richtext.to_text(sig):
        html_body += SIGNATURE_SEPARATOR + sig
    return html_body


def render_partial(
    template: TemplateLike, contact: Any, company: Any, signature: str = ""
) -> tuple[str, str, list[str]]:
    """Fill what can be filled; leave the rest in place and list the problems.
    Returns (subject text, body HTML, problems). Used by the live editor preview."""
    values = token_values(contact, company)
    problems: list[str] = []

    def filler(escape: bool):
        def fill(match: re.Match[str]) -> str:
            token = TAG_RE.sub("", match.group(1))  # [<strong>Name</strong>] counts as [Name]
            key = token.lower()
            if key not in KNOWN_TOKENS:
                problems.append(f"Unknown token [{token}]")
                return match.group(0)
            if not values[key]:
                problems.append(f"[{token}] has no value for this contact")
                return match.group(0)
            return html.escape(values[key]) if escape else values[key]
        return fill

    source_body = body_html(template.body or "", signature)
    subject = TOKEN_RE.sub(filler(escape=False), template.subject or "")
    body = TOKEN_RE.sub(filler(escape=True), source_body)
    for text in (template.subject or "", source_body):
        for match in CURLY_RE.finditer(text):
            problems.append(f"Unknown placeholder {match.group(0)}")
    if not subject.strip():
        problems.append("Subject is empty")
    if not richtext.to_text(richtext.sanitize(template.body or "")):
        problems.append("Body is empty")
    return subject, body, list(dict.fromkeys(problems))


def render(
    template: TemplateLike, contact: Any, company: Any, signature: str = ""
) -> tuple[str, str]:
    """(subject text, body HTML) with every token filled, or TemplateError."""
    subject, body, problems = render_partial(template, contact, company, signature)
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
