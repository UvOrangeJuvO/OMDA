"""Minimal, dependency-free HTML page extraction (G3 T3.4).

Uses only the standard library ``html.parser`` — no bs4, no browser SDK, no
socket. Extracts the <title> plus a bounded sample of visible text; the rest of
the page is discarded. No cookies, profiles, or session material are ever read
or written.
"""

from __future__ import annotations

from dataclasses import dataclass
from html.parser import HTMLParser


@dataclass(frozen=True)
class ParsedPage:
    title: str
    body_sample: str  # bounded sample of visible text, lowercased


class _Sampler(HTMLParser):
    """Collects <title> and a bounded sample of visible text."""

    MAX_SAMPLE = 4000

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title = ""
        self.sample: list[str] = []
        self._in_title = False
        self._seen = 0

    def handle_starttag(self, tag, attrs):
        if tag == "title":
            self._in_title = True

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False

    def handle_data(self, data):
        if self._in_title:
            self.title += data
            return
        if self._seen >= self.MAX_SAMPLE:
            return
        text = " ".join(data.split())
        if text:
            self.sample.append(text)
            self._seen += len(text)


def parse_page(html: str) -> ParsedPage:
    """Parse an HTML document into title + bounded text sample (Unicode-safe).

    Handles Unicode/entity encoding via ``convert_charrefs=True``. DOM changes
    that remove a ``<title>`` yield an empty title -> classified unknown_page.
    """
    parser = _Sampler()
    try:
        parser.feed(html)
        parser.close()
    except (UnicodeDecodeError, ValueError):
        # Malformed HTML that the stdlib parser rejects: treat as empty page.
        return ParsedPage(title="", body_sample="")
    title = parser.title.strip()
    body_sample = " ".join(parser.sample)
    return ParsedPage(title=title, body_sample=body_sample)


__all__ = ["ParsedPage", "parse_page"]
