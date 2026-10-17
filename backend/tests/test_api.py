from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from app.models import Company, Contact, DomainAlias, SendEvent

TEMPLATE = {
    "name": "Main",
    "subject": "Software internship at [Company]",
    "body": "Hi [Name],\n\nI'd love to intern at [Company].\n\nEric",
}


def parse(client, text, **extra):
    res = client.post("/parse", json={"text": text, **extra})
    assert res.status_code == 200, res.text
    return res.json()


def import_rows(client, rows, source="paste"):
    res = client.post("/contacts/import", json={"rows": rows, "source": source})
    assert res.status_code == 200, res.text
    return res.json()


def contacts(client, **params):
    res = client.get("/contacts", params=params)
    assert res.status_code == 200, res.text
    return res.json()


def add_contact(client, text):
    import_rows(client, parse(client, text))
    return contacts(client, q=text.split("@")[0])["items"][0]


# --- parse -> import -> preview --------------------------------------------


def test_parse_import_preview_flow(client, db):
    rows = parse(client, "Jane Doe <jane.doe@stripe.com>, careers@stripe.com\njsmith@ramp.com")
    assert [(r["email"], r["first_name"], r["company_name"], r["flags"]) for r in rows] == [
        ("jane.doe@stripe.com", "Jane", "Stripe", []),
        ("careers@stripe.com", None, "Stripe", ["generic_inbox", "needs_name"]),
        ("jsmith@ramp.com", None, "Ramp", ["needs_name"]),
    ]
    assert db.scalar(select(Contact).limit(1)) is None  # parse writes nothing

    rows[2]["first_name"] = "John"  # fixed in the preview table
    result = import_rows(client, [rows[0], rows[2]])
    assert result == {"created": 2, "skipped": 0, "skipped_rows": []}

    assert client.post("/templates", json=TEMPLATE).status_code == 201
    jane = contacts(client, q="jane")["items"][0]
    assert jane["status"] == "new" and jane["company_name"] == "Stripe"

    preview = client.get(f"/contacts/{jane['id']}/preview").json()
    assert preview["subject"] == "Software internship at Stripe"
    assert preview["body"].startswith("<p>Hi Jane,</p>")
    assert preview["attachment_name"] == "Eric_Resume_Stripe.pdf"
    assert preview["to"] == "jane.doe@stripe.com"
    assert preview["problems"] == ["No resume uploaded"]


def test_preview_without_template_is_409(client):
    jane = add_contact(client, "jane.doe@stripe.com")
    assert client.get(f"/contacts/{jane['id']}/preview").status_code == 409


def test_preview_without_name_uses_there(client):
    client.post("/templates", json=TEMPLATE)
    c = add_contact(client, "zxqv@ramp.com")  # no name
    preview = client.get(f"/contacts/{c['id']}/preview").json()
    assert preview["body"].startswith("<p>Hi there,</p>")
    assert preview["problems"] == ["No resume uploaded"]


def test_preview_lists_template_problems(client):
    client.post("/templates", json=TEMPLATE)
    c = add_contact(client, "emma.watson@gmail.com")  # personal: no company
    preview = client.get(f"/contacts/{c['id']}/preview").json()
    assert "[Company] has no value for this contact" in preview["problems"]


def test_csv_parse_and_import_keeps_title(client):
    csv_text = "First Name,Last Name,Title,Company,Email\nJane,Doe,Recruiter,Stripe,jane@stripe.com\n"
    rows = parse(client, csv_text, format="csv")
    import_rows(client, rows, source="csv")
    c = contacts(client)["items"][0]
    assert (c["first_name"], c["title"], c["source"]) == ("Jane", "Recruiter", "csv")


