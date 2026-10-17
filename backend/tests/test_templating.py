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
    assert body == "<p>Hi Jane (Jane Doe, University Recruiter) at Stripe</p>"


def test_tokens_are_case_insensitive():
    subject, body = render(tpl("[COMPANY] / [company]", "Hi [name], [fullNAME]"), JANE, STRIPE)
    assert subject == "Stripe / Stripe"
    assert body == "<p>Hi Jane, Jane Doe</p>"


def test_missing_name_falls_back_to_there():
    no_name = NS(first_name=None, last_name=None, title=None)
    assert render(tpl("Hello", "Hi [Name], / [FullName]"), no_name, STRIPE) == ("Hello", "<p>Hi there, / there</p>")


def test_blank_name_counts_as_missing():
    _, body = render(tpl("Hello"), NS(first_name="   ", last_name="Doe", title=None), STRIPE)
    assert body == "<p>Hi there,</p>"


def test_missing_company_raises():
    with pytest.raises(TemplateError, match=r"\[Company\] has no value"):
        render(tpl("Internship at [Company]"), JANE, None)


def test_missing_title_raises_only_when_used():
    no_title = NS(first_name="Jane", last_name=None, title=None)
    assert render(tpl("Hi"), no_title, STRIPE) == ("Hi", "<p>Hi Jane,</p>")
    with pytest.raises(TemplateError, match=r"\[Title\]"):
        render(tpl("Hi [Title]"), no_title, STRIPE)


def test_fullname_with_first_name_only():
    _, body = render(tpl("Hi", "[FullName]"), NS(first_name="Jane", last_name=None), STRIPE)
    assert body == "<p>Jane</p>"


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
    assert body == "<p>Hi Jane</p>"
    assert problems == ["[Company] has no value for this contact"]


def test_brackets_inside_values_are_not_rescanned():
    subject, _ = render(tpl("At [Company]"), JANE, NS(name="[Stealth]"))
    assert subject == "At [Stealth]"


# --- formatted (HTML) bodies -----------------------------------------------


def test_html_body_keeps_formatting_and_escapes_values():
    subject, body = render(
        tpl("[Company] internship", '<p>Hi <strong>[Name]</strong>, <a href="https://x.com">link</a></p>'),
        NS(first_name="<b>Jo</b>"), NS(name="AT&T"),
    )
    assert subject == "AT&T internship"  # the subject is plain text
    assert body == ('<p>Hi <strong>&lt;b&gt;Jo&lt;/b&gt;</strong>, '
                    '<a href="https://x.com" target="_blank" rel="noopener noreferrer">link</a></p>')


def test_formatting_inside_a_token_still_fills_it():
    _, body = render(tpl("Hi", "<p>[<strong>Name</strong>]</p>"), JANE, STRIPE)
    assert body == "<p>Jane</p>"


def test_signature_follows_a_separator_and_can_use_tokens():
    _, body = render(tpl("Hi", "<p>Hi [Name],</p>"), JANE, STRIPE,
                     signature="<p><strong>Eric</strong> · [Company] fan</p>")
    assert body == "<p>Hi Jane,</p><p>--</p><p><strong>Eric</strong> · Stripe fan</p>"


def test_blank_signature_adds_nothing():
    _, body = render(tpl("Hi", "<p>Hi</p>"), JANE, STRIPE, signature="<p> </p>")
    assert body == "<p>Hi</p>"


def test_body_of_only_empty_paragraphs_is_empty():
    with pytest.raises(TemplateError, match="Body is empty"):
        render(tpl("Hi", "<p></p><p> </p>"), JANE, STRIPE, signature="<p>Eric</p>")


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
