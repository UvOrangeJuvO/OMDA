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
        self.last_timeout = None

    def fetch(self, url: str, timeout: float | None = None) -> str:
        self.calls += 1
        self.last_timeout = timeout
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


# --- G3-005/G3-006 re-review: bounds, budget, URL, snapshot safety ---------------


def test_fetch_timeout_is_passed_to_fetcher() -> None:
    fetcher = FixtureFetcher("genre_ok.html")
    source = RymGenrePageSource(
        fetcher=fetcher, clock=_clock(AT0), fetch_timeout=7.5
    )
    source.fetch_genre_page(URL)
    assert fetcher.last_timeout == 7.5


def test_fetcher_exception_maps_to_unavailable() -> None:
    class ExplodingFetcher:
        def fetch(self, url, timeout=None):
            raise TimeoutError("bridge hung")

    source = RymGenrePageSource(fetcher=ExplodingFetcher(), clock=_clock(AT0))
    with pytest.raises(SourceUnavailableError):
        source.fetch_genre_page(URL)


def test_disallowed_url_scheme_rejected() -> None:
    source = RymGenrePageSource(fetcher=FixtureFetcher("genre_ok.html"), clock=_clock(AT0))
    with pytest.raises(SourceUnavailableError) as exc:
        source.fetch_genre_page("http://rateyourmusic.com/genre/Ambient/")
    assert "disallowed" in str(exc.value)


def test_disallowed_url_host_rejected() -> None:
    source = RymGenrePageSource(fetcher=FixtureFetcher("genre_ok.html"), clock=_clock(AT0))
    with pytest.raises(SourceUnavailableError):
        source.fetch_genre_page("https://example.org/genre/Ambient/")


def test_disallowed_url_path_rejected() -> None:
    source = RymGenrePageSource(fetcher=FixtureFetcher("genre_ok.html"), clock=_clock(AT0))
    with pytest.raises(SourceUnavailableError) as exc:
        source.fetch_genre_page("https://rateyourmusic.com/artist/foo/")
    assert "path" in str(exc.value)


def test_per_run_page_budget_is_enforced() -> None:
    fetcher = FixtureFetcher("genre_ok.html")
    source = RymGenrePageSource(
        fetcher=fetcher, clock=_clock(AT0), max_pages_per_run=2
    )
    source.fetch_genre_page("https://rateyourmusic.com/genre/A/", run_id="r1")
    source.fetch_genre_page("https://rateyourmusic.com/genre/B/", run_id="r1")
    with pytest.raises(SourceUnavailableError) as exc:
        source.fetch_genre_page("https://rateyourmusic.com/genre/C/", run_id="r1")
    assert "budget exhausted" in str(exc.value)
    # A different run keeps its own budget.
    source.fetch_genre_page("https://rateyourmusic.com/genre/C/", run_id="r2")
    assert source.budget_used("r1") == 2
    assert source.budget_used("r2") == 1


def test_page_cache_evicts_oldest_entries() -> None:
    cache = PageCache(max_entries=2)
    cache.put(
        PageCacheEntry("https://rateyourmusic.com/genre/A/", {"page_url": "a"}, AT0)
    )
    cache.put(
        PageCacheEntry("https://rateyourmusic.com/genre/B/", {"page_url": "b"}, AT0)
    )
    cache.put(
        PageCacheEntry("https://rateyourmusic.com/genre/C/", {"page_url": "c"}, AT0)
    )
    assert cache.get("https://rateyourmusic.com/genre/A/") is None
    assert cache.get("https://rateyourmusic.com/genre/B/") is not None
    assert cache.get("https://rateyourmusic.com/genre/C/") is not None


def test_cached_extract_mutation_does_not_corrupt_cache() -> None:
    fetcher = FixtureFetcher("genre_ok.html")
    source = RymGenrePageSource(fetcher=fetcher, clock=_clock(AT0))
    first = source.fetch_genre_page(URL)
    first["title"] = "MUTATED"  # caller mutates the returned copy
    second = source.fetch_genre_page(URL)  # served from cache
    assert second["title"] == "Ambient Music genre"  # snapshot intact
    assert fetcher.calls == 1


# --- G3-005 re-review 1: finite values and URL canonicalization -----------------


@pytest.mark.parametrize(
    "bad",
    [None, 0, -1, float("inf"), float("nan"), "fast"],
    ids=["none", "zero", "negative", "inf", "nan", "string"],
)
def test_non_finite_fetch_timeout_rejected(bad) -> None:
    # G3-005: the fetch deadline must be finite and positive — None/infinity
    # would defeat the promised bounded deadline.
    with pytest.raises(ValueError):
        RymGenrePageSource(
            fetcher=FixtureFetcher("genre_ok.html"),
            clock=_clock(AT0),
            fetch_timeout=bad,
        )


