from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import schemas, services, worker
from app.db import get_db
from app.gmail import GmailClient, get_gmail
from app.models import Contact
from app.routers.contacts import contact_out, get_contact

router = APIRouter(prefix="/send", tags=["send"])


class SendNowRequest(BaseModel):
    contact_id: int


class SendNowResult(BaseModel):
    outcome: str  # sent | failed | unknown
    detail: str
    contact: schemas.ContactOut


class QueueRequest(BaseModel):
    contact_ids: list[int] = Field(min_length=1, max_length=1000)


class QueueResult(BaseModel):
    queued: int
    skipped: list[schemas.SkippedRow]


@router.post("/now", response_model=SendNowResult)
def send_now(req: SendNowRequest, db: Session = Depends(get_db),
             gmail: GmailClient = Depends(get_gmail)):
    """Send one email immediately (ignores the send window, not the daily limit)."""
    contact = get_contact(db, req.contact_id)
    if services.was_contacted(db, contact):
        raise services.AlreadyContacted(contact)
    if contact.status not in ("new", "queued", "failed"):
        raise HTTPException(409, f"Can't send to a contact that is {contact.status}")
    settings = services.get_settings(db)
    if worker.daily_limit_reached(db, settings, datetime.now(UTC)):
        raise HTTPException(409, f"Daily limit of {settings.daily_limit} reached. Try tomorrow or raise it in Settings.")
    try:
        ready = worker.prepare(db, gmail)
    except worker.Paused as exc:
        raise HTTPException(409, str(exc)) from None

    claimed = db.scalar(worker.CLAIM_ONE, {"id": contact.id})
    db.commit()  # `sending` is durable before Gmail is called
    if claimed is None:
        raise HTTPException(409, "This contact is already being sent")
    result = worker.deliver(db, claimed, ready, gmail)
    return SendNowResult(outcome=result.outcome, detail=result.detail,
                         contact=contact_out(get_contact(db, claimed)))


@router.post("/queue", response_model=QueueResult)
def queue(req: QueueRequest, db: Session = Depends(get_db)):
    """Queue contacts for the throttled sender. Anyone already emailed is skipped."""
    contacts = db.scalars(select(Contact).where(Contact.id.in_(req.contact_ids))).all()
    queued, skipped = 0, []
    for contact in contacts:
        if contact.status not in ("new", "failed"):
            skipped.append(schemas.SkippedRow(email=contact.email, reason=f"already {contact.status}"))
            continue
        event = "requeued" if contact.status == "failed" else "queued"
        try:
            services.transition(db, contact, "queued", event)
        except services.AlreadyContacted:
            skipped.append(schemas.SkippedRow(email=contact.email, reason="already emailed"))
            continue
        queued += 1
    db.commit()
    return QueueResult(queued=queued, skipped=skipped)
