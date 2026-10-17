"""Email body HTML: allowlist cleaning and the plain-text alternative. Pure functions.

Template bodies and the signature are stored as HTML from the editor. Before
anything is saved, previewed, or sent, `sanitize` rebuilds it from scratch,
keeping only paragraphs, line breaks, bold, italic, lists and http(s)/mailto/tel
links. Everything else (scripts, styles, other tags, attributes) is dropped, so
the result is safe to show in the dashboard and to send.
"""

import html
import re
from html.parser import HTMLParser

# Tags kept as-is, and synonyms folded into them.
ALLOWED = {"p", "br", "strong", "em", "a", "ul", "ol", "li"}
SYNONYMS = {"b": "strong", "i": "em", "div": "p"}
# Content inside these is dropped entirely, not just the tags.
DROP_CONTENT = {"script", "style", "head", "title", "template", "iframe", "object", "noscript"}
LINK_SCHEMES = ("http://", "https://", "mailto:", "tel:")
HTML_TAG_RE = re.compile(r"</?(p|br|div|ul|ol|li|strong|em|b|i|a)\b", re.IGNORECASE)


def looks_like_html(text: str) -> bool:
    return bool(HTML_TAG_RE.search(text or ""))


def text_to_html(text: str) -> str:
    """Plain text (old templates, API callers) as paragraphs: blank line = new
    paragraph, single newline = line break."""
    paragraphs = re.split(r"\n\s*\n", (text or "").replace("\r\n", "\n").strip())
    return "".join(
        f"<p>{html.escape(p).replace(chr(10), '<br>')}</p>" for p in paragraphs if p.strip()
    )


def safe_href(href: str | None) -> str | None:
    href = (href or "").strip()
    return href if href.lower().startswith(LINK_SCHEMES) else None


class _Cleaner(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        # Open elements as (source tag, tag we emitted or None if we dropped it).
        self.open: list[tuple[str, str | None]] = []
        self.dropping = 0  # inside <script>, <style>, ...
        self.li_has_content: list[bool] = []  # one per open <li>

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = SYNONYMS.get(tag, tag)
        if self.dropping:
            if tag in DROP_CONTENT:
                self.dropping += 1
                self.open.append((tag, None))
            return
        if tag == "br":
            self.out.append("<br>")
            return
        emitted: str | None = tag if tag in ALLOWED else None
        if tag in DROP_CONTENT:
            self.dropping += 1
        elif tag == "p" and self.li_has_content:
            # Editors put <p> inside <li>; email clients then add paragraph gaps
            # between bullets. Unwrap it, keeping a line break between paragraphs.
            if self.li_has_content[-1]:
                self.out.append("<br>")
            emitted = None
        elif tag == "a":
            href = safe_href(dict(attrs).get("href"))
            if href is None:
                emitted = None
            else:
                self.out.append(f'<a href="{html.escape(href)}" target="_blank" rel="noopener noreferrer">')
        elif emitted:
            self.out.append(f"<{tag}>")
            if tag == "li":
                self.li_has_content.append(False)
        self.open.append((tag, emitted))

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "br" and not self.dropping:
            self.out.append("<br>")

    def handle_endtag(self, tag: str) -> None:
        tag = SYNONYMS.get(tag, tag)
        # Close the most recent matching element and anything left open inside it.
        for i in range(len(self.open) - 1, -1, -1):
            if self.open[i][0] == tag:
                while len(self.open) > i:
                    self._close(*self.open.pop())
                return

    def _close(self, source: str, emitted: str | None) -> None:
        if source in DROP_CONTENT:
            self.dropping -= 1
        if emitted:
            self.out.append(f"</{emitted}>")
            if emitted == "li":
                self.li_has_content.pop()

    def handle_data(self, data: str) -> None:
        if self.dropping:
            return
        if self.li_has_content and data.strip():
            self.li_has_content[-1] = True
        self.out.append(html.escape(data, quote=False))

    def result(self) -> str:
        while self.open:
            self._close(*self.open.pop())
        return "".join(self.out)


def sanitize(body: str) -> str:
    """Allowlisted HTML for an email body. Plain text is converted to paragraphs."""
    if not looks_like_html(body):
        return text_to_html(body)
    cleaner = _Cleaner()
    cleaner.feed(body or "")
    cleaner.close()
    # An empty paragraph is a deliberate blank line in the editor; keep its height.
    return re.sub(r"<p>\s*</p>", "<p><br></p>", cleaner.result()).strip()


class _Text(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        self.lists: list[list[int | None]] = []  # per list: [counter] (None = bullets)
        self.links: list[str | None] = []
        self.link_text: list[list[str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "br":
            self.out.append("\n")
        elif tag in ("ul", "ol"):
            self.out.append("\n")
            self.lists.append([0 if tag == "ol" else None])
        elif tag == "li" and self.lists:
            counter = self.lists[-1]
            indent = "  " * (len(self.lists) - 1)
            if counter[0] is None:
                self.out.append(f"{indent}- ")
            else:
                counter[0] += 1
                self.out.append(f"{indent}{counter[0]}. ")
        elif tag == "a":
            self.links.append(dict(attrs).get("href"))
            self.link_text.append([])

    def handle_endtag(self, tag: str) -> None:
        if tag == "p":
            self.out.append("\n\n")
        elif tag == "li":
            self.out.append("\n")
        elif tag in ("ul", "ol") and self.lists:
            self.lists.pop()
            self.out.append("\n")
        elif tag == "a" and self.links:
            href, text = self.links.pop(), "".join(self.link_text.pop()).strip()
            target = re.sub(r"^(mailto|tel):", "", href or "", flags=re.IGNORECASE)
            if href and target != text:
                self.out.append(f" ({href})")

    def handle_data(self, data: str) -> None:
        if self.link_text:
            self.link_text[-1].append(data)
        self.out.append(data)


def to_text(body_html: str) -> str:
    """Readable plain text for the text/plain part: paragraphs, "- " bullets,
    numbered lists, and links as "text (url)"."""
    parser = _Text()
    parser.feed(body_html or "")
    parser.close()
    text = "".join(parser.out).replace("\xa0", " ")
    text = re.sub(r"[ \t]+\n", "\n", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()
