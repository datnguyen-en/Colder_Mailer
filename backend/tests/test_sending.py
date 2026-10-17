import threading
import time
from datetime import UTC, datetime
from email import message_from_bytes, policy
from urllib.parse import parse_qs, urlparse

import pytest
from sqlalchemy import select, text, update

from app import crypto, gmail, services, worker
from app.gmail import GmailAuthError, GmailRejected, GmailUnknown, SentMessage
from app.main import app
from app.models import AppSettings, Contact, SendEvent
from app.storage import get_storage

RESUME = b"%PDF-1.7\nfake resume"
# Wednesday 2026-10-14, 14:00 in New York: inside the default Mon-Fri 09:00-16:00 window.
WEDNESDAY_2PM = datetime(2026, 10, 14, 18, 0, tzinfo=UTC)


class FakeGmail:
    """Records what would have been sent. `fail_with` makes send() raise."""

    def __init__(self, fail_with: Exception | None = None, token_error: Exception | None = None,
                 delay: float = 0):
        self.sent: list[bytes] = []
        self.fail_with = fail_with
        self.token_error = token_error
        self.delay = delay
        self.lock = threading.Lock()

    def access_token(self, refresh_token: str) -> str:
        if self.token_error:
            raise self.token_error
        assert refresh_token == "refresh-token-123"
        return "access-token"

    def send(self, access_token: str, raw_message: bytes) -> SentMessage:
        time.sleep(self.delay)
        if self.fail_with:
            raise self.fail_with
        with self.lock:
            self.sent.append(raw_message)
            n = len(self.sent)
        return SentMessage(message_id=f"msg-{n}", thread_id=f"thread-{n}")

    def recipients(self) -> list[str]:
        return [message_from_bytes(m, policy=policy.default)["To"] for m in self.sent]


@pytest.fixture
def ready(client, db):
    """Gmail connected, resume uploaded, default template, everything 'new'."""
    db.execute(text("INSERT INTO settings (id) VALUES (1) ON CONFLICT DO NOTHING"))
    db.execute(update(AppSettings).values(
        sender_name="Eric Nguyen",
        gmail_address="eric@gmail.com",
        gmail_refresh_token_encrypted=crypto.encrypt("refresh-token-123"),
        resume_storage_key="resume/test.pdf",
    ))
    db.commit()
    get_storage().save("resume/test.pdf", RESUME)
    client.post("/templates", json={
        "name": "Main",
        "subject": "Internship at [Company]",
        "body": "Hi [Name],\n\nI'd love to intern at [Company].",
    })
    return client


def add(client, *emails):
    rows = client.post("/parse", json={"text": ", ".join(emails)}).json()
    client.post("/contacts/import", json={"rows": rows})
    found = client.get("/contacts", params={"page_size": 200}).json()["items"]
    by_email = {c["email"]: c["id"] for c in found}
    return [by_email[e] for e in emails]


def queue(client, *ids):
    res = client.post("/send/queue", json={"contact_ids": list(ids)})
    assert res.status_code == 200, res.text
    return res.json()


def events(db, contact_id):
    return db.scalars(select(SendEvent.event).where(SendEvent.contact_id == contact_id)
                      .order_by(SendEvent.id)).all()


def contact(db, contact_id) -> Contact:
    db.expire_all()
    return db.get(Contact, contact_id)


# --- the happy path ----------------------------------------------------------


def test_worker_sends_oldest_queued_email(ready, db):
    first, second = add(ready, "jane.doe@stripe.com", "bob.stone@ramp.com")
    queue(ready, first)
    queue(ready, second)
    fake = FakeGmail()

    result = worker.process_queue(fake, now=WEDNESDAY_2PM)

    assert (result.outcome, result.contact_id) == ("sent", first)
    msg = message_from_bytes(fake.sent[0], policy=policy.default)
    assert msg["To"] == "jane.doe@stripe.com"
    assert msg["From"] == "Eric Nguyen <eric@gmail.com>"
    assert msg["Subject"] == "Internship at Stripe"
    assert msg.get_body(("plain",)).get_content().startswith("Hi Jane,")
    [attachment] = list(msg.iter_attachments())
    assert attachment.get_filename() == "Eric_Resume_Stripe.pdf"
    assert attachment.get_content() == RESUME

    c = contact(db, first)
    assert (c.status, c.gmail_message_id, c.gmail_thread_id) == ("sent", "msg-1", "thread-1")
    assert c.sent_at is not None
    assert events(db, first) == ["queued", "sent"]
    assert contact(db, second).status == "queued"  # one per run


