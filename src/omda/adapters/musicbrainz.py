"""MusicBrainz / community on-demand enrichment adapter (G3 T3.3).

Implements the EXISTING ``AlbumEnricher`` port. Queries are driven only by the
current run's finite candidates (no bulk/batch enrichment); network behaviour is
bounded (connect/read timeouts, bounded retries, 429/5xx/network classification
with backoff) and fully injectable (transport/clock/sleeper), so ordinary tests
use fakes/fixtures and never touch a live network (SPEC §3.2, §7-12).

Caching is explicit: every entry records source, fetched_at, query version and
provenance; fresh entries short-circuit, stale entries refresh, and a refresh
failure falls back to the stale value with an explicit ``cache_status="stale"``
marker instead of silently hiding source age. Ambiguity (multiple results) is
never collapsed: the adapter returns no canonical identity rather than guessing.
"""

from __future__ import annotations

import json
import time as _time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Protocol

from omda.core.album import normalized_text
from omda.ports.domain import AlbumCandidate, AlbumEvidence, AlbumIdentity
from omda.ports.errors import SourceUnavailableError

DEFAULT_USER_AGENT = "omda/0.1 (+https://github.com/omda) enrichment"
DEFAULT_MAX_RETRIES = 3
DEFAULT_CONNECT_TIMEOUT = 5.0
DEFAULT_READ_TIMEOUT = 10.0
DEFAULT_BASE_DELAY = 1.0
DEFAULT_MAX_BACKOFF = 30.0
DEFAULT_FRESH_TTL = 7 * 24 * 3600  # 7 days
# G3-005: client-side pacing across successful calls — MusicBrainz guidance
# requires at most ~1 request/second; keep this >= 1.0 for live use.
DEFAULT_PACING_SECONDS = 1.0
DEFAULT_CACHE_MAX_ENTRIES = 256

QUERY_VERSION = "v1"

_RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})


@dataclass(frozen=True)
class MBHttpResponse:
    """A raw HTTP response as seen by the adapter (injectable transport)."""

    status: int
    body: str

    def json(self) -> dict:
        try:
            data = json.loads(self.body)
        except json.JSONDecodeError as exc:
            raise SourceUnavailableError("musicbrainz: malformed JSON response") from exc
        if not isinstance(data, dict):
            raise SourceUnavailableError("musicbrainz: response body is not a JSON object")
        return data


class Transport(Protocol):
    """Injectable network boundary: no socket/HTTP imports live in this module."""

    def get(
        self,
        url: str,
        params: Mapping[str, str] | None = None,
        headers: Mapping[str, str] | None = None,
        timeout: tuple[float, float] | None = None,
    ) -> MBHttpResponse:
        """Perform a bounded GET; provider exceptions are classified by callers."""
        ...


@dataclass(frozen=True)
class EnrichmentEntry:
    """One cache entry with full provenance (SPEC §3.3, MP §5)."""

    query_key: str
    canonical_id: str | None
    canonical_source: str | None
    fetched_at: str
    query_version: str
    source: str


class EnrichmentCache:
    """Bounded in-memory enrichment cache keyed by normalized query (G3-006).

    Capacity is capped at ``max_entries`` with deterministic FIFO eviction;
    ``get``/``put`` are overridable for a persistent (JSON file) backend; the
    adapter only ever sees provenance-carrying entries.
    """

    def __init__(self, max_entries: int = DEFAULT_CACHE_MAX_ENTRIES) -> None:
        if max_entries <= 0:
            raise ValueError("max_entries must be > 0")
        self._max_entries = max_entries
        self._entries: dict[str, EnrichmentEntry] = {}

    def get(self, query_key: str) -> EnrichmentEntry | None:
        return self._entries.get(query_key)

    def put(self, entry: EnrichmentEntry) -> None:
        # G3-006: bounded capacity with deterministic FIFO eviction — a
        # long-lived process never grows memory without limit.
        if entry.query_key not in self._entries and len(self._entries) >= self._max_entries:
            oldest_key = next(iter(self._entries))
            self._entries.pop(oldest_key)
        self._entries[entry.query_key] = entry


