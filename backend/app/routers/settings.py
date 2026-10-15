from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app import schemas, services
from app.db import get_db
from app.models import AppSettings
from app.storage import get_storage

router = APIRouter(tags=["settings"])

MAX_RESUME_BYTES = 5 * 1024 * 1024


def settings_out(settings: AppSettings) -> schemas.SettingsOut:
    return schemas.SettingsOut(
        sender_name=settings.sender_name,
        resume_uploaded=bool(settings.resume_storage_key),
        resume_filename_pattern=settings.resume_filename_pattern,
        daily_limit=settings.daily_limit,
        send_window_start=settings.send_window_start,
        send_window_end=settings.send_window_end,
        send_days=settings.send_days,
        timezone=settings.timezone,
        gmail_address=settings.gmail_address,
        gmail_connected=bool(settings.gmail_refresh_token_encrypted),
    )


@router.get("/settings", response_model=schemas.SettingsOut)
def get_settings(db: Session = Depends(get_db)):
    return settings_out(services.get_settings(db))


@router.put("/settings", response_model=schemas.SettingsOut)
def update_settings(req: schemas.SettingsUpdate, db: Session = Depends(get_db)):
    settings = services.get_settings(db)
    changes = req.model_dump(exclude_unset=True, exclude_none=True)
    start = changes.get("send_window_start", settings.send_window_start)
    end = changes.get("send_window_end", settings.send_window_end)
    if start >= end:
        raise HTTPException(422, "Send window start must be before its end")
    for field, value in changes.items():
        setattr(settings, field, value.strip() if isinstance(value, str) else value)
    db.commit()
    return settings_out(settings)


@router.post("/resume", response_model=schemas.SettingsOut)
def upload_resume(file: UploadFile, db: Session = Depends(get_db)):
    data = file.file.read(MAX_RESUME_BYTES + 1)
    if len(data) > MAX_RESUME_BYTES:
        raise HTTPException(413, "Resume must be 5 MB or smaller")
    if not data.startswith(b"%PDF-"):
        raise HTTPException(415, "Resume must be a PDF")

    settings = services.get_settings(db)
    storage = get_storage()
    old_key = settings.resume_storage_key
    key = f"resume/resume-{datetime.now(UTC):%Y%m%d%H%M%S}.pdf"
    storage.save(key, data)
    settings.resume_storage_key = key
    db.commit()
    if old_key and old_key != key:
        storage.delete(old_key)
    return settings_out(settings)