def test_email_is_formatted_with_plain_text_copy_and_signature(ready, db):
    ready.put("/settings", json={"signature": '<p><strong>Eric Nguyen</strong></p>'
                                              '<p><a href="https://linkedin.com/in/x">LinkedIn</a></p>'})
    tid = ready.get("/templates").json()[0]["id"]
    ready.put(f"/templates/{tid}", json={
        "name": "Main", "subject": "Internship at [Company]",
        "body": "<p>Hi [Name],</p><ul><li><p>Offer from <strong>Google</strong></p></li></ul>"})
    [cid] = add(ready, "jane.doe@stripe.com")
    queue(ready, cid)
    fake = FakeGmail()
    assert worker.process_queue(fake, now=WEDNESDAY_2PM).outcome == "sent"

    msg = message_from_bytes(fake.sent[0], policy=policy.default)
    html = msg.get_body(("html",)).get_content()
    assert "<p>Hi Jane,</p><ul><li>Offer from <strong>Google</strong></li></ul><p>--</p>" in html
    assert '<a href="https://linkedin.com/in/x"' in html
    assert msg.get_body(("plain",)).get_content().strip() == (
        "Hi Jane,\n\n- Offer from Google\n\n--\n\nEric Nguyen\n\nLinkedIn (https://linkedin.com/in/x)")
    assert [a.get_filename() for a in msg.iter_attachments()] == ["Eric_Resume_Stripe.pdf"]


def test_worker_uses_the_company_template(ready, db):
    special = ready.post("/templates", json={
        "name": "Special", "subject": "Special for [Company]", "body": "<p>Extra effort</p>"}).json()
    jane, bob = add(ready, "jane.doe@stripe.com", "bob.stone@ramp.com")
    stripe_id = next(c["id"] for c in ready.get("/companies").json() if c["name"] == "Stripe")
    ready.patch(f"/companies/{stripe_id}", json={"template_id": special["id"]})
    queue(ready, jane)
    queue(ready, bob)
    fake = FakeGmail()

    worker.process_queue(fake, now=WEDNESDAY_2PM)
    worker.process_queue(fake, now=WEDNESDAY_2PM)

    subjects = [message_from_bytes(raw, policy=policy.default)["Subject"] for raw in fake.sent]
    assert subjects == ["Special for Stripe", "Internship at Ramp"]  # Ramp keeps the default


def test_contact_without_name_gets_hi_there(ready, db):
    [cid] = add(ready, "zxqv@stripe.com")
    queue(ready, cid)
    fake = FakeGmail()
    assert worker.process_queue(fake, now=WEDNESDAY_2PM).outcome == "sent"
    body = message_from_bytes(fake.sent[0], policy=policy.default).get_body(("plain",)).get_content()
    assert body.startswith("Hi there,")


# --- when not to send ---------------------------------------------------------


@pytest.mark.parametrize("now,reason", [
    (datetime(2026, 10, 14, 12, 0, tzinfo=UTC), "outside the send window"),  # 08:00 NY
    (datetime(2026, 10, 14, 20, 0, tzinfo=UTC), "outside the send window"),  # 16:00 NY (end is exclusive)
    (datetime(2026, 10, 17, 18, 0, tzinfo=UTC), "outside the send window"),  # Saturday
])
def test_send_window(ready, db, now, reason):
    queue(ready, *add(ready, "jane.doe@stripe.com"))
    fake = FakeGmail()
    assert worker.process_queue(fake, now=now).detail == reason
    assert fake.sent == []


def test_send_window_uses_settings_timezone(ready, db):
    ready.put("/settings", json={"timezone": "Asia/Ho_Chi_Minh"})
    queue(ready, *add(ready, "jane.doe@stripe.com"))
    # 18:00 UTC is 01:00 next day in Vietnam: outside the window there.
    assert worker.process_queue(FakeGmail(), now=WEDNESDAY_2PM).outcome == "skipped"
    assert worker.process_queue(FakeGmail(), now=datetime(2026, 10, 14, 3, 0, tzinfo=UTC)).outcome == "sent"


def test_daily_limit(ready, db):
    ready.put("/settings", json={"daily_limit": 2})
    ids = add(ready, "a.one@stripe.com", "b.two@stripe.com", "c.three@stripe.com")
    queue(ready, *ids)
    fake = FakeGmail()
    now = datetime.now(UTC)
    with_window = {"send_days": "Mon-Sun", "send_window_start": "00:00", "send_window_end": "23:59"}
    ready.put("/settings", json=with_window)
    outcomes = [worker.process_queue(fake, now=now).outcome for _ in range(3)]
    assert outcomes == ["sent", "sent", "skipped"]
    assert len(fake.sent) == 2
    assert worker.process_queue(fake, now=now).detail == "daily limit reached"


def test_empty_queue(ready):
    assert worker.process_queue(FakeGmail(), now=WEDNESDAY_2PM).detail == "queue is empty"


