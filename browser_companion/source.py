"""RymGenrePageSource — thin, compliant page source for an active run (G3 T3.4).

Fetches ONE page for the current run's needs, parses the minimum fields,
classifies the page state, schema-validates the output with provenance and
timestamp, and caches it (fresh/stale). Non-``ok`` states raise a typed
``SourceUnavailableError`` with ``detail.kind == "human-action-required"`` —
the operator is asked to intervene; the companion never bypasses Cloudflare,
solves CAPTCHAs, mass-crawls or fans out to Album Detail pages.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from browser_companion.contract import (
    HUMAN_ACTION_STATUSES,
    classify_page,
    extract_genre_metadata,
    human_action_error,
)
from browser_companion.parser import parse_page
from omda.ports.errors import InvalidInputError
from omda.schemas import validate
from omda.schemas.validator import RecordValidationError

SOURCE_NAME = "rym-browser-companion"
QUERY_VERSION = "v1"


class PageFetcher(Protocol):
    """Injectable fetch boundary: returns raw HTML for a URL."""

    def fetch(self, url: str) -> str:
        ...


@dataclass(frozen=True)
class PageCacheEntry:
    page_url: str
    extract: dict
    fetched_at: str


class PageCache:
    """Bounded in-memory page cache (override for persistence)."""

    def __init__(self) -> None:
        self._entries: dict[str, PageCacheEntry] = {}

    def get(self, page_url: str) -> PageCacheEntry | None:
        return self._entries.get(page_url)

    def put(self, entry: PageCacheEntry) -> None:
        self._entries[entry.page_url] = entry


class RymGenrePageSource:
    """Extract + validate ONE RYM genre page for the current run.

    Disable-able by construction: nothing else in OMDA depends on this module;
    the Orchestrator/Core keep working with other sources and fakes.
    """

    def __init__(
        self,
        *,
        fetcher: PageFetcher,
        clock: Callable[[], str],
        cache: PageCache | None = None,
        fresh_ttl_seconds: float = 6 * 3600,
    ) -> None:
        self._fetcher = fetcher
        self._clock = clock
        self._cache = cache or PageCache()
        self._fresh_ttl = fresh_ttl_seconds
        self._url = None

    def fetch_genre_page(self, page_url: str) -> dict:
        """Fetch, parse, classify, validate and cache one genre page.

        Returns the schema-validated ``rym_page`` record on success; raises a
        typed ``SourceUnavailableError`` (human-action-required) otherwise.
        """
        cached = self._cache.get(page_url)
        now = self._clock()
        if cached is not None and _is_fresh(cached, now, self._fresh_ttl):
            return cached.extract
        html = self._fetcher.fetch(page_url)
        parsed = parse_page(html)
        status = classify_page(parsed.title, parsed.body_sample)
        if status in HUMAN_ACTION_STATUSES:
            raise human_action_error(page_url, status, {"title": parsed.title})
        extract = {
            "page_url": page_url,
            "status": status,
            "title": parsed.title,
            "extracted_at": now,
            "provenance": {"source": SOURCE_NAME, "page_url": page_url},
        }
        meta = extract_genre_metadata(parsed.title)
        if meta.get("genre_id"):
            extract["genre_id"] = meta["genre_id"]
        if meta.get("genre_name"):
            extract["genre_name"] = meta["genre_name"]
        _validate_extract(extract, page_url)
        self._cache.put(PageCacheEntry(page_url=page_url, extract=extract, fetched_at=now))
        return extract


def _validate_extract(extract: dict, page_url: str) -> None:
    try:
        validate("rym_page", extract, page_url)
    except RecordValidationError as exc:
        raise InvalidInputError(str(exc), detail={"errors": exc.errors}) from exc


def _is_fresh(entry: PageCacheEntry, now: str, ttl: float) -> bool:
    from datetime import datetime

    try:
        fetched = datetime.fromisoformat(entry.fetched_at.replace("Z", "+00:00")).timestamp()
        current = datetime.fromisoformat(now.replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError):
        return False
    return (current - fetched) <= ttl


__all__ = ["PageCache", "PageCacheEntry", "RymGenrePageSource", "SOURCE_NAME"]