@pytest.mark.parametrize(
    "bad_url",
    [
        "https://rateyourmusic.com/genre/../release/album/x/",  # dot segment
        "https://rateyourmusic.com/genre/%2e%2e/release/album/x/",  # encoded ..
        "https://rateyourmusic.com/%2e%2e/release/",  # encoded traversal at root
        "https://user@rateyourmusic.com/genre/A/",  # userinfo
        "https://rateyourmusic.com:8080/genre/A/",  # port
        "https://rateyourmusic.com/genre%2fA/",  # encoded slash in segment
    ],
    ids=["dot-segment", "encoded-dotdot", "encoded-traversal", "userinfo", "port", "encoded-slash"],
)
def test_disallowed_url_bypasses_are_rejected(bad_url: str) -> None:
    # G3-005: normalization (dot segments, percent-encoding, userinfo, ports)
    # must never let a target escape the /genre/ boundary.
    source = RymGenrePageSource(fetcher=FixtureFetcher("genre_ok.html"), clock=_clock(AT0))
    with pytest.raises(SourceUnavailableError):
        source.fetch_genre_page(bad_url)


def test_canonical_genre_url_still_accepted() -> None:
    source = RymGenrePageSource(fetcher=FixtureFetcher("genre_ok.html"), clock=_clock(AT0))
    extract = source.fetch_genre_page("https://rateyourmusic.com/genre/Ambient/")
    assert extract["status"] == OK_STATUS


# --- G3-007 re-review 1: budget ledger lifecycle ---------------------------------


def test_budget_ledger_capacity_is_fail_closed() -> None:
    # G3-007: capacity is bounded WITHOUT silently resetting active runs — when
    # the ledger is full and a NEW run id arrives, the request is REJECTED
    # (fail-closed) instead of evicting a still-active run's counter.
    fetcher = FixtureFetcher("genre_ok.html")
    source = RymGenrePageSource(
        fetcher=fetcher, clock=_clock(AT0), max_tracked_runs=2
    )
    source.fetch_genre_page("https://rateyourmusic.com/genre/A/", run_id="r1")
    source.fetch_genre_page("https://rateyourmusic.com/genre/B/", run_id="r2")
    with pytest.raises(SourceUnavailableError) as exc:
        source.fetch_genre_page("https://rateyourmusic.com/genre/C/", run_id="r3")
    assert "ledger" in str(exc.value) or "run" in str(exc.value)
    assert fetcher.calls == 2  # the rejected run never reached the fetcher
    # Active runs keep their counters intact.
    assert source.budget_used("r1") == 1
    assert source.budget_used("r2") == 1
    # Explicit lifecycle cleanup frees capacity for new runs.
    source.finish_run("r2")
    source.fetch_genre_page("https://rateyourmusic.com/genre/C/", run_id="r3")
    assert source.budget_used("r3") == 1
    assert fetcher.calls == 3


def test_finish_run_releases_budget_ledger() -> None:
    fetcher = FixtureFetcher("genre_ok.html")
    source = RymGenrePageSource(
        fetcher=fetcher, clock=_clock(AT0), max_pages_per_run=2
    )
    source.fetch_genre_page("https://rateyourmusic.com/genre/A/", run_id="run-1")
    source.finish_run("run-1")  # explicit run-completion cleanup (G3-007)
    assert source.budget_used("run-1") == 0
    # A new run may start fresh without an unbounded ledger entry (new URL so
    # the fresh page cache does not skip the budget consumption).
    source.fetch_genre_page("https://rateyourmusic.com/genre/B/", run_id="run-2")
    assert source.budget_used("run-2") == 1


# --- G3-005 re-review 2: integer counts, canonical URLs, contact UA -------------


@pytest.mark.parametrize(
    "bad",
    [True, 1.5, float("nan"), float("inf")],
    ids=["bool", "fractional", "nan", "inf"],
)
def test_max_pages_per_run_must_be_positive_integer(bad) -> None:
    # G3-005: page counts are INTEGER bounds; NaN/Infinity/booleans/fractions
    # must fail deterministically at construction, before any fetch.
    with pytest.raises(ValueError):
        RymGenrePageSource(
            fetcher=FixtureFetcher("genre_ok.html"),
            clock=_clock(AT0),
            max_pages_per_run=bad,
        )


@pytest.mark.parametrize(
    "bad",
    [True, 1.5, float("nan"), float("inf")],
    ids=["bool", "fractional", "nan", "inf"],
)
def test_max_tracked_runs_must_be_positive_integer(bad) -> None:
    with pytest.raises(ValueError):
        RymGenrePageSource(
            fetcher=FixtureFetcher("genre_ok.html"),
            clock=_clock(AT0),
            max_tracked_runs=bad,
        )


