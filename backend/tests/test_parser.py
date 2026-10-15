import pytest

from app.parser import is_generic_inbox, is_personal_domain, parse, parse_csv

P, G, N = "personal_email", "generic_inbox", "needs_name"


def row(email, first=None, last=None, company=None, domain=None, flags=()):
    return {
        "email": email,
        "first_name": first,
        "last_name": last,
        "company_name": company,
        "domain": domain or email.split("@")[1],
        "flags": sorted(flags),
    }


# (id, pasted text, expected rows, known aliases, known companies)
CASES = [
    # --- formats ---
    ("plain", "john.smith@amazon.com",
     [row("john.smith@amazon.com", "John", "Smith", "Amazon")], {}, {}),
    ("display name", "Jane Doe <jane.doe@stripe.com>",
     [row("jane.doe@stripe.com", "Jane", "Doe", "Stripe")], {}, {}),
    ("quoted last, first", '"Doe, Jane" <jdoe@stripe.com>',
     [row("jdoe@stripe.com", "Jane", "Doe", "Stripe")], {}, {}),
    ("mailto link", '<a href="mailto:sarah@notion.so">email</a>',
     [row("sarah@notion.so", "Sarah", None, "Notion")], {}, {}),
    ("url-encoded mailto", "mailto:anna%40datadog.com",
     [row("anna@datadog.com", "Anna", None, "Datadog")], {}, {}),
    ("comma, semicolon, newline separated", "alex@figma.com, maria@canva.com;\ntom@airbnb.com",
     [row("alex@figma.com", "Alex", None, "Figma"),
      row("maria@canva.com", "Maria", None, "Canva"),
      row("tom@airbnb.com", "Tom", None, "Airbnb")], {}, {}),
    ("surrounding punctuation", "Reach me (john.smith@amazon.com). Or <kevin.hart@ramp.com>,",
     [row("john.smith@amazon.com", "John", "Smith", "Amazon"),
      row("kevin.hart@ramp.com", "Kevin", "Hart", "Ramp")], {}, {}),
    ("several display names", "Alice Wong <alice.wong@ramp.com>; Bob Stone <bob@ramp.com>",
     [row("alice.wong@ramp.com", "Alice", "Wong", "Ramp"),
      row("bob@ramp.com", "Bob", "Stone", "Ramp")], {}, {}),
    ("header line", "To: Carlos Mendez <carlos@rippling.com>",
     [row("carlos@rippling.com", "Carlos", "Mendez", "Rippling")], {}, {}),
    ("display name inside prose", "Please contact Jane Doe <jane.doe@acme.com> for details",
     [row("jane.doe@acme.com", "Jane", "Doe", "Acme")], {}, {}),
    ("prose word before bracket is not a name", "Mail john.smith@amazon.com or <zxqv@ramp.com>",
     [row("john.smith@amazon.com", "John", "Smith", "Amazon"),
      row("zxqv@ramp.com", company="Ramp", flags=[N])], {}, {}),
    ("junk glued after tld", "email mike.ross@pearson.com.Thanks!",
     [row("mike.ross@pearson.com", "Mike", "Ross", "Pearson")], {}, {}),
    ("image filename is not an email", "<img src='logo@2x.png'>", [], {}, {}),
    ("no emails", "nothing to see here @ all", [], {}, {}),
    ("uppercase is lowercased", "JOHN.SMITH@AMAZON.COM",
     [row("john.smith@amazon.com", "John", "Smith", "Amazon")], {}, {}),
    # --- subdomains and country TLDs ---
    ("subdomain", "kevin.lee@corp.jobs.amazon.com",
     [row("kevin.lee@corp.jobs.amazon.com", "Kevin", "Lee", "Amazon", "amazon.com")], {}, {}),
    ("country tld", "priya.patel@amazon.co.uk",
     [row("priya.patel@amazon.co.uk", "Priya", "Patel", "Amazon", "amazon.co.uk")], {}, {}),
    ("two-level country tld", "wei.zhang@tencent.com.cn",
     [row("wei.zhang@tencent.com.cn", "Wei", "Zhang", "Tencent")], {}, {}),
    # --- known mappings ---
    ("alias wins", "sheryl.sandberg@fb.com",
     [row("sheryl.sandberg@fb.com", "Sheryl", "Sandberg", "Meta")], {"fb.com": "Meta"}, {}),
    ("existing company matched by key across tlds", "ana.lopez@jpmorgan.co.uk",
     [row("ana.lopez@jpmorgan.co.uk", "Ana", "Lopez", "JPMorgan Chase")],
     {}, {"jpmorgan.com": "JPMorgan Chase"}),
    # --- personal domains ---
    ("gmail", "johnsmith@gmail.com",
     [row("johnsmith@gmail.com", flags=[P, N])], {}, {}),
    ("yahoo country variant", "emma.watson@yahoo.co.uk",
     [row("emma.watson@yahoo.co.uk", "Emma", "Watson", flags=[P])], {}, {}),
    ("hotmail france", "luc.besson@hotmail.fr",
     [row("luc.besson@hotmail.fr", "Luc", "Besson", flags=[P])], {}, {}),
    ("edu subdomain + honorific", "Dr. Emily Chen <echen@cs.umass.edu>",
     [row("echen@cs.umass.edu", "Emily", "Chen", domain="umass.edu", flags=[P])], {}, {}),
    # --- role inboxes ---
    ("careers inbox", "careers@google.com",
     [row("careers@google.com", company="Google", flags=[G, N])], {}, {}),
    ("no-reply", "no-reply@linkedin.com",
     [row("no-reply@linkedin.com", company="Linkedin", flags=[G, N])], {}, {}),
    ("role inbox display name is ignored", "Google Careers <careers@google.com>",
     [row("careers@google.com", company="Google", flags=[G, N])], {}, {}),
    ("role word glued in", "amazoncareers@amazon.com",
     [row("amazoncareers@amazon.com", company="Amazon", flags=[G, N])], {}, {}),
    ("role word as last name is a person", "steve.jobs@apple.com",
     [row("steve.jobs@apple.com", "Steve", "Jobs", "Apple")], {}, {}),
    # --- name patterns ---
    ("first initial + last", "jsmith@microsoft.com",
     [row("jsmith@microsoft.com", company="Microsoft", flags=[N])], {}, {}),
    ("dotted initial", "j.smith@uber.com",
     [row("j.smith@uber.com", company="Uber", flags=[N])], {}, {}),
    ("common first name", "sarah@openai.com",
     [row("sarah@openai.com", "Sarah", None, "Openai")], {}, {}),
    ("first name with digits", "sarah2@bloomberg.net",
     [row("sarah2@bloomberg.net", "Sarah", None, "Bloomberg")], {}, {}),
    ("middle initial", "john.q.public@meta.com",
     [row("john.q.public@meta.com", "John", "Public", "Meta")], {}, {}),
    ("underscore", "tom_hanks@pixar.com",
     [row("tom_hanks@pixar.com", "Tom", "Hanks", "Pixar")], {}, {}),
    ("plus tag", "david+jobs@hubspot.com",
     [row("david+jobs@hubspot.com", "David", None, "Hubspot")], {}, {}),
    ("company as display name", "Notion <ivan@notion.so>",
     [row("ivan@notion.so", "Ivan", None, "Notion")], {}, {}),
    ("unknown single token", "zxqv@stripe.com",
     [row("zxqv@stripe.com", company="Stripe", flags=[N])], {}, {}),
    # --- duplicates ---
    ("duplicates in one paste", "john.smith@amazon.com\nJohn.Smith@Amazon.com, john.smith@amazon.com",
     [row("john.smith@amazon.com", "John", "Smith", "Amazon")], {}, {}),
    ("later display name upgrades a duplicate", "jane@ramp.com ... Jane Roe <jane@ramp.com>",
     [row("jane@ramp.com", "Jane", "Roe", "Ramp")], {}, {}),
]


