"""G3 T3.4 — Browser Companion page source tests (SPEC §7-12).

All tests use LOCAL HTML fixtures; no live RYM or browser session is ever
required. Covers: normal page, DOM change, empty page, login page, challenge
page, rate-limit page, session-invalid page, missing fields, duplicate records,
Unicode, cache fresh/stale.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from browser_companion import RymGenrePageSource
from browser_companion.contract import (
    CAPTCHA_CHALLENGE,
    LOGIN_REQUIRED,
    OK_STATUS,
    RATE_LIMITED,
    SESSION_INVALID,
    UNKNOWN_PAGE,
    classify_page,
)
from browser_companion.parser import parse_page
from browser_companion.source import PageCache, PageCacheEntry

from omda.ports.errors import SourceUnavailableError

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "rym"
URL = "https://rateyourmusic.com/genre/Ambient/"


def _html(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


class FixtureFetcher:
    def __init__(self, name: str | None = None):
        self.name = name
        self.calls = 0

    def fetch(self, url: str) -> str:
        self.calls += 1
        if self.name is None:
            raise SourceUnavailableError(f"rym: fetch failed for {url}")
        return _html(self.name)


def _clock(value: str):
    return lambda: value


AT0 = "2026-08-20T00:00:00+00:00"
AT1 = "2026-08-21T00:00:00+00:00"
LATER = "2026-08-20T08:00:00+00:00"  # 8h later (> 6h fresh_ttl)


# --- page classification --------------------------------------------------------


def test_normal_genre_page_classified_ok() -> None:
    parsed = parse_page(_html("genre_ok.html"))
    assert classify_page(parsed.title, parsed.body_sample) == OK_STATUS


def test_login_page_classified_login_required() -> None:
    parsed = parse_page(_html("login.html"))
    assert classify_page(parsed.title, parsed.body_sample) == LOGIN_REQUIRED


def test_captcha_page_classified_challenge() -> None:
    parsed = parse_page(_html("captcha.html"))
    assert classify_page(parsed.title, parsed.body_sample) == CAPTCHA_CHALLENGE


def test_rate_limit_page_classified_rate_limited() -> None:
    parsed = parse_page(_html("rate_limit.html"))
    assert classify_page(parsed.title, parsed.body_sample) == RATE_LIMITED


def test_session_invalid_page_classified() -> None:
    parsed = parse_page(_html("session_invalid.html"))
    assert classify_page(parsed.title, parsed.body_sample) == SESSION_INVALID


def test_empty_page_classified_unknown() -> None:
    parsed = parse_page(_html("empty.html"))
    assert classify_page(parsed.title, parsed.body_sample) == UNKNOWN_PAGE


def test_dom_changed_page_classified_unknown() -> None:
    parsed = parse_page(_html("dom_changed.html"))
    assert classify_page(parsed.title, parsed.body_sample) == UNKNOWN_PAGE


def test_unicode_title_survives_parsing() -> None:
    parsed = parse_page(_html("unicode.html"))
    assert parsed.title == "日本語 ミュージック genre"


def test_duplicate_records_do_not_duplicate_extraction() -> None:
    # A page listing the same genre twice still yields ONE stable extract.
    source = RymGenrePageSource(
        fetcher=FixtureFetcher("duplicate.html"), clock=_clock(AT0)
    )
    extract = source.fetch_genre_page(URL)
    assert extract["status"] == OK_STATUS
    assert extract["genre_id"] == "ambient"
    assert extract["genre_name"] == "Ambient"


# --- source behaviour ----------------------------------------------------------


def test_ok_page_returns_schema_validated_extract_with_provenance() -> None:
    source = RymGenrePageSource(fetcher=FixtureFetcher("genre_ok.html"), clock=_clock(AT0))
    extract = source.fetch_genre_page(URL)
    assert extract["status"] == OK_STATUS
    assert extract["page_url"] == URL
    assert extract["title"] == "Ambient Music genre"
    assert extract["genre_id"] == "ambient"
    assert extract["genre_name"] == "Ambient"
    assert extract["extracted_at"] == AT0
    assert extract["provenance"]["source"] == "rym-browser-companion"
    assert extract["provenance"]["page_url"] == URL


@pytest.mark.parametrize(
    ("fixture", "status"),
    [
        ("login.html", LOGIN_REQUIRED),
        ("captcha.html", CAPTCHA_CHALLENGE),
        ("rate_limit.html", RATE_LIMITED),
        ("session_invalid.html", SESSION_INVALID),
        ("empty.html", UNKNOWN_PAGE),
        ("dom_changed.html", UNKNOWN_PAGE),
    ],
    ids=["login", "captcha", "rate-limit", "session", "empty", "dom-changed"],
)
def test_human_action_pages_raise_typed_error(fixture: str, status: str) -> None:
    source = RymGenrePageSource(fetcher=FixtureFetcher(fixture), clock=_clock(AT0))
    with pytest.raises(SourceUnavailableError) as exc:
        source.fetch_genre_page(URL)
    assert exc.value.detail["kind"] == "human-action-required"
    assert exc.value.detail["page_status"] == status
    assert exc.value.detail["page_url"] == URL


def test_fetch_failure_is_typed_unavailable() -> None:
    source = RymGenrePageSource(fetcher=FixtureFetcher(), clock=_clock(AT0))
    with pytest.raises(SourceUnavailableError):
        source.fetch_genre_page(URL)


def test_fresh_cache_skips_fetch() -> None:
    fetcher = FixtureFetcher("genre_ok.html")
    cache = PageCache()
    source = RymGenrePageSource(fetcher=fetcher, clock=_clock(AT0), cache=cache)
    source.fetch_genre_page(URL)
    source.fetch_genre_page(URL)
    assert fetcher.calls == 1  # second call served from cache


def test_stale_cache_refetches() -> None:
    fetcher = FixtureFetcher("genre_ok.html")
    cache = PageCache()
    source = RymGenrePageSource(
        fetcher=fetcher, clock=_clock(AT0), cache=cache, fresh_ttl_seconds=6 * 3600
    )
    first = source.fetch_genre_page(URL)
    assert fetcher.calls == 1
    # clock advances 8h -> stale -> refetch
    source2 = RymGenrePageSource(
        fetcher=fetcher, clock=_clock(LATER), cache=cache, fresh_ttl_seconds=6 * 3600
    )
    second = source2.fetch_genre_page(URL)
    assert fetcher.calls == 2
    assert second["extracted_at"] == LATER
    assert second["genre_id"] == first["genre_id"]  # same stable identity


def test_stale_cache_with_failed_refetch_is_explicit_unavailable() -> None:
    fetcher = FixtureFetcher()  # fails after first success? first fetch also fails
    cache = PageCache()
    cache.put(
        PageCacheEntry(
            page_url=URL,
            extract={
                "page_url": URL,
                "status": OK_STATUS,
                "title": "Ambient Music genre",
                "genre_id": "ambient",
                "genre_name": "Ambient",
                "extracted_at": AT0,
                "provenance": {"source": "rym-browser-companion", "page_url": URL},
            },
            fetched_at=AT0,
        )
    )
    source = RymGenrePageSource(
        fetcher=fetcher, clock=_clock(LATER), cache=cache, fresh_ttl_seconds=6 * 3600
    )
    with pytest.raises(SourceUnavailableError):
        source.fetch_genre_page(URL)  # stale + refetch failed -> explicit error
    assert fetcher.calls == 1