def test_import_skips_duplicates_and_flags_them(client, db):
    import_rows(client, parse(client, "jane.doe@stripe.com"))
    rows = parse(client, "jane.doe@stripe.com, bob.stone@stripe.com, bob.stone@stripe.com")
    assert rows[0]["flags"] == ["already_imported"]
    result = import_rows(client, rows + [{"email": "BOB.STONE@stripe.com"}, {"email": "nope"}])
    assert result["created"] == 1
    assert [(s["email"], s["reason"]) for s in result["skipped_rows"]] == [
        ("jane.doe@stripe.com", "already exists"),
        ("bob.stone@stripe.com", "already exists"),
        ("nope", "invalid email"),
    ]

    db.execute(update(Contact).where(Contact.email == "jane.doe@stripe.com").values(status="sent"))
    db.commit()
    assert parse(client, "jane.doe@stripe.com")[0]["flags"] == ["already_contacted"]


def test_personal_email_imports_without_company(client, db):
    import_rows(client, parse(client, "emma.watson@gmail.com"))
    assert contacts(client)["items"][0]["company_id"] is None
    assert db.scalar(select(Company)) is None


# --- company mapping memory -------------------------------------------------


def test_edited_company_name_creates_company_with_domain(client, db):
    rows = parse(client, "sheryl.sandberg@fb.com")
    assert rows[0]["company_name"] == "Fb"
    rows[0]["company_name"] = "Meta"
    import_rows(client, rows)
    meta = db.scalar(select(Company))
    assert (meta.name, meta.domain) == ("Meta", "fb.com")
    assert parse(client, "mark.lee@fb.com")[0]["company_name"] == "Meta"


def test_new_domain_for_existing_company_is_remembered_as_alias(client, db):
    rows = parse(client, "sheryl.sandberg@fb.com")
    rows[0]["company_name"] = "Meta"
    import_rows(client, rows)

    rows = parse(client, "mark.lee@meta.com")
    rows[0]["company_name"] = "meta"  # matched case-insensitively
    import_rows(client, rows)

    assert db.scalars(select(Company)).all().__len__() == 1
    assert db.get(DomainAlias, "meta.com").company.name == "Meta"
    assert parse(client, "alex@meta.com")[0]["company_name"] == "Meta"


def test_renaming_owned_domain_adds_alias_to_new_company(client, db):
    import_rows(client, parse(client, "jane.doe@stripe.com"))
    rows = parse(client, "bob.stone@stripe.com")
    assert rows[0]["company_name"] == "Stripe"
    rows[0]["company_name"] = "Stripe Inc"
    import_rows(client, rows)

    new = db.scalar(select(Company).where(Company.name == "Stripe Inc"))
    assert new.domain is None
    assert db.get(DomainAlias, "stripe.com").company_id == new.id
    assert parse(client, "tom@stripe.com")[0]["company_name"] == "Stripe Inc"


def test_country_domain_matches_existing_company(client, db):
    import_rows(client, parse(client, "jane.doe@jpmorgan.com"))
    client.patch(f"/companies/{db.scalar(select(Company.id))}", json={"name": "JPMorgan Chase"})
    rows = parse(client, "ana.lopez@jpmorgan.co.uk")
    assert rows[0]["company_name"] == "JPMorgan Chase"
    import_rows(client, rows)
    assert len(db.scalars(select(Company)).all()) == 1


# --- contacts ---------------------------------------------------------------


def test_list_filters_search_and_pages(client):
    import_rows(client, parse(client, "jane.doe@stripe.com, bob.stone@stripe.com, tom.ford@ramp.com"))
    assert contacts(client)["total"] == 3
    assert {c["email"] for c in contacts(client, q="stripe")["items"]} == {
        "jane.doe@stripe.com", "bob.stone@stripe.com"}
    assert contacts(client, q="FORD")["items"][0]["email"] == "tom.ford@ramp.com"
    page = contacts(client, page=2, page_size=2)
    assert (page["total"], len(page["items"])) == (3, 1)
    ramp_id = contacts(client, q="ramp")["items"][0]["company_id"]
    assert contacts(client, company_id=ramp_id)["total"] == 1
    assert contacts(client, status="sent")["total"] == 0