class MusicBrainzEnricher:
    """``AlbumEnricher`` over the MusicBrainz release-group search API."""

    def __init__(
        self,
        *,
        transport: Transport,
        clock: Callable[[], str],
        sleeper: Callable[[float], None] = _time.sleep,
        cache: EnrichmentCache | None = None,
        user_agent: str = DEFAULT_USER_AGENT,
        max_retries: int = DEFAULT_MAX_RETRIES,
        connect_timeout: float = DEFAULT_CONNECT_TIMEOUT,
        read_timeout: float = DEFAULT_READ_TIMEOUT,
        base_delay: float = DEFAULT_BASE_DELAY,
        max_backoff: float = DEFAULT_MAX_BACKOFF,
        fresh_ttl_seconds: float = DEFAULT_FRESH_TTL,
        pacing_seconds: float = DEFAULT_PACING_SECONDS,
    ) -> None:
        if max_retries < 0:
            raise ValueError("max_retries must be >= 0")
        if pacing_seconds < 0:
            raise ValueError("pacing_seconds must be >= 0")
        self._transport = transport
        self._clock = clock
        self._sleeper = sleeper
        self._cache = cache or EnrichmentCache()
        self._user_agent = user_agent
        self._max_retries = max_retries
        self._connect_timeout = connect_timeout
        self._read_timeout = read_timeout
        self._base_delay = base_delay
        self._max_backoff = max_backoff
        self._fresh_ttl = fresh_ttl_seconds
        self._pacing = pacing_seconds
        self._url = "https://musicbrainz.org/ws/2/release-group/"

    # -- AlbumEnricher port ----------------------------------------------------
    def enrich(self, candidate: AlbumCandidate) -> AlbumCandidate:
        """Return an enriched copy (canonical identity) for ONE candidate.

        Driven only by this candidate (finite, per-run): no bulk/batch lookup.
        G3-004: the Port signature is unchanged, so a stale-refresh failure
        cannot carry evidence through the return value — it therefore FAILS
        CLEARLY with the stale evidence in the error detail instead of silently
        serving unlabelled old data. Callers that need observable freshness use
        :meth:`enrich_with_evidence`.
        """
        enriched, _ = self.enrich_with_evidence(candidate)
        return enriched

    def enrich_with_evidence(
        self, candidate: AlbumCandidate
    ) -> tuple[AlbumCandidate, AlbumEvidence]:
        """Enrich one candidate and return its caller-visible evidence.

        ``AlbumEvidence`` carries cache_status ("fresh"|"stale"), source,
        fetched_at and query_version so downstream code can report source age or
        decide whether stale evidence is acceptable (MP §6).
        """
        key = self._query_key(candidate)
        cached = self._cache.get(key)
        now = self._clock()
        if cached is not None and self._is_fresh(cached, now):
            return (
                self._apply(candidate, cached),
                AlbumEvidence("fresh", cached.source, cached.fetched_at, cached.query_version),
            )
        try:
            entry = self._lookup(candidate, key, now)
        except SourceUnavailableError as exc:
            if cached is not None:
                # G3-004: fail clearly — the stale evidence is preserved and
                # exposed through the error detail; never silently relabel it.
                raise SourceUnavailableError(
                    "musicbrainz: refresh failed; stale evidence from "
                    f"{cached.fetched_at} is not served without an observable marker",
                    detail={
                        "kind": "stale-refresh-failure",
                        "cache_status": "stale",
                        "source": cached.source,
                        "fetched_at": cached.fetched_at,
                        "query_version": cached.query_version,
                    },
                ) from exc
            raise
        self._cache.put(entry)
        return (
            self._apply(candidate, entry),
            AlbumEvidence("fresh", entry.source, entry.fetched_at, entry.query_version),
        )

    # -- internals -------------------------------------------------------------
    def _query_key(self, candidate: AlbumCandidate) -> str:
        artist = normalized_text(candidate.artist)
        title = normalized_text(candidate.title)
        year = candidate.year if candidate.year is not None else ""
        return f"{QUERY_VERSION}|{artist}|{title}|{year}"

    def _is_fresh(self, entry: EnrichmentEntry, now: str) -> bool:
        try:
            fetched = _to_epoch(entry.fetched_at)
            current = _to_epoch(now)
        except (TypeError, ValueError):
            return False
        return (current - fetched) <= self._fresh_ttl

    def _lookup(self, candidate: AlbumCandidate, key: str, now: str) -> EnrichmentEntry:
        params = {
            "query": (
                f'release:"{candidate.title}" AND artist:"{candidate.artist}"'
            ),
            "fmt": "json",
            "limit": "5",
        }
        headers = {"User-Agent": self._user_agent}
        timeout = (self._connect_timeout, self._read_timeout)
        response = self._get_with_retry(params, headers, timeout)
        if response.status == 404:
            # Explicit no-match: record an empty result (no canonical identity).
            return EnrichmentEntry(
                query_key=key,
                canonical_id=None,
                canonical_source=None,
                fetched_at=now,
                query_version=QUERY_VERSION,
                source="musicbrainz",
            )
        data = response.json()
        release_groups = data.get("release-groups")
        if not isinstance(release_groups, list):
            raise SourceUnavailableError("musicbrainz: response missing 'release-groups'")
        # G3-003: validate every item shape BEFORE any matching, translating
        # malformed items into the domain error taxonomy.
        items = [self._parse_item(item) for item in release_groups]
        matches = [item for item in items if self._matches(candidate, item)]
        if not matches:
            # No plausible match: explicit no-match (no canonical identity).
            return self._no_match_entry(key, now)
        if len(matches) > 1:
            # Ambiguity is never silently collapsed (SPEC §2.4): no canonical ID.
            return self._no_match_entry(key, now)
        match = matches[0]
        if self._year_conflict(candidate, match):
            # Corroboration (year) conflicts: refuse to install a destructive ID.
            return self._no_match_entry(key, now)
        return EnrichmentEntry(
            query_key=key,
            canonical_id=match["id"],
            canonical_source="musicbrainz",
            fetched_at=now,
            query_version=QUERY_VERSION,
            source="musicbrainz",
        )

    def _parse_item(self, item) -> dict:
        """Validate one release-group item; malformed items raise the domain error."""
        if not isinstance(item, dict):
            raise SourceUnavailableError(
                "musicbrainz: release-group item must be a JSON object"
            )
        canonical_id = item.get("id")
        if not isinstance(canonical_id, str) or not canonical_id:
            raise SourceUnavailableError(
                "musicbrainz: release-group item missing canonical 'id'"
            )
        title = item.get("title")
        if not isinstance(title, str) or not title:
            raise SourceUnavailableError(
                "musicbrainz: release-group item missing 'title'"
            )
        artist_credit = item.get("artist-credit")
        if not isinstance(artist_credit, list) or not artist_credit:
            raise SourceUnavailableError(
                "musicbrainz: release-group item missing 'artist-credit'"
            )
        names: list[str] = []
        for credit in artist_credit:
            if not isinstance(credit, dict) or not isinstance(credit.get("name"), str):
                raise SourceUnavailableError(
                    "musicbrainz: malformed artist-credit entry"
                )
            names.append(credit["name"])
        year = None
        first_date = item.get("first-release-date")
        if isinstance(first_date, str) and len(first_date) >= 4 and first_date[:4].isdigit():
            year = int(first_date[:4])
        return {"id": canonical_id, "title": title, "artist": " ".join(names), "year": year}

    def _matches(self, candidate: AlbumCandidate, item: dict) -> bool:
        """Strong match: normalized title AND complete artist-credit both equal."""
        return (
            normalized_text(candidate.title) == normalized_text(item["title"])
            and normalized_text(candidate.artist) == normalized_text(item["artist"])
        )

    def _year_conflict(self, candidate: AlbumCandidate, item: dict) -> bool:
        """Conflicting first-release year rejects exactness (reviewable corroboration)."""
        if candidate.year is None or item["year"] is None:
            return False
        return candidate.year != item["year"]

    def _no_match_entry(self, key: str, now: str) -> EnrichmentEntry:
        return EnrichmentEntry(
            query_key=key,
            canonical_id=None,
            canonical_source=None,
            fetched_at=now,
            query_version=QUERY_VERSION,
            source="musicbrainz",
        )

    def _get_with_retry(self, params, headers, timeout) -> MBHttpResponse:
        last_error: Exception | None = None
        for attempt in range(self._max_retries + 1):
            try:
                response = self._transport.get(self._url, params, headers, timeout)
            except Exception as exc:  # transport-level failure (timeout, network)
                last_error = exc
                if attempt < self._max_retries:
                    self._backoff(attempt)
                continue
            if response.status in _RETRYABLE_STATUS:
                last_error = SourceUnavailableError(
                    f"musicbrainz: HTTP {response.status} (retryable)"
                )
                if attempt < self._max_retries:
                    self._backoff(attempt)
                continue
            if response.status == 404:
                # Explicit no-result is not an error: empty result path.
                self._pace()  # G3-005: pace successful calls too
                return response
            if response.status != 200:
                raise SourceUnavailableError(f"musicbrainz: HTTP {response.status}")
            self._pace()  # G3-005: client-side pacing across successful calls
            return response
        raise SourceUnavailableError(
            f"musicbrainz: request failed after {self._max_retries + 1} attempts"
            f" ({last_error})"
        )

    def _pace(self) -> None:
        """Sleep the configured pacing interval after a successful call (G3-005)."""
        if self._pacing > 0:
            self._sleeper(self._pacing)

    def _backoff(self, attempt: int) -> None:
        delay = min(self._base_delay * (2**attempt), self._max_backoff)
        self._sleeper(delay)

    def _apply(
        self, candidate: AlbumCandidate, entry: EnrichmentEntry
    ) -> AlbumCandidate:
        identity = None
        if entry.canonical_id and entry.canonical_source:
            identity = AlbumIdentity(
                album_id=candidate.album_id,
                canonical_id=entry.canonical_id,
                canonical_source=entry.canonical_source,
                identity_confidence="exact",
            )
        return replace(
            candidate,
            identity=identity or candidate.identity,
        )


def _to_epoch(value: str) -> float:
    """Parse an ISO 8601 timestamp (with timezone) into epoch seconds."""
    return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()


__all__ = [
    "DEFAULT_FRESH_TTL",
    "DEFAULT_USER_AGENT",
    "EnrichmentCache",
    "EnrichmentEntry",
    "MBHttpResponse",
    "MusicBrainzEnricher",
    "QUERY_VERSION",
    "Transport",
]