@pytest.mark.parametrize("missing,reason", [
    ("gmail", "Gmail isn't connected"),
    ("resume", "No resume uploaded"),
])
def test_missing_setup_pauses_instead_of_failing(ready, db, missing, reason):
    [cid] = add(ready, "jane.doe@stripe.com")
    queue(ready, cid)
    column = {"gmail": "gmail_refresh_token_encrypted", "resume": "resume_storage_key"}[missing]
    db.execute(update(AppSettings).values({column: None}))
    db.commit()
    result = worker.process_queue(FakeGmail(), now=WEDNESDAY_2PM)
    assert result.detail == f"paused: {reason}"
    assert contact(db, cid).status == "queued"  # untouched, sends once fixed


# --- failures -----------------------------------------------------------------


def test_template_problem_fails_without_calling_gmail(ready, db):
    [cid] = add(ready, "emma.watson@gmail.com")  # personal: no [Company]
    queue(ready, cid)
    fake = FakeGmail()
    result = worker.process_queue(fake, now=WEDNESDAY_2PM)
    assert result.outcome == "failed"
    assert fake.sent == []
    c = contact(db, cid)
    assert c.status == "failed" and "[Company] has no value" in c.error
    assert events(db, cid) == ["queued", "failed"]


def test_gmail_rejection_fails_and_can_be_requeued(ready, db):
    [cid] = add(ready, "jane.doe@stripe.com")
    queue(ready, cid)
    result = worker.process_queue(FakeGmail(fail_with=GmailRejected("Gmail returned 400: bad")),
                                  now=WEDNESDAY_2PM)
    assert result.outcome == "failed"
    c = contact(db, cid)
    assert c.status == "failed" and c.error.startswith("Not sent: Gmail returned 400")
    # Not sent, so a manual retry is allowed, and it sends exactly once.
    assert ready.post(f"/contacts/{cid}/requeue").json()["status"] == "queued"
    fake = FakeGmail()
    assert worker.process_queue(fake, now=WEDNESDAY_2PM).outcome == "sent"
    assert events(db, cid) == ["queued", "failed", "requeued", "sent"]


def test_unclear_gmail_answer_is_never_retried(ready, db):
    [cid] = add(ready, "jane.doe@stripe.com")
    queue(ready, cid)
    result = worker.process_queue(FakeGmail(fail_with=GmailUnknown("ReadTimeout")), now=WEDNESDAY_2PM)
    assert result.outcome == "unknown"

    c = contact(db, cid)
    assert c.status == "sending" and c.error.startswith("May have been sent")
    item = ready.get("/contacts").json()["items"][0]
    assert item["stuck"] is True
    assert "stuck_sending" in ready.get("/stats").json()["warnings"]

    fake = FakeGmail()
    assert worker.process_queue(fake, now=WEDNESDAY_2PM).detail == "queue is empty"
    assert ready.post("/send/now", json={"contact_id": cid}).status_code == 409
    assert ready.post(f"/contacts/{cid}/requeue").status_code == 409  # needs confirmation
    assert fake.sent == []


def test_dead_gmail_token_pauses_and_asks_to_reconnect(ready, db):
    [cid] = add(ready, "jane.doe@stripe.com")
    queue(ready, cid)
    result = worker.process_queue(FakeGmail(token_error=GmailAuthError("invalid_grant")),
                                  now=WEDNESDAY_2PM)
    assert result.detail.startswith("paused: Gmail connection stopped working")
    assert contact(db, cid).status == "queued"
    status = ready.get("/gmail/status").json()
    assert (status["connected"], status["needs_reconnect"], status["address"]) == (
        False, True, "eric@gmail.com")
    assert "gmail_reconnect" in ready.get("/stats").json()["warnings"]


def test_gmail_auth_error_mid_send_fails_and_disconnects(ready, db):
    [cid] = add(ready, "jane.doe@stripe.com")
    queue(ready, cid)
    result = worker.process_queue(FakeGmail(fail_with=GmailAuthError("401")), now=WEDNESDAY_2PM)
    assert result.outcome == "failed"
    assert ready.get("/gmail/status").json()["needs_reconnect"] is True


# --- one email per address ------------------------------------------------------


def test_already_emailed_contact_is_never_claimed(ready, db):
    [cid] = add(ready, "jane.doe@stripe.com")
    queue(ready, cid)
    # Simulate a stale queue entry for someone already emailed (e.g. a bug elsewhere).
    db.add(SendEvent(contact_id=cid, event="sent"))
    db.commit()
    fake = FakeGmail()
    assert worker.process_queue(fake, now=WEDNESDAY_2PM).detail == "queue is empty"
    assert fake.sent == []


