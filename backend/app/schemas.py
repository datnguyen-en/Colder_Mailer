import re
from datetime import datetime
from typing import Literal
from zoneinfo import available_timezones

from pydantic import BaseModel, ConfigDict, Field, field_validator

ContactStatus = Literal["new", "queued", "sending", "sent", "replied", "bounced", "failed"]
ContactSource = Literal["paste", "csv", "hunter", "manual"]

DAY_NAMES = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


def parse_send_days(spec: str) -> set[int]:
    """`Mon-Fri` or `Mon,Wed,Fri` -> weekday numbers (Mon=0). ValueError if invalid."""
    days: set[int] = set()
    for part in spec.replace(" ", "").lower().split(","):
        start, _, end = part.partition("-")
        try:
            a = DAY_NAMES.index(start[:3])
            b = DAY_NAMES.index(end[:3]) if end else a
        except ValueError:
            raise ValueError(f"Unknown day in {spec!r}; use e.g. Mon-Fri or Mon,Wed,Fri") from None
        if b < a:
            raise ValueError(f"Day range {part!r} runs backwards")
        days.update(range(a, b + 1))
    return days


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --- parse / import ----------------------------------------------------------


class ParseRequest(BaseModel):
    text: str = Field(max_length=500_000)
    format: Literal["text", "csv"] = "text"


class PreviewRow(BaseModel):
    email: str = Field(max_length=320)
    first_name: str | None = Field(default=None, max_length=100)
    last_name: str | None = Field(default=None, max_length=100)
    title: str | None = Field(default=None, max_length=200)
    domain: str | None = Field(default=None, max_length=255)
    company_name: str | None = Field(default=None, max_length=200)
    flags: list[str] = []


class ImportRequest(BaseModel):
    rows: list[PreviewRow] = Field(max_length=5000)
    source: Literal["paste", "csv", "manual"] = "paste"


class SkippedRow(BaseModel):
    email: str
    reason: str


class ImportResult(BaseModel):
    created: int
    skipped: int
    skipped_rows: list[SkippedRow]


# --- contacts ----------------------------------------------------------------


class ContactOut(ORM):
    id: int
    email: str
    first_name: str | None
    last_name: str | None
    title: str | None
    company_id: int | None
    company_name: str | None
    source: str
    status: ContactStatus
    queued_at: datetime | None
    sent_at: datetime | None
    gmail_message_id: str | None
    gmail_thread_id: str | None
    error: str | None
    stuck: bool = False
    created_at: datetime
    updated_at: datetime


class ContactPage(BaseModel):
    items: list[ContactOut]
    total: int
    page: int
    page_size: int


class ContactUpdate(BaseModel):
    first_name: str | None = Field(default=None, max_length=100)
    last_name: str | None = Field(default=None, max_length=100)
    title: str | None = Field(default=None, max_length=200)
    company_id: int | None = None
    # Manual status changes; "new" and "sending" are owned by the app.
    status: Literal["queued", "sent", "replied", "bounced", "failed"] | None = None


class EmailPreview(BaseModel):
    subject: str
    body: str
    attachment_name: str
    to: str | None = None
    problems: list[str] = []


# --- companies ---------------------------------------------------------------


class CompanyOut(ORM):
    id: int
    name: str
    domain: str | None
    notes: str | None
    aliases: list[str] = []
    contact_count: int = 0
    status_counts: dict[str, int] = {}
    last_contacted_at: datetime | None = None
    created_at: datetime


class CompanyUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    notes: str | None = None


# --- templates ---------------------------------------------------------------


class TemplateIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    subject: str = Field(min_length=1, max_length=300)
    body: str = Field(min_length=1, max_length=20_000)
    is_default: bool = False


class TemplateOut(ORM):
    id: int
    name: str
    subject: str
    body: str
    is_default: bool
    updated_at: datetime


class TemplatePreviewRequest(BaseModel):
    subject: str = Field(max_length=300)
    body: str = Field(max_length=20_000)
    contact_id: int


# --- settings ----------------------------------------------------------------

_TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
_PATTERN_RE = re.compile(r"^[A-Za-z0-9._ -]*(\{company\}[A-Za-z0-9._ -]*)?$")


class SettingsOut(ORM):
    sender_name: str
    resume_uploaded: bool
    resume_filename_pattern: str
    daily_limit: int
    send_window_start: str
    send_window_end: str
    send_days: str
    timezone: str
    gmail_address: str | None
    gmail_connected: bool


class SettingsUpdate(BaseModel):
    sender_name: str | None = Field(default=None, max_length=100)
    resume_filename_pattern: str | None = Field(default=None, min_length=5, max_length=100)
    daily_limit: int | None = Field(default=None, ge=1, le=100)
    send_window_start: str | None = None
    send_window_end: str | None = None
    send_days: str | None = None
    timezone: str | None = None

    @field_validator("send_window_start", "send_window_end")
    @classmethod
    def _time(cls, v: str | None) -> str | None:
        if v is not None and not _TIME_RE.match(v):
            raise ValueError("Use 24-hour HH:MM")
        return v

    @field_validator("send_days")
    @classmethod
    def _days(cls, v: str | None) -> str | None:
        if v is not None:
            parse_send_days(v)
        return v

    @field_validator("timezone")
    @classmethod
    def _tz(cls, v: str | None) -> str | None:
        if v is not None and v not in available_timezones():
            raise ValueError(f"Unknown timezone {v!r}")
        return v

    @field_validator("resume_filename_pattern")
    @classmethod
    def _pattern(cls, v: str | None) -> str | None:
        if v is not None:
            if not _PATTERN_RE.match(v):
                raise ValueError("Letters, digits, . _ - and one {company} only")
            if not v.lower().endswith(".pdf"):
                raise ValueError("Must end with .pdf")
        return v



# --- stats -------------------------------------------------------------------


class DayCount(BaseModel):
    date: str
    sent: int


class ActivityItem(BaseModel):
    id: int
    contact_id: int
    email: str
    company_name: str | None
    event: str
    detail: str | None
    created_at: datetime


class Stats(BaseModel):
    sent_today: int
    sent_this_week: int
    total_companies: int
    total_contacts: int
    replies: int
    reply_rate: float
    status_counts: dict[str, int]
    sends_per_day: list[DayCount]
    recent_activity: list[ActivityItem]
    stuck_sending: int
    warnings: list[str]