@pytest.mark.parametrize(
    "text,expected,aliases,companies", [c[1:] for c in CASES], ids=[c[0] for c in CASES]
)
def test_parse(text, expected, aliases, companies):
    rows = parse(text, aliases, companies)
    got = [
        {
            "email": r.email,
            "first_name": r.first_name,
            "last_name": r.last_name,
            "company_name": r.company_name,
            "domain": r.domain,
            "flags": sorted(r.flags),
        }
        for r in rows
    ]
    assert got == expected


def test_case_count():
    assert len(CASES) >= 25


@pytest.mark.parametrize("domain,personal", [
    ("gmail.com", True), ("googlemail.com", True), ("outlook.com", True), ("live.com", True),
    ("icloud.com", True), ("me.com", True), ("proton.me", True), ("aol.com", True),
    ("umass.edu", True), ("ox.ac.uk", True), ("google.com", False), ("amazon.co.uk", False),
])
def test_personal_domains(domain, personal):
    assert is_personal_domain(domain) is personal


@pytest.mark.parametrize("local,generic", [
    ("careers", True), ("jobs", True), ("recruiting", True), ("talent", True), ("hr", True),
    ("info", True), ("hello", True), ("contact", True), ("team", True), ("admin", True),
    ("noreply", True), ("no-reply", True), ("support", True), ("careers-us", True),
    ("university.recruiting", True), ("jane.doe", False), ("steve.jobs", False),
])
def test_generic_inboxes(local, generic):
    assert is_generic_inbox(local) is generic


def test_parse_csv_uses_columns():
    csv_text = (
        "﻿First Name,Last Name,Title,Company,Email\n"
        "jane,DOE,University Recruiter,Jane Street Capital,jane.d@janestreet.com\n"
        ",,Engineer,Stripe,jsmith@stripe.com\n"
        "Bob,Stone,,Ramp,BOB@ramp.com\n"
        "Bob,Stone,,Ramp,bob@ramp.com\n"
    )
    rows = parse_csv(csv_text, {}, {"stripe.com": "Stripe, Inc."})
    assert [(r.email, r.first_name, r.last_name, r.title, r.company_name, r.flags) for r in rows] == [
        ("jane.d@janestreet.com", "Jane", "Doe", "University Recruiter", "Jane Street Capital", []),
        ("jsmith@stripe.com", None, None, "Engineer", "Stripe, Inc.", [N]),
        ("bob@ramp.com", "Bob", "Stone", None, "Ramp", []),
    ]


def test_parse_csv_without_email_column_falls_back_to_text():
    rows = parse_csv("name,contact\nJohn,john.smith@amazon.com\n")
    assert [r.email for r in rows] == ["john.smith@amazon.com"]
