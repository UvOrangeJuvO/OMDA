"""MusicBrainz / community on-demand enrichment adapter (G3 T3.3).

Implements the EXISTING ``AlbumEnricher`` port. Queries are driven only by the
current run's finite candidates (no bulk/batch enrichment); network behaviour is
bounded (connect/read timeouts, bounded retries, 429/5xx/network classification
with backoff) and fully injectable (transport/clock/sleeper), so ordinary tests
use fakes/fixtures and never touch a live network (SPEC §3.2, §7-12).

Caching is explicit: every entry records source, fetched_at, query version and
provenance; fresh entries short-circuit and stale entries refresh. A refresh
failure is observable as a TYPED ``SourceUnavailableError`` whose detail carries
the stale provenance (cache_status/source/fetched_at/query_version); the stale
identity is NEVER served because the accepted ``AlbumEnricher`` Port return
value cannot label it — the run fails clearly and can decide recovery. Ambiguity
(multiple results) is never collapsed: the adapter returns no canonical identity
rather than guessing.
"""

from __future__ import annotations

import json
import re
import time as _time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Protocol
from urllib.parse import urlparse

from omda.core.album import normalized_text
from omda.ports.domain import AlbumCandidate, AlbumIdentity
from omda.ports.errors import SourceUnavailableError

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

# G3-005: MusicBrainz requires a MEANINGFUL, contactable User-Agent for live
# API use. No verified project contact exists in this repository, so the
# constructor REQUIRES an explicit User-Agent and no placeholder default is
# offered. Live deployments must supply a contactable value.
DEFAULT_USER_AGENT: str | None = None

# G3-003: MusicBrainz search score is a 0..100 confidence value. A destructive
# canonical identity requires a STRONG search match; anything below this named,
# documented threshold is treated as insufficient corroboration (no exact).
MIN_EXACT_SCORE = 90.0
_SCORE_MIN = 0.0
_SCORE_MAX = 100.0

