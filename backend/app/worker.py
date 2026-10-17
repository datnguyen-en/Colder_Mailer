"""Queue sender: `process_queue()` sends at most one email per run.

Runs every 15 minutes (EventBridge -> Lambda in prod, `python -m app.worker`
locally). Each address is emailed at most once, ever:
- a contact is claimed atomically (FOR UPDATE SKIP LOCKED), and never if it
  has already been emailed;
- if Gmail's answer is unclear, the contact stays in `sending` with a note and
  is never retried automatically.
"""

import argparse
import logging
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import exists, select, text
from sqlalchemy.orm import Session, selectinload

from app import crypto, services, templating
from app.db import get_sessionmaker
from app.gmail import (
    GmailAuthError,
    GmailClient,
    GmailError,
    GmailRejected,
    build_message,
    get_gmail,
)
from app.models import AppSettings, Contact, Template
from app.schemas import parse_send_days
from app.storage import get_storage

log = logging.getLogger("worker")

_NOT_CONTACTED = """
    c.sent_at IS NULL AND c.gmail_message_id IS NULL
    AND NOT EXISTS (
        SELECT 1 FROM send_events e
        WHERE e.contact_id = c.id AND e.event IN ('sent', 'replied', 'bounced')
    )
"""

CLAIM_NEXT = text(f"""
    UPDATE contacts SET status = 'sending', updated_at = now(), error = NULL
    WHERE id = (
        SELECT c.id FROM contacts c
        WHERE c.status = 'queued' AND {_NOT_CONTACTED}
        ORDER BY c.queued_at, c.id
        LIMIT 1
        FOR UPDATE SKIP LOCKED
    )
    RETURNING id
""")

CLAIM_ONE = text(f"""
    UPDATE contacts SET status = 'sending', updated_at = now(), error = NULL
    WHERE id = (
        SELECT c.id FROM contacts c
        WHERE c.id = :id AND c.status IN ('new', 'queued', 'failed') AND {_NOT_CONTACTED}
        FOR UPDATE SKIP LOCKED
    )
    RETURNING id
""")


class Paused(Exception):
    """Sending can't happen right now; nothing was claimed or changed."""


@dataclass
class Ready:
    """Everything a send needs, checked before any contact is claimed."""

    settings: AppSettings
    template: Template
    resume: bytes
    access_token: str


@dataclass
class RunResult:
    outcome: str  # sent | failed | unknown | skipped
    detail: str = ""
    contact_id: int | None = None


def prepare(db: Session, gmail: GmailClient) -> Ready:
    """Check Gmail, template and resume up front, so a missing piece pauses
    sending instead of failing every queued contact."""
    settings = services.get_settings(db)
    if not settings.gmail_refresh_token_encrypted:
        raise Paused("Gmail isn't connected")
    template = services.default_template(db)
    if template is None:
        raise Paused("No default template")
    if not settings.resume_storage_key:
        raise Paused("No resume uploaded")
    try:
        resume = get_storage().load(settings.resume_storage_key)
    except Exception as exc:
        raise Paused(f"Couldn't load the resume: {exc}") from exc
    try:
        token = gmail.access_token(crypto.decrypt(settings.gmail_refresh_token_encrypted))
    except (GmailAuthError, crypto.CryptoError) as exc:
        disconnect_gmail(db, settings)
        raise Paused(f"Gmail connection stopped working, reconnect it in Settings ({exc})") from exc
    except GmailError as exc:
        raise Paused(str(exc)) from exc
    return Ready(settings, template, resume, token)


def disconnect_gmail(db: Session, settings: AppSettings) -> None:
    """Drop a dead token but keep the address, so the UI can say 'Reconnect'."""
    settings.gmail_refresh_token_encrypted = None
    db.commit()


