from types import SimpleNamespace as NS

import pytest

from app.templating import TemplateError, render, render_partial, resume_filename

JANE = NS(first_name="Jane", last_name="Doe", title="University Recruiter")
STRIPE = NS(name="Stripe")


def tpl(subject, body="Hi [Name],"):
    return NS(subject=subject, body=body)


def test_fills_all_tokens():
    subject, body = render(
        tpl("Internship at [Company]", "Hi [Name] ([FullName], [Title]) at [Company]"),
        JANE, STRIPE,
    )
    assert subject == "Internship at Stripe"
    assert body == "Hi Jane (Jane Doe, University Recruiter) at Stripe"


def test_tokens_are_case_insensitive():
    subject, body = render(tpl("[COMPANY] / [company]", "Hi [name], [fullNAME]"), JANE, STRIPE)
    assert subject == "Stripe / Stripe"
    assert body == "Hi Jane, Jane Doe"


def test_missing_name_falls_back_to_there():
    no_name = NS(first_name=None, last_name=None, title=None)
    assert render(tpl("Hello", "Hi [Name], / [FullName]"), no_name, STRIPE) == ("Hello", "Hi there, / there")


def test_blank_name_counts_as_missing():
    _, body = render(tpl("Hello"), NS(first_name="   ", last_name="Doe", title=None), STRIPE)
    assert body == "Hi there,"


def test_missing_company_raises():
    with pytest.raises(TemplateError, match=r"\[Company\] has no value"):
        render(tpl("Internship at [Company]"), JANE, None)


def test_missing_title_raises_only_when_used():
    no_title = NS(first_name="Jane", last_name=None, title=None)
    assert render(tpl("Hi"), no_title, STRIPE) == ("Hi", "Hi Jane,")
    with pytest.raises(TemplateError, match=r"\[Title\]"):
        render(tpl("Hi [Title]"), no_title, STRIPE)


def test_fullname_with_first_name_only():
    _, body = render(tpl("Hi", "[FullName]"), NS(first_name="Jane", last_name=None), STRIPE)
    assert body == "Jane"


def test_unknown_token_raises():
    with pytest.raises(TemplateError, match=r"Unknown token \[Role\]"):
        render(tpl("Hi", "As a [Role] at [Company]"), JANE, STRIPE)


def test_token_with_spaces_is_unknown():
    with pytest.raises(TemplateError, match="Unknown token"):
        render(tpl("Hi", "Hi [ Name ]"), JANE, STRIPE)


def test_curly_placeholder_raises():
    with pytest.raises(TemplateError, match="Unknown placeholder"):
        render(tpl("Hi", "Hi {first_name}"), JANE, STRIPE)


def test_empty_subject_raises():
    with pytest.raises(TemplateError, match="Subject is empty"):
        render(tpl("  "), JANE, STRIPE)


def test_all_problems_reported_together():
    with pytest.raises(TemplateError) as exc:
        render(tpl("[Company] [Foo]", "Hi [Title] [Foo]"), NS(first_name=None), None)
    assert exc.value.problems == [
        "[Company] has no value for this contact",
        "Unknown token [Foo]",
        "[Title] has no value for this contact",
    ]


def test_partial_render_leaves_unfilled_tokens_visible():
    subject, body, problems = render_partial(
        tpl("Role at [Company]", "Hi [Name]"), NS(first_name="Jane"), None
    )
    assert subject == "Role at [Company]"
    assert body == "Hi Jane"
    assert problems == ["[Company] has no value for this contact"]


def test_brackets_inside_values_are_not_rescanned():
    subject, _ = render(tpl("At [Company]"), JANE, NS(name="[Stealth]"))
    assert subject == "At [Stealth]"


@pytest.mark.parametrize("pattern,company,expected", [
    ("Eric_Resume_{company}.pdf", "Amazon", "Eric_Resume_Amazon.pdf"),
    ("Eric_Resume_{company}.pdf", "Jane Street", "Eric_Resume_JaneStreet.pdf"),
    ("Eric_Resume_{company}.pdf", "AT&T", "Eric_Resume_ATT.pdf"),
    ("Eric_Resume_{company}.pdf", "Société Générale", "Eric_Resume_SocieteGenerale.pdf"),
    ("Eric_Resume_{company}.pdf", "../../etc/passwd", "Eric_Resume_etcpasswd.pdf"),
    ("Eric_Resume_{company}.pdf", None, "Eric_Resume.pdf"),
    ("Eric_Resume_{company}.pdf", "!!!", "Eric_Resume.pdf"),
    ("Eric-Resume-{Company}.pdf", "Two Sigma", "Eric-Resume-TwoSigma.pdf"),
    ("Eric_Resume_{company}", "Ramp", "Eric_Resume_Ramp.pdf"),
    ("Resume.pdf", "Ramp", "Resume.pdf"),
])
def test_resume_filename(pattern, company, expected):
    assert resume_filename(pattern, company) == expected
