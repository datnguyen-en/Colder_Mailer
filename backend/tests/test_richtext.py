from app.richtext import sanitize, to_text


def test_plain_text_becomes_paragraphs():
    assert sanitize("Hi [Name],\n\nLine one\nLine two") == "<p>Hi [Name],</p><p>Line one<br>Line two</p>"
    assert sanitize("5 < 6 & 7") == "<p>5 &lt; 6 &amp; 7</p>"


def test_keeps_only_allowed_formatting():
    dirty = ('<p onclick="x()" style="color:red">a<script>alert(1)</script><style>p{}</style>'
             '<span>b</span><img src=x onerror=y><b>c</b><i>d</i></p>')
    assert sanitize(dirty) == "<p>ab<strong>c</strong><em>d</em></p>"


def test_links_only_with_safe_schemes():
    out = sanitize('<p><a href="javascript:alert(1)">bad</a> <a href="https://a.com/?x=1&y=2" '
                   'onclick="z">ok</a> <a href="mailto:me@x.com">mail</a> <a href="tel:+1">call</a></p>')
    assert out == ('<p>bad <a href="https://a.com/?x=1&amp;y=2" target="_blank" rel="noopener noreferrer">ok</a> '
                   '<a href="mailto:me@x.com" target="_blank" rel="noopener noreferrer">mail</a> '
                   '<a href="tel:+1" target="_blank" rel="noopener noreferrer">call</a></p>')


def test_paragraphs_inside_list_items_are_unwrapped():
    out = sanitize("<ul><li><p>one</p></li><li><p>two</p><p>more</p></li></ul>")
    assert out == "<ul><li>one</li><li>two<br>more</li></ul>"


def test_unclosed_tags_are_closed_and_blank_lines_kept():
    assert sanitize("<p>a <strong>b <em>c</p><p></p><p>d</p>") == (
        "<p>a <strong>b <em>c</em></strong></p><p><br></p><p>d</p>")


def test_dropped_content_does_not_leak():
    assert sanitize("<p>a<script><p>b</p></script>c</p>") == "<p>ac</p>"


def test_plain_text_version():
    html = sanitize('<p>Hi <strong>Jane</strong>,</p><ul><li>Built <a href="https://x.com">RAG</a></li>'
                    '<li>Two</li></ul><ol><li>first</li><li>second</li></ol>'
                    '<p><a href="mailto:me@x.com">me@x.com</a> | <a href="https://x.com">https://x.com</a></p>')
    assert to_text(html) == ("Hi Jane,\n\n- Built RAG (https://x.com)\n- Two\n\n1. first\n2. second\n\n"
                             "me@x.com | https://x.com")