def deliver(db: Session, contact_id: int, ready: Ready, gmail: GmailClient) -> RunResult:
    """Send to a contact already claimed into `sending`. Commits the outcome."""
    contact = db.get(Contact, contact_id, options=[selectinload(Contact.company)],
                     populate_existing=True)
    assert contact is not None and contact.status == "sending"

    def fail(reason: str) -> RunResult:
        services.transition(db, contact, "failed", "failed", f"Not sent: {reason}")
        db.commit()
        return RunResult("failed", reason, contact.id)

    try:
        template = services.template_for(db, contact) or ready.template
        subject, body = templating.render(
            template, contact, contact.company, ready.settings.signature)
    except templating.TemplateError as exc:
        return fail(str(exc))
    if services.was_contacted(db, contact):  # the claim already checks; belt and braces
        return fail("this address has already been emailed")
    try:
        raw = build_message(
            sender_name=ready.settings.sender_name,
            sender_address=ready.settings.gmail_address or "",
            to=contact.email,
            subject=subject,
            body_html=body,
            attachment_name=templating.resume_filename(
                ready.settings.resume_filename_pattern, contact.company_name),
            attachment=ready.resume,
        )
    except Exception as exc:
        return fail(f"couldn't build the email ({exc})")

    try:
        sent = gmail.send(ready.access_token, raw)
    except GmailAuthError as exc:
        disconnect_gmail(db, ready.settings)
        return fail(f"Gmail connection stopped working ({exc})")
    except GmailRejected as exc:
        return fail(str(exc))
    except Exception as exc:  # GmailUnknown, or anything unexpected mid-send
        # It may have gone out. Stay in `sending` (shown as stuck); never retried.
        contact.error = (f"May have been sent: {exc}. Check Gmail's Sent folder "
                         "before requeueing.")
        db.commit()
        log.error("unclear send for contact %s: %s", contact.id, exc)
        return RunResult("unknown", contact.error, contact.id)

    services.transition(db, contact, "sent", "sent",
                        f"Gmail message {sent.message_id}")
    contact.gmail_message_id = sent.message_id
    contact.gmail_thread_id = sent.thread_id
    db.commit()
    return RunResult("sent", contact.email, contact.id)


def in_send_window(settings: AppSettings, now: datetime) -> bool:
    local = now.astimezone(ZoneInfo(settings.timezone))
    if local.weekday() not in parse_send_days(settings.send_days):
        return False
    return settings.send_window_start <= f"{local:%H:%M}" < settings.send_window_end


def daily_limit_reached(db: Session, settings: AppSettings, now: datetime) -> bool:
    return services.sent_on_day(db, settings.timezone, now) >= settings.daily_limit


def process_queue(gmail: GmailClient | None = None, now: datetime | None = None) -> RunResult:
    """Send the oldest queued email, if it's a good time. One per run."""
    gmail = gmail or get_gmail()
    now = now or datetime.now(UTC)
    with get_sessionmaker()() as db:
        settings = services.get_settings(db)
        if not in_send_window(settings, now):
            return RunResult("skipped", "outside the send window")
        if daily_limit_reached(db, settings, now):
            return RunResult("skipped", "daily limit reached")
        if not db.scalar(select(exists().where(Contact.status == "queued"))):
            return RunResult("skipped", "queue is empty")
        try:
            ready = prepare(db, gmail)
        except Paused as exc:
            return RunResult("skipped", f"paused: {exc}")

        contact_id = db.scalar(CLAIM_NEXT)
        db.commit()  # `sending` is durable before Gmail is ever called
        if contact_id is None:
            return RunResult("skipped", "queue is empty")
        return deliver(db, contact_id, ready, gmail)


def main() -> None:
    parser = argparse.ArgumentParser(description="Send queued cold emails, one per run.")
    parser.add_argument("--once", action="store_true", help="run once and exit (default)")
    parser.add_argument("--every", type=float, metavar="MINUTES",
                        help="keep running, one run every MINUTES (local testing)")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    while True:
        result = process_queue()
        log.info("%s: %s", result.outcome, result.detail)
        if not args.every:
            return
        time.sleep(args.every * 60)


if __name__ == "__main__":
    main()