# G3-003: the query/cache policy version. Advance this version whenever
# matching or destructive-identity acceptance semantics change — cache entries
# written under an older policy (e.g. the pre-90-point weak-score rule) carry a
# different namespace prefix and are NEVER served as current exact identities;
# a version mismatch forces a fresh lookup under the current policy.
QUERY_VERSION = "v2"

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
        # G3-006: capacity is a positive INTEGER — booleans, fractions and
        # non-finite values would silently disable the eviction bound.
        if (
            not isinstance(max_entries, int)
            or isinstance(max_entries, bool)
            or max_entries <= 0
        ):
            raise ValueError(
                f"max_entries must be a positive integer, got {max_entries!r}"
            )
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
        user_agent: str | None = DEFAULT_USER_AGENT,
        max_retries: int = DEFAULT_MAX_RETRIES,
        connect_timeout: float = DEFAULT_CONNECT_TIMEOUT,
        read_timeout: float = DEFAULT_READ_TIMEOUT,
        base_delay: float = DEFAULT_BASE_DELAY,
        max_backoff: float = DEFAULT_MAX_BACKOFF,
        fresh_ttl_seconds: float = DEFAULT_FRESH_TTL,
        pacing_seconds: float = DEFAULT_PACING_SECONDS,
    ) -> None:
        # G3-005: retries are an INTEGER count — booleans, fractions, non-finite
        # values, strings and negatives fail deterministically at construction.
        if (
            not isinstance(max_retries, int)
            or isinstance(max_retries, bool)
            or max_retries < 0
        ):
            raise ValueError(
                f"max_retries must be a non-negative integer, got {max_retries!r}"
            )
        # G3-005: a MEANINGFUL, CONTACTABLE User-Agent is REQUIRED for live use
        # (MusicBrainz policy). An explicit value is not enough — it must carry
        # an `Application/version (contact URL or email)` contact shape, so an
        # anonymous/non-contact string can never be silently substituted.
        if not _is_contactable_user_agent(user_agent):
            raise ValueError(
                "user_agent must match 'Application/version (contact URL or "
                "email)' with a contactable URL or email, got "
                f"{user_agent!r}"
            )
        # G3-005: every time/delay/pacing value must be finite and positive —
        # zero/negative/NaN/infinity would defeat the promised bounded access.
        for name, value in (
            ("connect_timeout", connect_timeout),
            ("read_timeout", read_timeout),
            ("base_delay", base_delay),
            ("max_backoff", max_backoff),
            ("fresh_ttl_seconds", fresh_ttl_seconds),
            ("pacing_seconds", pacing_seconds),
        ):
            if not _is_finite_positive(value):
                raise ValueError(
                    f"{name} must be a finite positive number, got {value!r}"
                )
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
        G3-004: the accepted Port signature is unchanged, so a stale-refresh
        failure cannot carry cache evidence through the return value — it
        therefore FAILS CLEARLY with the stale evidence in the error detail
        instead of silently serving unlabelled old data (MP §6). No parallel
        concrete-only enrichment API is provided.
        """
        key = self._query_key(candidate)
        cached = self._cache.get(key)
        now = self._clock()
        if cached is not None and cached.query_version == QUERY_VERSION and self._is_fresh(
            cached, now
        ):
            # G3-003: only entries written under the CURRENT policy version are
            # served as exact identities. A version mismatch (even under the
            # same key from a persistent backend) is stale-by-policy and forces
            # a fresh lookup under the current rules.
            return self._apply(candidate, cached)
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
        return self._apply(candidate, entry)

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
        if not self._sufficient_evidence(candidate, match):
            # G3-003: a destructive canonical identity needs corroborating
            # evidence — a compatible first-release year (when the candidate
            # year is known) AND a positive search score. Missing/malformed
            # year or absent/zero score => explicit no-match, never "exact".
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
        # G3-003: the search confidence is parsed from the provider's documented
        # representation (a decimal string such as "100", or a JSON number) into
        # ONE finite numeric domain [0, 100]. Booleans, non-finite values,
        # malformed strings and out-of-range values are malformed evidence and
        # fail through the typed source boundary — never "exact".
        score = item.get("score")
        if score is None:
            return {
                "id": canonical_id,
                "title": title,
                "artist": " ".join(names),
                "year": year,
                "score": None,
            }
        parsed = _parse_score(score)
        if parsed is None:
            raise SourceUnavailableError(
                "musicbrainz: release-group item has malformed 'score'"
            )
        return {
            "id": canonical_id,
            "title": title,
            "artist": " ".join(names),
            "year": year,
            "score": parsed,
        }

    def _matches(self, candidate: AlbumCandidate, item: dict) -> bool:
        """Strong match: normalized title AND complete artist-credit both equal."""
        return (
            normalized_text(candidate.title) == normalized_text(item["title"])
            and normalized_text(candidate.artist) == normalized_text(item["artist"])
        )

    def _sufficient_evidence(self, candidate: AlbumCandidate, item: dict) -> bool:
        """Corroboration required before a destructive canonical ID is installed.

        - When the candidate year is known, a valid, compatible first-release
          year is REQUIRED (missing/malformed year is not treated as neutral).
        - The search score must reach the named conservative threshold
          ``MIN_EXACT_SCORE`` — a strong match; weaker confidence (including
          missing/zero) never installs a canonical identity.
        """
        if candidate.year is not None and (
            item["year"] is None or item["year"] != candidate.year
        ):
            return False
        return item["score"] is not None and item["score"] >= MIN_EXACT_SCORE

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


_UA_APP_VERSION = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)/(\d[\w.+-]*)$")
_UA_CONTACT_URL = re.compile(r"^\([+]?(https?://\S+)\)$")
_UA_CONTACT_MAILTO = re.compile(r"^\([+]?mailto:([^@\s)]+)@([^@\s)]+)\)$")
_UA_CONTACT_ANGLE = re.compile(r"^<([^@\s>]+)@([^@\s>]+)>$")
_UA_CTRL = re.compile(r"[\x00-\x1f\x7f]")
_UA_ANON_APPS = frozenset({"anonymous", "anon", "bot", "app"})


def _is_contactable_user_agent(value) -> bool:
    """True when ``value`` matches the complete MusicBrainz UA shape.

    MusicBrainz requires ``Application/version (contact URL or email)``. The
    ENTIRE value is validated:

    - control characters are inspected on the ORIGINAL value BEFORE any
      normalization (leading/trailing whitespace is REJECTED, never silently
      trimmed/rewritten — CR/LF/Tab cannot hide from the header boundary);
    - a real application token ``name/version`` (``anonymous`` and friends are
      not accepted as the application identity);
    - exactly one contact field, one of:
      ``(+https://host/...)`` / ``(+http://host/...)`` with a NON-EMPTY
      ``hostname`` (userinfo-only/port-only authorities are not a host),
      ``(+mailto:user@host)`` / ``(mailto:user@host)`` or
      ``<user@host>`` with non-empty local and domain parts;
    - no trailing content after the contact field.
    """
    if not isinstance(value, str) or not value:
        return False
    # 1) Control characters / CRLF injection on the ORIGINAL value, before any
    #    trimming — a header value is never silently rewritten.
    if _UA_CTRL.search(value):
        return False
    # 2) Leading/trailing whitespace is rejected outright (no silent rewrite);
    #    the UA must be an exact, tight "app/version contact" string.
    if value != value.strip():
        return False
    parts = value.split(" ", 1)
    if len(parts) != 2:
        return False  # must be "app/version contact"
    app_version, contact = parts
    match = _UA_APP_VERSION.fullmatch(app_version)
    if match is None:
        return False  # requires an application token and a /version
    app_token = match.group(1).lower()
    if app_token in _UA_ANON_APPS:
        return False  # "anonymous" etc. are not a real application identity
    # Contact field: URL (with host) or email (non-empty local/domain).
    url_match = _UA_CONTACT_URL.fullmatch(contact)
    if url_match is not None:
        return _url_has_hostname(url_match.group(1))
    if _UA_CONTACT_MAILTO.fullmatch(contact) is not None:
        return True  # non-empty local/domain enforced by the pattern
    # Angle-bracketed email contact (non-empty local/domain enforced).
    return _UA_CONTACT_ANGLE.fullmatch(contact) is not None


def _url_has_hostname(url: str) -> bool:
    """True when an http(s) contact URL carries a real, non-empty hostname.

    ``parsed.netloc`` alone is not enough — an authority of only userinfo
    (``https://user@``) or only a port (``https://:443``) has no host. We
    require ``parsed.hostname``, and also touch ``parsed.port`` (inside the
    same guarded parse block) because ``urllib.parse`` defers port validation
    to that property: a non-numeric port (``:notaport``) or a port outside
    1–65535 (``:99999``) raises ``ValueError`` there and is treated as
    invalid (``False``). ``None``/default ports are fine.
    """
    try:
        parsed = urlparse(url)
        hostname = parsed.hostname
        _ = parsed.port  # validates non-numeric / out-of-range ports
    except ValueError:
        return False  # malformed IPv6, port, or out-of-range port
    if parsed.scheme not in ("http", "https"):
        return False
    return bool(hostname)


def _parse_score(value) -> float | None:
    """Parse a MusicBrainz search score into a finite ``[0, 100]`` float.

    Accepts the provider's documented decimal-string form (``"100"``) and JSON
    numbers; rejects booleans, non-finite values, malformed strings and
    out-of-range values. Returns ``None`` for anything unusable so callers can
    fail through the typed source boundary.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, str):
        try:
            numeric = float(value)
        except ValueError:
            return None
    elif isinstance(value, (int, float)):
        numeric = float(value)
    else:
        return None
    if numeric != numeric or numeric in (float("inf"), float("-inf")):  # NaN/±Inf
        return None
    if not (_SCORE_MIN <= numeric <= _SCORE_MAX):
        return None
    return numeric


def _to_epoch(value: str) -> float:
    """Parse an ISO 8601 timestamp (with timezone) into epoch seconds."""
    return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()


def _is_finite_positive(value: float) -> bool:
    """True when ``value`` is a real, finite, strictly positive number (G3-005)."""
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and value > 0
        and value != float("inf")
        and value != float("nan")
    )


__all__ = [
    "DEFAULT_FRESH_TTL",
    "DEFAULT_USER_AGENT",
    "EnrichmentCache",
    "EnrichmentEntry",
    "MBHttpResponse",
    "MIN_EXACT_SCORE",
    "MusicBrainzEnricher",
    "QUERY_VERSION",
    "Transport",
]