@pytest.mark.parametrize(
    "bad_url",
    [
        "https://rateyourmusic.com/genre/..\\release/album/x/",  # backslash traversal
        "https://rateyourmusic.com/genre/..%5crelease/album/x/",  # encoded backslash
        "https://rateyourmusic.com/genre/%252e%252e/release/",  # double-encoded ..
        "https://rateyourmusic.com/genre/%252Frelease/",  # double-encoded slash
        "https://rateyourmusic.com/genre/A/%2e%2e/release/",  # encoded dot segment
    ],
    ids=["backslash", "encoded-backslash", "double-dotdot", "double-slash", "encoded-dot-segment"],
)
def test_non_canonical_url_bypasses_are_rejected(bad_url: str) -> None:
    # G3-005: backslashes, residual/double percent-encoding and any non-canonical
    # target must be rejected BEFORE the PageFetcher boundary.
    fetcher = FixtureFetcher("genre_ok.html")
    source = RymGenrePageSource(fetcher=fetcher, clock=_clock(AT0))
    with pytest.raises(SourceUnavailableError):
        source.fetch_genre_page(bad_url)
    assert fetcher.calls == 0  # never reached the fetcher


# --- G3-007 re-review 2: active run budget is a HARD bound ---------------------


def test_interleaved_runs_cannot_reset_active_budget() -> None:
    # Reviewer counter-example: with max_pages_per_run == 1, r1 fetches A (its
    # only page), r2 fetches B (must NOT silently evict active r1), then r1's
    # SECOND fetch must be REJECTED without reaching the fetcher — the active
    # run's counter was never reset by r2's arrival.
    fetcher = FixtureFetcher("genre_ok.html")
    source = RymGenrePageSource(
        fetcher=fetcher,
        clock=_clock(AT0),
        max_pages_per_run=1,
        max_tracked_runs=2,
    )
    source.fetch_genre_page("https://rateyourmusic.com/genre/A/", run_id="r1")
    source.fetch_genre_page("https://rateyourmusic.com/genre/B/", run_id="r2")
    with pytest.raises(SourceUnavailableError) as exc:
        source.fetch_genre_page("https://rateyourmusic.com/genre/C/", run_id="r1")
    assert "budget exhausted" in str(exc.value)
    assert fetcher.calls == 2  # the third request never reached the fetcher
    # r1's own budget stays consumed — the second fetch did not reset it.
    assert source.budget_used("r1") == 1
    # r2's arrival did not steal r1's ledger slot either.
    assert source.budget_used("r2") == 1


def test_active_run_budget_survives_ledger_capacity() -> None:
    # A run that has already consumed pages must NOT lose its counter when the
    # ledger reaches capacity; its hard limit remains in force until finish_run.
    fetcher = FixtureFetcher("genre_ok.html")
    source = RymGenrePageSource(
        fetcher=fetcher,
        clock=_clock(AT0),
        max_pages_per_run=1,
        max_tracked_runs=2,
    )
    source.fetch_genre_page("https://rateyourmusic.com/genre/A/", run_id="r1")
    source.fetch_genre_page("https://rateyourmusic.com/genre/B/", run_id="r2")
    # r3 arriving at full capacity is REJECTED fail-closed (never evicts r1).
    with pytest.raises(SourceUnavailableError) as exc:
        source.fetch_genre_page("https://rateyourmusic.com/genre/C/", run_id="r3")
    assert "ledger" in str(exc.value)
    assert fetcher.calls == 2
    # r1's counter is intact and its own hard limit still applies.
    assert source.budget_used("r1") == 1
    with pytest.raises(SourceUnavailableError):
        source.fetch_genre_page("https://rateyourmusic.com/genre/D/", run_id="r1")
    assert fetcher.calls == 2
    # finish_run frees r1's slot; a NEW run with that identifier is legal.
    source.finish_run("r1")
    source.fetch_genre_page("https://rateyourmusic.com/genre/E/", run_id="r1")
    assert source.budget_used("r1") == 1
    assert fetcher.calls == 3


def test_finished_run_identifier_is_reusable() -> None:
    # After finish_run(r1), the identifier is free again for a NEW run — the
    # explicit completed-run lifecycle rule makes reuse legal.
    fetcher = FixtureFetcher("genre_ok.html")
    source = RymGenrePageSource(
        fetcher=fetcher,
        clock=_clock(AT0),
        max_pages_per_run=1,
        max_tracked_runs=1,
    )
    source.fetch_genre_page("https://rateyourmusic.com/genre/A/", run_id="r1")
    source.finish_run("r1")
    source.fetch_genre_page("https://rateyourmusic.com/genre/B/", run_id="r1")  # new run
    assert source.budget_used("r1") == 1
    with pytest.raises(SourceUnavailableError):
        source.fetch_genre_page("https://rateyourmusic.com/genre/C/", run_id="r1")


# --- G3-006 re-review 2: cache capacity must be a positive integer -------------


@pytest.mark.parametrize(
    "bad",
    [True, 1.5, float("nan"), float("inf"), 0, -1],
    ids=["bool", "fractional", "nan", "inf", "zero", "negative"],
)
def test_page_cache_max_entries_must_be_positive_integer(bad) -> None:
    # G3-006: NaN/Infinity/fractions/booleans would disable the capacity bound.
    with pytest.raises(ValueError):
        PageCache(max_entries=bad)