def test_patch_edits_fields_and_logs_status_change(client, db):
    c = add_contact(client, "jsmith@ramp.com")
    res = client.patch(f"/contacts/{c['id']}", json={"first_name": " John ", "title": "EM"})
    assert (res.json()["first_name"], res.json()["title"]) == ("John", "EM")

    res = client.patch(f"/contacts/{c['id']}", json={"status": "sent"})
    assert res.json()["status"] == "sent" and res.json()["sent_at"]
    events = db.scalars(select(SendEvent.event)).all()
    assert events == ["sent"]

    res = client.patch(f"/contacts/{c['id']}", json={"status": "queued"})
    assert res.status_code == 409  # would send twice
    assert client.patch(f"/contacts/{c['id']}", json={"status": "new"}).status_code == 422


def test_mark_replied_and_requeue_rules(client, db):
    c = add_contact(client, "jane.doe@stripe.com")
    assert client.post(f"/contacts/{c['id']}/requeue").status_code == 409  # new, not failed

    client.patch(f"/contacts/{c['id']}", json={"status": "failed"})
    res = client.post(f"/contacts/{c['id']}/requeue")
    assert res.json()["status"] == "queued" and res.json()["error"] is None

    res = client.post(f"/contacts/{c['id']}/mark-replied")
    assert res.json()["status"] == "replied"
    assert db.scalars(select(SendEvent.event).order_by(SendEvent.id)).all() == [
        "failed", "requeued", "replied"]


def test_stuck_sending_can_be_requeued_but_fresh_one_cannot(client, db):
    c = add_contact(client, "jane.doe@stripe.com")
    db.execute(update(Contact).values(status="sending", updated_at=datetime.now(UTC)))
    db.commit()
    assert client.post(f"/contacts/{c['id']}/requeue").status_code == 409
    assert client.delete(f"/contacts/{c['id']}").status_code == 409

    db.execute(update(Contact).values(updated_at=datetime.now(UTC) - timedelta(minutes=31)))
    db.commit()
    assert contacts(client)["items"][0]["stuck"] is True
    # It may have gone out: requeue needs explicit confirmation after checking Gmail.
    assert client.post(f"/contacts/{c['id']}/requeue").status_code == 409
    res = client.post(f"/contacts/{c['id']}/requeue", params={"confirm_not_sent": True})
    assert res.json()["status"] == "queued"


def test_delete_contact(client, db):
    c = add_contact(client, "jane.doe@stripe.com")
    client.patch(f"/contacts/{c['id']}", json={"status": "queued"})
    assert client.delete(f"/contacts/{c['id']}").status_code == 204
    assert client.delete(f"/contacts/{c['id']}").status_code == 404
    assert db.scalar(select(SendEvent)) is None


# --- one email per address, ever ---------------------------------------------


def test_emailed_contact_cannot_be_deleted_so_reimport_is_skipped(client):
    c = add_contact(client, "jane.doe@stripe.com")
    client.patch(f"/contacts/{c['id']}", json={"status": "sent"})
    res = client.delete(f"/contacts/{c['id']}")
    assert res.status_code == 409 and "second email" in res.json()["detail"]
    assert import_rows(client, parse(client, "Jane.Doe@stripe.com"))["created"] == 0


@pytest.mark.parametrize("contacted", ["sent", "replied", "bounced"])
def test_contacted_address_can_never_be_queued_again(client, contacted):
    c = add_contact(client, "jane.doe@stripe.com")
    url = f"/contacts/{c['id']}"
    client.patch(url, json={"status": contacted})
    # Every route back into the queue is refused, even via a manual "failed".
    client.patch(url, json={"status": "failed"})
    for attempt in (
        lambda: client.patch(url, json={"status": "queued"}),
        lambda: client.post(f"{url}/requeue"),
        lambda: client.patch(url, json={"status": "sent"}),
    ):
        res = attempt()
        assert res.status_code == 409, res.text
        assert "one email, ever" in res.json()["detail"]
    assert contacts(client)["items"][0]["status"] == "failed"


