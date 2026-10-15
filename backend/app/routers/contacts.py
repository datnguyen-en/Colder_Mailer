from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app import schemas, services
from app.db import get_db
from app.models import Company, Contact

router = APIRouter(prefix="/contacts", tags=["contacts"])


def contact_out(contact: Contact) -> schemas.ContactOut:
    out = schemas.ContactOut.model_validate(contact)
    out.stuck = services.is_stuck(contact)
    return out


def get_contact(db: Session, contact_id: int) -> Contact:
    contact = db.get(Contact, contact_id, options=[selectinload(Contact.company)])
    if contact is None:
        raise HTTPException(404, "Contact not found")
    return contact


def _ensure_not_in_flight(contact: Contact) -> None:
    if contact.status == "sending" and not services.is_stuck(contact):
        raise HTTPException(409, "This contact is being sent right now")


@router.post("/import", response_model=schemas.ImportResult)
def import_contacts(req: schemas.ImportRequest, db: Session = Depends(get_db)):
    return services.import_rows(db, req.rows, req.source)


@router.get("", response_model=schemas.ContactPage)
def list_contacts(
    status: schemas.ContactStatus | None = None,
    company_id: int | None = None,
    q: str | None = Query(default=None, max_length=200),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    query = select(Contact).outerjoin(Company)
    if status:
        query = query.where(Contact.status == status)
    if company_id is not None:
        query = query.where(Contact.company_id == company_id)
    if q:
        like = f"%{q.strip()}%"
        query = query.where(or_(
            Contact.email.ilike(like),
            Contact.first_name.ilike(like),
            Contact.last_name.ilike(like),
            Contact.title.ilike(like),
            Company.name.ilike(like),
        ))
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    contacts = db.scalars(
        query.options(selectinload(Contact.company))
        .order_by(Contact.created_at.desc(), Contact.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return schemas.ContactPage(
        items=[contact_out(c) for c in contacts], total=total or 0, page=page, page_size=page_size
    )


@router.patch("/{contact_id}", response_model=schemas.ContactOut)
def update_contact(contact_id: int, req: schemas.ContactUpdate, db: Session = Depends(get_db)):
    contact = get_contact(db, contact_id)
    changes = req.model_dump(exclude_unset=True)
    status = changes.pop("status", None)

    if "company_id" in changes and changes["company_id"] is not None:
        if db.get(Company, changes["company_id"]) is None:
            raise HTTPException(422, "Company not found")
    for field, value in changes.items():
        setattr(contact, field, (value.strip() or None) if isinstance(value, str) else value)

    if status and status != contact.status:
        _ensure_not_in_flight(contact)
        if status == "queued" and contact.status not in ("new", "failed"):
            raise HTTPException(409, f"Can't queue a contact that is {contact.status}")
        event = "requeued" if status == "queued" and contact.status == "failed" else status
        services.transition(db, contact, status, event, "manual status change")

    db.commit()
    db.refresh(contact)
    return contact_out(contact)


@router.delete("/{contact_id}", status_code=204)
def delete_contact(contact_id: int, db: Session = Depends(get_db)):
    contact = get_contact(db, contact_id)
    _ensure_not_in_flight(contact)
    if services.was_contacted(db, contact):
        # Keeping the row is what stops a re-import from emailing them again.
        raise HTTPException(409, f"{contact.email} has been emailed, so it's kept to prevent a second email")
    db.delete(contact)
    db.commit()
    return Response(status_code=204)


@router.post("/{contact_id}/mark-replied", response_model=schemas.ContactOut)
def mark_replied(contact_id: int, db: Session = Depends(get_db)):
    contact = get_contact(db, contact_id)
    if contact.status != "replied":
        _ensure_not_in_flight(contact)
        services.transition(db, contact, "replied", "replied")
        db.commit()
    return contact_out(contact)


@router.post("/{contact_id}/requeue", response_model=schemas.ContactOut)
def requeue(contact_id: int, confirm_not_sent: bool = False, db: Session = Depends(get_db)):
    """Manual retry for a failed or stuck send. Never automatic.

    A stuck send may have reached Gmail, so it needs `confirm_not_sent=true`:
    you checked Gmail's Sent folder and it isn't there."""
    contact = get_contact(db, contact_id)
    if contact.status not in ("failed", "sending"):
        raise HTTPException(409, f"Only failed or stuck contacts can be requeued (this one is {contact.status})")
    _ensure_not_in_flight(contact)
    if contact.status == "sending" and not confirm_not_sent:
        raise HTTPException(409, "This send may have gone out. Check Gmail's Sent folder, then confirm.")
    previous = contact.status
    services.transition(db, contact, "queued", "requeued", f"requeued from {previous}")
    db.commit()
    return contact_out(contact)


@router.post("/{contact_id}/unqueue", response_model=schemas.ContactOut)
def unqueue(contact_id: int, db: Session = Depends(get_db)):
    """Take a queued contact back out of the queue before it is sent."""
    contact = get_contact(db, contact_id)
    if contact.status != "queued":
        raise HTTPException(409, f"Only queued contacts can be unqueued (this one is {contact.status})")
    services.transition(db, contact, "new", "unqueued")
    contact.queued_at = None
    db.commit()
    return contact_out(contact)


@router.get("/{contact_id}/preview", response_model=schemas.EmailPreview)
def preview(contact_id: int, db: Session = Depends(get_db)):
    contact = get_contact(db, contact_id)
    template = services.default_template(db)
    if template is None:
        raise HTTPException(409, "No default template yet. Create one on the Templates page.")
    return services.preview_email(db, template, contact)
