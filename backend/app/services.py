"""DB-facing logic shared by routers, the worker, and the contact finder."""

from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import exists, func, select
from sqlalchemy.orm import Session

from app import parser, schemas, templating
from app.models import AppSettings, Company, Contact, DomainAlias, SendEvent, Template

STUCK_AFTER = timedelta(minutes=30)


def get_settings(db: Session) -> AppSettings:
    settings = db.get(AppSettings, 1)
    if settings is None:
        settings = AppSettings(id=1)
        db.add(settings)
        db.commit()
    return settings


def default_template(db: Session) -> Template | None:
    return db.scalar(select(Template).where(Template.is_default))


def preview_email(db: Session, template: templating.TemplateLike, contact: Contact) -> schemas.EmailPreview:
    """Exactly what would be sent to this contact, plus anything blocking it."""
    settings = get_settings(db)
    subject, body, problems = templating.render_partial(template, contact, contact.company)
    if not settings.resume_storage_key:
        problems.append("No resume uploaded")
    return schemas.EmailPreview(
        subject=subject,
        body=body,
        attachment_name=templating.resume_filename(
            settings.resume_filename_pattern, contact.company_name
        ),
        to=contact.email,
        problems=problems,
    )


def is_stuck(contact: Contact, now: datetime | None = None) -> bool:
    """In `sending` for too long, or Gmail's answer was unclear (error is set).
    Either way it may have gone out, so it's never resent automatically."""
    now = now or datetime.now(UTC)
    return contact.status == "sending" and (
        contact.error is not None or now - contact.updated_at > STUCK_AFTER
    )


def sent_on_day(db: Session, tz: str, when: datetime) -> int:
    """Emails sent on `when`'s calendar day in timezone `tz`."""
    day = when.astimezone(ZoneInfo(tz)).date()
    local_day = func.date(func.timezone(tz, SendEvent.created_at))
    return db.scalar(
        select(func.count()).where(SendEvent.event == "sent", local_day == day)
    ) or 0


# --- companies ---------------------------------------------------------------


class CompanyIndex:
    """Known companies keyed the ways import and parse need to look them up."""

    def __init__(self, db: Session):
        companies = db.scalars(select(Company)).all()
        self.by_domain = {c.domain: c for c in companies if c.domain}
        self.by_name = {}
        for c in sorted(companies, key=lambda c: c.id):
            self.by_name.setdefault(c.name.lower(), c)
        self.aliases = {a.domain: a.company for a in db.scalars(select(DomainAlias)).all()}

    def resolve(self, domain: str) -> Company | None:
        return parser.resolve(domain, self.aliases, self.by_domain)

    def name_maps(self) -> tuple[dict[str, str], dict[str, str]]:
        """(aliases, companies) as domain -> name, the shape the parser takes."""
        return (
            {d: c.name for d, c in self.aliases.items()},
            {d: c.name for d, c in self.by_domain.items()},
        )


def _company_for_row(db: Session, index: CompanyIndex, domain: str, name: str) -> Company:
    """The company a preview row should land in, creating it if needed.

    If the name was edited in the preview so it no longer matches what the
    domain resolves to, a domain alias is saved so the correction sticks.
    """
    personal = parser.is_personal_domain(domain)
    resolved = None if personal else index.resolve(domain)
    if resolved is not None and resolved.name.lower() == name.lower():
        return resolved

    company = index.by_name.get(name.lower())
    if company is None:
        owns_domain = not personal and domain not in index.by_domain
        company = Company(name=name, domain=domain if owns_domain else None)
        db.add(company)
        db.flush()
        index.by_name[name.lower()] = company
        if company.domain:
            index.by_domain[company.domain] = company

    if not personal and index.resolve(domain) is not company:
        alias = db.get(DomainAlias, domain)
        if alias is None:
            db.add(DomainAlias(domain=domain, company_id=company.id))
        else:
            alias.company_id = company.id
        db.flush()
        index.aliases[domain] = company
    return company


def import_rows(
    db: Session, rows: Iterable[schemas.PreviewRow], source: str
) -> schemas.ImportResult:
    """Create contacts (and companies) from edited preview rows. Skips duplicates."""
    index = CompanyIndex(db)
    rows = list(rows)
    emails = {r.email.strip().lower() for r in rows}
    existing = set(db.scalars(select(Contact.email).where(Contact.email.in_(emails))))
    created = 0
    skipped: list[schemas.SkippedRow] = []

    for row in rows:
        found = parser.extract(row.email)
        if len(found) != 1:
            skipped.append(schemas.SkippedRow(email=row.email, reason="invalid email"))
            continue
        email, domain = found[0].email, found[0].registrable
        if email in existing:
            skipped.append(schemas.SkippedRow(email=email, reason="already exists"))
            continue
        existing.add(email)

        name = (row.company_name or "").strip()
        company = _company_for_row(db, index, domain, name) if name else None
        db.add(Contact(
            email=email,
            first_name=_clean(row.first_name),
            last_name=_clean(row.last_name),
            title=_clean(row.title),
            company=company,
            source=source,
            status="new",
        ))
        created += 1

    db.commit()
    return schemas.ImportResult(created=created, skipped=len(skipped), skipped_rows=skipped)


def _clean(value: str | None) -> str | None:
    return (value.strip() or None) if value else None


# --- status ------------------------------------------------------------------


CONTACTED_EVENTS = ("sent", "replied", "bounced")


class AlreadyContacted(Exception):
    """Raised instead of ever queueing or sending a second email to someone."""

    def __init__(self, contact: Contact):
        super().__init__(f"{contact.email} has already been emailed. Each address gets one email, ever.")


def was_contacted(db: Session, contact: Contact) -> bool:
    """True once this address has been emailed (by the app, or marked sent/replied/bounced
    by hand). History lives in send_events, which survives status edits."""
    if contact.sent_at or contact.gmail_message_id:
        return True
    return bool(db.scalar(select(exists().where(
        SendEvent.contact_id == contact.id, SendEvent.event.in_(CONTACTED_EVENTS)
    ))))


def transition(
    db: Session, contact: Contact, status: str, event: str, detail: str | None = None
) -> None:
    """Change a contact's status and append the matching send_events row.
    The caller commits. Every queue/send path goes through here, so this is
    where a second email to the same person is refused."""
    if status in ("queued", "sent") and was_contacted(db, contact):
        raise AlreadyContacted(contact)
    now = datetime.now(UTC)
    contact.status = status
    contact.updated_at = now
    if status == "queued":
        contact.queued_at = now
        contact.error = None
    elif status == "sent":
        contact.sent_at = now
    elif status == "failed":
        contact.error = detail
    db.add(SendEvent(contact_id=contact.id, event=event, detail=detail))


def contact_counts_by_status(db: Session) -> dict[str, int]:
    rows = db.execute(select(Contact.status, func.count()).group_by(Contact.status)).all()
    return {status: count for status, count in rows}