def test_concurrent_workers_never_claim_the_same_contact(ready, db):
    ids = add(ready, *[f"person.{n}@stripe.com" for n in range(8)])
    queue(ready, *ids)
    fake = FakeGmail(delay=0.05)  # slow sends so the runs overlap
    start = threading.Barrier(12)
    results = []

    def run():
        start.wait()
        results.append(worker.process_queue(fake, now=WEDNESDAY_2PM))

    threads = [threading.Thread(target=run) for _ in range(12)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    recipients = fake.recipients()
    assert len(recipients) == 8
    assert len(set(recipients)) == 8  # nobody got two
    assert sorted(r.outcome for r in results) == ["sent"] * 8 + ["skipped"] * 4
    sent_events = db.scalars(select(SendEvent.contact_id).where(SendEvent.event == "sent")).all()
    assert sorted(sent_events) == sorted(ids)


def test_two_workers_one_contact(ready, db):
    [cid] = add(ready, "jane.doe@stripe.com")
    queue(ready, cid)
    fake = FakeGmail(delay=0.1)
    start = threading.Barrier(2)
    outcomes = []

    def run():
        start.wait()
        outcomes.append(worker.process_queue(fake, now=WEDNESDAY_2PM).outcome)

    threads = [threading.Thread(target=run) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(outcomes) == ["sent", "skipped"]
    assert len(fake.sent) == 1


# --- endpoints ----------------------------------------------------------------


@pytest.fixture
def fake_gmail():
    fake = FakeGmail()
    app.dependency_overrides[gmail.get_gmail] = lambda: fake
    yield fake
    app.dependency_overrides.pop(gmail.get_gmail, None)


def test_send_now(ready, db, fake_gmail):
    [cid] = add(ready, "jane.doe@stripe.com")
    res = ready.post("/send/now", json={"contact_id": cid})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["outcome"] == "sent"
    assert body["contact"]["status"] == "sent"
    assert body["contact"]["gmail_thread_id"] == "thread-1"
    assert fake_gmail.recipients() == ["jane.doe@stripe.com"]

    again = ready.post("/send/now", json={"contact_id": cid})
    assert again.status_code == 409 and "one email, ever" in again.json()["detail"]
    assert len(fake_gmail.sent) == 1


def test_send_now_respects_daily_limit_and_setup(ready, db, fake_gmail):
    ready.put("/settings", json={"daily_limit": 1})
    a, b = add(ready, "a.one@stripe.com", "b.two@stripe.com")
    assert ready.post("/send/now", json={"contact_id": a}).json()["outcome"] == "sent"
    res = ready.post("/send/now", json={"contact_id": b})
    assert res.status_code == 409 and "Daily limit" in res.json()["detail"]

    ready.put("/settings", json={"daily_limit": 5})
    db.execute(update(AppSettings).values(gmail_refresh_token_encrypted=None))
    db.commit()
    res = ready.post("/send/now", json={"contact_id": b})
    assert res.status_code == 409 and "Gmail isn't connected" in res.json()["detail"]


def test_queue_endpoint_skips_contacted(ready, db, fake_gmail):
    a, b, c = add(ready, "a.one@stripe.com", "b.two@stripe.com", "c.three@stripe.com")
    ready.post("/send/now", json={"contact_id": a})
    ready.patch(f"/contacts/{c}", json={"status": "failed"})
    result = queue(ready, a, b, c)
    assert result["queued"] == 2
    assert [(s["email"], s["reason"]) for s in result["skipped"]] == [("a.one@stripe.com", "already sent")]
    assert events(db, c)[-1] == "requeued"


# --- Gmail OAuth --------------------------------------------------------------


def test_connect_and_callback_store_encrypted_token(client, db, monkeypatch):
    url = client.get("/gmail/connect").json()["url"]
    query = parse_qs(urlparse(url).query)
    assert query["access_type"] == ["offline"]
    assert "https://www.googleapis.com/auth/gmail.send" in query["scope"][0]

    monkeypatch.setattr(gmail, "exchange_code", lambda code: ("refresh-xyz", "me@gmail.com"))
    res = client.get("/gmail/callback", params={"state": query["state"][0], "code": "abc"},
                     follow_redirects=False)
    assert res.status_code == 303
    assert res.headers["location"].endswith("/settings?gmail=connected")

    settings = services.get_settings(db)
    db.refresh(settings)
    assert settings.gmail_address == "me@gmail.com"
    assert "refresh-xyz" not in settings.gmail_refresh_token_encrypted
    assert crypto.decrypt(settings.gmail_refresh_token_encrypted) == "refresh-xyz"
    assert client.get("/gmail/status").json()["connected"] is True


def test_callback_rejects_forged_state(client, db, monkeypatch):
    monkeypatch.setattr(gmail, "exchange_code", lambda code: pytest.fail("must not exchange"))
    res = client.get("/gmail/callback", params={"state": "forged", "code": "abc"},
                     follow_redirects=False)
    assert "gmail=error" in res.headers["location"]
    assert services.get_settings(db).gmail_refresh_token_encrypted is None