def test_database_allows_only_one_sent_event_per_contact(client, db):
    c = add_contact(client, "jane.doe@stripe.com")
    db.add(SendEvent(contact_id=c["id"], event="sent"))
    db.commit()
    db.add(SendEvent(contact_id=c["id"], event="sent"))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


# --- companies --------------------------------------------------------------


def test_companies_counts_and_rename(client):
    import_rows(client, parse(client, "jane.doe@stripe.com, bob.stone@stripe.com"))
    c = contacts(client, q="jane")["items"][0]
    client.patch(f"/contacts/{c['id']}", json={"status": "sent"})

    [stripe] = client.get("/companies").json()
    assert stripe["contact_count"] == 2
    assert stripe["status_counts"] == {"new": 1, "sent": 1}
    assert stripe["last_contacted_at"] is not None

    res = client.patch(f"/companies/{stripe['id']}", json={"name": "Stripe, Inc."})
    assert res.json()["name"] == "Stripe, Inc."
    assert client.patch(f"/companies/{stripe['id']}", json={"name": "  "}).status_code == 422


# --- templates --------------------------------------------------------------


def test_first_template_becomes_default_and_default_moves(client):
    a = client.post("/templates", json=TEMPLATE).json()
    b = client.post("/templates", json={**TEMPLATE, "name": "B"}).json()
    assert (a["is_default"], b["is_default"]) == (True, False)

    client.put(f"/templates/{b['id']}", json={**TEMPLATE, "name": "B", "is_default": True})
    defaults = {t["name"]: t["is_default"] for t in client.get("/templates").json()}
    assert defaults == {"Main": False, "B": True}

    # Can't un-default the only default.
    res = client.put(f"/templates/{b['id']}", json={**TEMPLATE, "name": "B", "is_default": False})
    assert res.json()["is_default"] is True


def test_template_choice_person_then_company_then_default(client):
    default = client.post("/templates", json=TEMPLATE).json()
    special = client.post("/templates", json={**TEMPLATE, "name": "Special", "subject": "Special for [Company]"}).json()
    personal = client.post("/templates", json={**TEMPLATE, "name": "Personal", "subject": "Just for [Name]"}).json()
    assert default["is_default"] and not special["is_default"]
    jane = add_contact(client, "jane.doe@stripe.com")
    subject = lambda: client.get(f"/contacts/{jane['id']}/preview").json()["subject"]

    assert subject() == "Software internship at Stripe"  # nothing chosen: default

    res = client.patch(f"/companies/{jane['company_id']}", json={"template_id": special["id"]})
    assert res.status_code == 200 and res.json()["template_id"] == special["id"]
    assert subject() == "Special for Stripe"  # the company's choice

    res = client.patch(f"/contacts/{jane['id']}", json={"template_id": personal["id"]})
    assert res.json()["template_id"] == personal["id"]
    assert res.json()["company_template_id"] == special["id"]
    assert subject() == "Just for Jane"  # the person's choice wins

    client.patch(f"/contacts/{jane['id']}", json={"template_id": None})
    assert subject() == "Special for Stripe"  # back to the company's
    client.patch(f"/companies/{jane['company_id']}", json={"template_id": None})
    assert subject() == "Software internship at Stripe"  # back to the default

    assert client.patch(f"/contacts/{jane['id']}", json={"template_id": 9999}).status_code == 422
    assert client.patch(f"/companies/{jane['company_id']}", json={"template_id": 9999}).status_code == 422


