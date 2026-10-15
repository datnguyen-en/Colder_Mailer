from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends
from sqlalchemy import func, literal_column, select
from sqlalchemy.orm import Session, selectinload

from app import schemas, services
from app.db import get_db
from app.models import Company, Contact, SendEvent

router = APIRouter(tags=["stats"])

CONTACTED = ("sent", "replied", "bounced")


@router.get("/stats", response_model=schemas.Stats)
def stats(db: Session = Depends(get_db)):
    settings = services.get_settings(db)
    tz = settings.timezone
    today = datetime.now(ZoneInfo(tz)).date()
    week_start = today - timedelta(days=today.weekday())
    first_day = today - timedelta(days=29)

    # Sends per local calendar day, from the append-only event log.
    local_day = func.date(func.timezone(tz, SendEvent.created_at))
    per_day = dict(db.execute(
        select(local_day, func.count())
        .where(SendEvent.event == "sent", local_day >= first_day)
        .group_by(literal_column("1"))  # same expression twice would bind tz twice
    ).all())
    days = [first_day + timedelta(days=i) for i in range(30)]
    sends_per_day = [schemas.DayCount(date=d.isoformat(), sent=per_day.get(d, 0)) for d in days]
    sent_this_week = db.scalar(
        select(func.count()).where(SendEvent.event == "sent", local_day >= week_start)
    ) or 0

    status_counts = services.contact_counts_by_status(db)
    contacted = sum(status_counts.get(s, 0) for s in CONTACTED)
    replies = status_counts.get("replied", 0)

    stuck = db.scalar(select(func.count()).where(
        Contact.status == "sending",
        Contact.updated_at < datetime.now(UTC) - services.STUCK_AFTER,
    )) or 0

    events = db.scalars(
        select(SendEvent)
        .options(selectinload(SendEvent.contact).selectinload(Contact.company))
        .order_by(SendEvent.created_at.desc(), SendEvent.id.desc())
        .limit(20)
    ).all()

    warnings = []
    if not settings.gmail_refresh_token_encrypted:
        warnings.append("gmail_disconnected")
    if not settings.resume_storage_key:
        warnings.append("no_resume")
    if services.default_template(db) is None:
        warnings.append("no_default_template")
    if stuck:
        warnings.append("stuck_sending")

    return schemas.Stats(
        sent_today=per_day.get(today, 0),
        sent_this_week=sent_this_week,
        total_companies=db.scalar(select(func.count()).select_from(Company)) or 0,
        total_contacts=sum(status_counts.values()),
        replies=replies,
        reply_rate=round(replies / contacted, 4) if contacted else 0.0,
        status_counts=status_counts,
        sends_per_day=sends_per_day,
        recent_activity=[
            schemas.ActivityItem(
                id=e.id,
                contact_id=e.contact_id,
                email=e.contact.email,
                company_name=e.contact.company_name,
                event=e.event,
                detail=e.detail,
                created_at=e.created_at,
            )
            for e in events
        ],
        stuck_sending=stuck,
        warnings=warnings,
    )
