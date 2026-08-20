"""RymGenrePageSource — thin, compliant page source for an active run (G3 T3.4).

Fetches ONE page for the current run's needs, parses the minimum fields,
classifies the page state, schema-validates the output with provenance and
timestamp, and caches it (fresh/stale). Non-``ok`` states raise a typed
``SourceUnavailableError`` with ``detail.kind == "human-action-required"`` —
the operator is asked to intervene; the companion never bypasses Cloudflare,
solves CAPTCHAs, mass-crawls or fans out to Album Detail pages.

G3-005: fetch deadlines/timeouts are part of the executable contract, page URLs
are restricted to the intended HTTPS RYM origin/genre path, and a configurable
per-run page budget is enforced. G3-006: the cache is capacity-bounded with
deterministic FIFO eviction and stores immutable snapshots (callers get
defensive copies, never the cached object).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import unquote, urlparse

from browser_companion.contract import (
    HUMAN_ACTION_STATUSES,
    classify_page,
    extract_genre_metadata,
    human_action_error,
)
from browser_companion.parser import parse_page
from omda.ports.domain import freeze_json, thaw_json
from omda.ports.errors import InvalidInputError, SourceUnavailableError
from omda.schemas import validate
from omda.schemas.validator import RecordValidationError

SOURCE_NAME = "rym-browser-companion"
QUERY_VERSION = "v1"

# G3-005: only the intended HTTPS RYM genre origin is acceptable.
RYM_ORIGIN = "rateyourmusic.com"
RYM_GENRE_PATH_PREFIX = "/genre/"

DEFAULT_MAX_PAGES_PER_RUN = 10
DEFAULT_CACHE_MAX_ENTRIES = 64
DEFAULT_MAX_TRACKED_RUNS = 64


def _is_finite_positive(value: float) -> bool:
    """True when ``value`` is a real, finite, strictly positive number (G3-005)."""
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and value > 0
        and value != float("inf")
        and value != float("nan")
    )


class PageFetcher(Protocol):
    """Injectable fetch boundary with a REQUIRED finite deadline (G3-005)."""

    def fetch(self, url: str, timeout: float) -> str:
        ...


@dataclass(frozen=True)
class PageCacheEntry:
    page_url: str
    extract: dict  # frozen snapshot (MappingProxyType after freeze_json)
    fetched_at: str


class PageCache:
    """Capacity-bounded in-memory page cache with FIFO eviction (G3-006)."""

    def __init__(self, max_entries: int = DEFAULT_CACHE_MAX_ENTRIES) -> None:
        if max_entries <= 0:
            raise ValueError("max_entries must be > 0")
        self._max_entries = max_entries
        self._entries: dict[str, PageCacheEntry] = {}

    def get(self, page_url: str) -> PageCacheEntry | None:
        entry = self._entries.get(page_url)
        if entry is None:
            return None
        # Defensive copy: callers can never mutate the cached snapshot.
        return PageCacheEntry(
            page_url=entry.page_url,
            extract=thaw_json(entry.extract),
            fetched_at=entry.fetched_at,
        )

    def put(self, entry: PageCacheEntry) -> None:
        if entry.page_url not in self._entries and len(self._entries) >= self._max_entries:
            oldest_key = next(iter(self._entries))
            self._entries.pop(oldest_key)
        # Store an immutable snapshot (recursively frozen).
        self._entries[entry.page_url] = PageCacheEntry(
            page_url=entry.page_url,
            extract=freeze_json(entry.extract),
            fetched_at=entry.fetched_at,
        )


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
        fetch_timeout: float = 10.0,
        max_pages_per_run: int = DEFAULT_MAX_PAGES_PER_RUN,
        max_tracked_runs: int = DEFAULT_MAX_TRACKED_RUNS,
    ) -> None:
        if max_pages_per_run <= 0:
            raise ValueError("max_pages_per_run must be > 0")
        if max_tracked_runs <= 0:
            raise ValueError("max_tracked_runs must be > 0")
        # G3-005: the fetch deadline must be finite and positive — None/zero/
        # negative/NaN/infinity would defeat the promised bounded access.
        if not _is_finite_positive(fetch_timeout):
            raise ValueError(
                f"fetch_timeout must be a finite positive number, got {fetch_timeout!r}"
            )
        if not _is_finite_positive(fresh_ttl_seconds):
            raise ValueError(
                f"fresh_ttl_seconds must be a finite positive number, "
                f"got {fresh_ttl_seconds!r}"
            )
        self._fetcher = fetcher
        self._clock = clock
        self._cache = cache or PageCache()
        self._fresh_ttl = fresh_ttl_seconds
        self._fetch_timeout = fetch_timeout
        self._max_pages_per_run = max_pages_per_run
        self._max_tracked_runs = max_tracked_runs
        self._budget_used: dict[str, int] = {}

    def fetch_genre_page(self, page_url: str, run_id: str | None = None) -> dict:
        """Fetch, parse, classify, validate and cache one genre page.

        Returns the schema-validated ``rym_page`` record on success; raises a
        typed ``SourceUnavailableError`` (human-action-required, timeout,
        budget exhaustion or disallowed URL) otherwise.
        """
        self._check_url(page_url)
        run_id = run_id or "default"
        cached = self._cache.get(page_url)
        now = self._clock()
        if cached is not None and _is_fresh(cached, now, self._fresh_ttl):
            return cached.extract
        self._consume_budget(run_id, page_url)
        try:
            html = self._fetcher.fetch(page_url, timeout=self._fetch_timeout)
        except SourceUnavailableError:
            raise
        except Exception as exc:  # G3-005: fetcher failures map to domain errors
            raise SourceUnavailableError(
                f"rym: page fetch failed for {page_url}: {exc}"
            ) from exc
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

    def budget_used(self, run_id: str | None = None) -> int:
        return self._budget_used.get(run_id or "default", 0)

    def finish_run(self, run_id: str | None = None) -> None:
        """Explicitly discard a run's budget ledger entry at run completion.

        G3-007: budget state is run-scoped and released when the run finishes;
        callers must invoke this exactly once when a run completes, so a
        finished run's ledger can never keep the long-lived object growing.
        """
        self._budget_used.pop(run_id or "default", None)

    # -- internals -------------------------------------------------------------
    def _check_url(self, page_url: str) -> None:
        """G3-005: allow only the canonical HTTPS RYM genre origin/path.

        Rejects dot segments, percent-encoded separators/traversal, userinfo
        and ports so browser/HTTP normalization cannot escape ``/genre/``.
        """
        try:
            parsed = urlparse(page_url)
        except ValueError as exc:
            raise SourceUnavailableError(f"rym: malformed page URL {page_url!r}") from exc
        if parsed.scheme != "https" or parsed.netloc != RYM_ORIGIN:
            raise SourceUnavailableError(
                f"rym: disallowed page URL {page_url!r} — only "
                f"https://{RYM_ORIGIN}/genre/... is permitted"
            )
        if "@" in parsed.netloc or ":" in parsed.netloc:
            raise SourceUnavailableError(
                f"rym: disallowed page URL {page_url!r} — userinfo/port are not allowed"
            )
        raw_path = parsed.path
        if not raw_path.startswith(RYM_GENRE_PATH_PREFIX):
            raise SourceUnavailableError(
                f"rym: disallowed page path {raw_path!r} — only the "
                f"{RYM_GENRE_PATH_PREFIX}... path is permitted"
            )
        # Reject dot segments and percent-encoded traversal (raw and decoded).
        decoded = unquote(raw_path)
        for candidate in (raw_path, decoded):
            segments = candidate.split("/")
            if any(segment in (".", "..") for segment in segments):
                raise SourceUnavailableError(
                    f"rym: disallowed dot segment in page URL {page_url!r}"
                )
        if not decoded.startswith(RYM_GENRE_PATH_PREFIX):
            raise SourceUnavailableError(
                f"rym: decoded path {decoded!r} escapes the {RYM_GENRE_PATH_PREFIX}... "
                "boundary"
            )

    def _consume_budget(self, run_id: str, page_url: str) -> None:
        # G3-007: the ledger is bounded — the oldest tracked run is evicted
        # when capacity is reached, so a long-lived object cannot grow forever.
        if run_id not in self._budget_used and len(self._budget_used) >= self._max_tracked_runs:
            oldest_run = next(iter(self._budget_used))
            self._budget_used.pop(oldest_run)
        used = self._budget_used.get(run_id, 0)
        if used >= self._max_pages_per_run:
            raise SourceUnavailableError(
                f"rym: page budget exhausted for run {run_id!r} "
                f"(max {self._max_pages_per_run} pages)"
            )
        self._budget_used[run_id] = used + 1


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


__all__ = [
    "PageCache",
    "PageCacheEntry",
    "RYM_GENRE_PATH_PREFIX",
    "RYM_ORIGIN",
    "RymGenrePageSource",
    "SOURCE_NAME",
]
