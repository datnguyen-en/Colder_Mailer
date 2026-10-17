from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

CONTACT_STATUSES = ("new", "queued", "sending", "sent", "replied", "bounced", "failed")
CONTACT_SOURCES = ("paste", "csv", "hunter", "manual")
SEND_EVENTS = ("queued", "sent", "failed", "replied", "bounced", "requeued", "unqueued")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention={
        "ix": "ix_%(column_0_label)s",
        "uq": "uq_%(table_name)s_%(column_0_name)s",
        "ck": "ck_%(table_name)s_%(constraint_name)s",
        "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
        "pk": "pk_%(table_name)s",
    })


def _created() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now())


class Company(Base):
    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    # Nullable: a company typed in for a personal-domain contact has no domain of its own.
    domain: Mapped[str | None] = mapped_column(String(255), unique=True)
    notes: Mapped[str | None] = mapped_column(Text)
    # Template for everyone at this company; None = the default template.
    template_id: Mapped[int | None] = mapped_column(
        ForeignKey("templates.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = _created()

    contacts: Mapped[list["Contact"]] = relationship(back_populates="company")
    template: Mapped["Template | None"] = relationship()
    aliases: Mapped[list["DomainAlias"]] = relationship(
        back_populates="company", cascade="all, delete-orphan"
    )


class DomainAlias(Base):
    __tablename__ = "domain_aliases"

    domain: Mapped[str] = mapped_column(String(255), primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"))

    company: Mapped[Company] = relationship(back_populates="aliases")


class Contact(Base):
    __tablename__ = "contacts"
    __table_args__ = (
        CheckConstraint("email = lower(email)", name="email_lowercase"),
        CheckConstraint(_in("status", CONTACT_STATUSES), name="status_valid"),
        CheckConstraint(_in("source", CONTACT_SOURCES), name="source_valid"),
        Index("ix_contacts_status_queued_at", "status", "queued_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True)
    first_name: Mapped[str | None] = mapped_column(String(100))
    last_name: Mapped[str | None] = mapped_column(String(100))
    title: Mapped[str | None] = mapped_column(String(200))
    company_id: Mapped[int | None] = mapped_column(
        ForeignKey("companies.id", ondelete="SET NULL"), index=True
    )
    source: Mapped[str] = mapped_column(String(20), default="paste")
    status: Mapped[str] = mapped_column(String(20), default="new", server_default="new")
    queued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    gmail_message_id: Mapped[str | None] = mapped_column(String(100))
    gmail_thread_id: Mapped[str | None] = mapped_column(String(100))
    error: Mapped[str | None] = mapped_column(Text)
    # This person's own template, overriding the company's; None = use the company's.
    template_id: Mapped[int | None] = mapped_column(
        ForeignKey("templates.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    company: Mapped[Company | None] = relationship(back_populates="contacts")
    template: Mapped["Template | None"] = relationship()
    events: Mapped[list["SendEvent"]] = relationship(
        back_populates="contact", cascade="all, delete-orphan", passive_deletes=True
    )

    @property
    def company_name(self) -> str | None:
        return self.company.name if self.company else None

    @property
    def company_template_id(self) -> int | None:
        return self.company.template_id if self.company else None


class Template(Base):
    __tablename__ = "templates"
    __table_args__ = (
        # At most one default template.
        Index("uq_templates_one_default", "is_default", unique=True,
              postgresql_where=text("is_default")),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    subject: Mapped[str] = mapped_column(String(300))
    body: Mapped[str] = mapped_column(Text)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class SendEvent(Base):
    """Append-only history of contact status changes."""

    __tablename__ = "send_events"
    __table_args__ = (
        CheckConstraint(_in("event", SEND_EVENTS), name="event_valid"),
        # One email per address, enforced by the database too.
        Index("uq_send_events_one_sent", "contact_id", unique=True,
              postgresql_where=text("event = 'sent'")),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    contact_id: Mapped[int] = mapped_column(
        ForeignKey("contacts.id", ondelete="CASCADE"), index=True
    )
    event: Mapped[str] = mapped_column(String(20))
    detail: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )

    contact: Mapped[Contact] = relationship(back_populates="events")


class AppSettings(Base):
    """The single settings row (id is always 1)."""

    __tablename__ = "settings"
    __table_args__ = (CheckConstraint("id = 1", name="single_row"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    sender_name: Mapped[str] = mapped_column(String(100), default="", server_default="")
    # Sanitized HTML, added after a "--" line at the end of every email.
    signature: Mapped[str] = mapped_column(Text, default="", server_default="")
    resume_storage_key: Mapped[str | None] = mapped_column(String(300))
    resume_filename_pattern: Mapped[str] = mapped_column(
        String(100), default="Eric_Resume_{company}.pdf",
        server_default="Eric_Resume_{company}.pdf",
    )
    daily_limit: Mapped[int] = mapped_column(Integer, default=25, server_default="25")
    send_window_start: Mapped[str] = mapped_column(String(5), default="09:00", server_default="09:00")
    send_window_end: Mapped[str] = mapped_column(String(5), default="16:00", server_default="16:00")
    send_days: Mapped[str] = mapped_column(String(40), default="Mon-Fri", server_default="Mon-Fri")
    timezone: Mapped[str] = mapped_column(
        String(64), default="America/New_York", server_default="America/New_York"
    )
    gmail_address: Mapped[str | None] = mapped_column(String(320))
    gmail_refresh_token_encrypted: Mapped[str | None] = mapped_column(Text)