def test_template_live_preview(client):
    c = add_contact(client, "jane.doe@stripe.com")
    res = client.post("/templates/preview", json={
        "subject": "Hi [name] from [Unknown]", "body": "[Company]", "contact_id": c["id"]})
    body = res.json()
    assert body["subject"] == "Hi Jane from [Unknown]"
    assert body["body"] == "<p>Stripe</p>"
    assert "Unknown token [Unknown]" in body["problems"]


# --- settings + resume ------------------------------------------------------


def test_settings_defaults_and_update(client):
    s = client.get("/settings").json()
    assert s["daily_limit"] == 25 and s["send_days"] == "Mon-Fri"
    assert s["timezone"] == "America/New_York" and s["resume_uploaded"] is False
    assert "gmail_refresh_token_encrypted" not in s

    res = client.put("/settings", json={"signature": '<p onclick="x"><b>Eric</b><script>1</script></p>'})
    assert res.json()["signature"] == "<p><strong>Eric</strong></p>"  # cleaned before saving
    assert client.put("/settings", json={"signature": "<p> </p>"}).json()["signature"] == ""

    res = client.put("/settings", json={"sender_name": "Eric", "daily_limit": 10,
                                        "send_days": "Mon,Wed,Fri", "timezone": "Asia/Ho_Chi_Minh"})
    assert res.status_code == 200, res.text
    assert res.json()["daily_limit"] == 10

    for bad in ({"daily_limit": 0}, {"send_days": "Funday"}, {"timezone": "Mars/Base"},
                {"send_window_start": "25:00"}, {"send_window_start": "17:00"},
                {"resume_filename_pattern": "../evil.pdf"},
                {"resume_filename_pattern": "Resume_{company}.exe"}):
        assert client.put("/settings", json=bad).status_code == 422, bad


def test_resume_upload(client):
    assert client.get("/resume").status_code == 404
    pdf = b"%PDF-1.7\n" + b"x" * 100
    res = client.post("/resume", files={"file": ("cv.pdf", pdf, "application/pdf")})
    assert res.status_code == 200 and res.json()["resume_uploaded"] is True
    res = client.get("/resume")
    assert res.status_code == 200 and res.content == pdf
    assert res.headers["content-type"] == "application/pdf"

    res = client.post("/resume", files={"file": ("cv.pdf", b"not a pdf", "application/pdf")})
    assert res.status_code == 415
    big = b"%PDF-" + b"x" * (5 * 1024 * 1024)
    assert client.post("/resume", files={"file": ("cv.pdf", big, "application/pdf")}).status_code == 413


# --- stats ------------------------------------------------------------------


def test_stats(client, db):
    import_rows(client, parse(client, "jane.doe@stripe.com, bob.stone@stripe.com, tom.ford@ramp.com"))
    ids = [c["id"] for c in contacts(client)["items"]]
    for i in ids:
        client.patch(f"/contacts/{i}", json={"status": "sent"})
    client.post(f"/contacts/{ids[0]}/mark-replied")

    stats = client.get("/stats").json()
    assert stats["sent_today"] == 3
    assert stats["sent_this_week"] == 3
    assert stats["total_companies"] == 2
    assert stats["replies"] == 1
    assert stats["reply_rate"] == round(1 / 3, 4)
    assert len(stats["sends_per_day"]) == 30 and stats["sends_per_day"][-1]["sent"] == 3
    assert stats["recent_activity"][0]["event"] == "replied"
    assert set(stats["warnings"]) == {"gmail_disconnected", "no_resume", "no_default_template"}


def test_unqueue(client, db):
    c = add_contact(client, "jane.doe@stripe.com")
    assert client.post(f"/contacts/{c['id']}/unqueue").status_code == 409  # not queued
    client.patch(f"/contacts/{c['id']}", json={"status": "queued"})
    res = client.post(f"/contacts/{c['id']}/unqueue").json()
    assert (res["status"], res["queued_at"]) == ("new", None)
    assert db.scalars(select(SendEvent.event).order_by(SendEvent.id)).all() == ["queued", "unqueued"]
