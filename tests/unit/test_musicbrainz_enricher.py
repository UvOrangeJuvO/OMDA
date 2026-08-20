"""G3 T3.3 — MusicBrainz enrichment adapter tests (SPEC §7-12).

Ordinary tests use a scripted fake transport + fake clock + recording sleeper;
no live network is ever touched. Covers: bounded timeout/retry/backoff, 429/5xx/
network classification, malformed JSON / missing fields / empty / ambiguity,
fresh / stale / refresh-failure cache semantics, provenance, User-Agent.
"""

from __future__ import annotations

import pytest

from omda.adapters.musicbrainz import (
    DEFAULT_USER_AGENT,
    QUERY_VERSION,
    EnrichmentCache,
    EnrichmentEntry,
    MBHttpResponse,
    MusicBrainzEnricher,
)
from omda.ports.domain import AlbumCandidate
from omda.ports.errors import SourceUnavailableError

AT0 = "2026-08-20T00:00:00+00:00"
AT1 = "2026-08-21T00:00:00+00:00"
LATER = "2026-09-01T00:00:00+00:00"  # > 7 days after AT0


def _candidate(album_id="a-1", title="Blue Train", artist="John Coltrane", year=1958):
    return AlbumCandidate(album_id=album_id, title=title, artist=artist, year=year)


class ScriptedTransport:
    """Serves a script of responses/exceptions per call; records headers/timeout."""

    def __init__(self, script):
        self.script = script
        self.calls = 0
        self.last_headers = None
        self.last_timeout = None

    def get(self, url, params=None, headers=None, timeout=None):
        step = self.script[min(self.calls, len(self.script) - 1)]
        self.calls += 1
        self.last_headers = headers
        self.last_timeout = timeout
        if isinstance(step, Exception):
            raise step
        return step


class FixedClock:
    def __init__(self, value=AT0):
        self.value = value

    def __call__(self):
        return self.value


class RecordingSleeper:
    def __init__(self):
        self.delays = []

    def __call__(self, seconds):
        self.delays.append(seconds)


def _enricher(transport, clock=AT0, sleeper=None, cache=None, **kw):
    return MusicBrainzEnricher(
        transport=transport,
        clock=FixedClock(clock),
        sleeper=sleeper or RecordingSleeper(),
        cache=cache,
        **kw,
    )


def _single_ok_response(canonical_id="mb-release-1") -> MBHttpResponse:
    return MBHttpResponse(
        200,
        f'{{"release-groups": [{{"id": "{canonical_id}", "title": "Blue Train"}}]}}',
    )


def _empty_ok_response() -> MBHttpResponse:
    return MBHttpResponse(200, '{"release-groups": []}')


def _multi_ok_response() -> MBHttpResponse:
    return MBHttpResponse(
        200, '{"release-groups": [{"id": "mb-1"}, {"id": "mb-2"}]}'
    )


# --- happy paths --------------------------------------------------------------


def test_single_result_sets_exact_canonical_identity() -> None:
    transport = ScriptedTransport([_single_ok_response()])
    enricher = _enricher(transport)
    enriched = enricher.enrich(_candidate())
    assert enriched.identity is not None
    assert enriched.identity.canonical_id == "mb-release-1"
    assert enriched.identity.canonical_source == "musicbrainz"
    assert enriched.identity.identity_confidence == "exact"
    assert transport.calls == 1


def test_empty_result_leaves_identity_unknown() -> None:
    transport = ScriptedTransport([_empty_ok_response()])
    enriched = _enricher(transport).enrich(_candidate())
    assert enriched.identity is None


def test_ambiguous_multi_result_never_guesses() -> None:
    transport = ScriptedTransport([_multi_ok_response()])
    enriched = _enricher(transport).enrich(_candidate())
    # Ambiguity is not silently collapsed: no canonical identity is claimed.
    assert enriched.identity is None
    assert transport.calls == 1


def test_missing_release_groups_field_is_unavailable() -> None:
    transport = ScriptedTransport([MBHttpResponse(200, '{"count": 1}')])
    with pytest.raises(SourceUnavailableError):
        _enricher(transport).enrich(_candidate())


def test_malformed_json_is_unavailable() -> None:
    transport = ScriptedTransport([MBHttpResponse(200, "{not json")])
    with pytest.raises(SourceUnavailableError):
        _enricher(transport).enrich(_candidate())


# --- bounded network behaviour -------------------------------------------------


def test_network_timeout_retries_then_fails_unavailable() -> None:
    transport = ScriptedTransport([TimeoutError("connect")])
    sleeper = RecordingSleeper()
    with pytest.raises(SourceUnavailableError):
        _enricher(transport, sleeper=sleeper, max_retries=3, base_delay=0.01).enrich(
            _candidate()
        )
    assert transport.calls == 4  # 1 + max_retries
    assert len(sleeper.delays) == 3  # backoff between attempts


def test_429_retries_with_backoff_then_fails_unavailable() -> None:
    transport = ScriptedTransport([MBHttpResponse(429, "{}"), MBHttpResponse(429, "{}")])
    sleeper = RecordingSleeper()
    with pytest.raises(SourceUnavailableError):
        _enricher(transport, sleeper=sleeper, max_retries=1, base_delay=1.0).enrich(
            _candidate()
        )
    assert transport.calls == 2
    assert sleeper.delays == [1.0]  # exponential backoff base * 2^0


def test_5xx_retries_then_fails_unavailable() -> None:
    transport = ScriptedTransport([MBHttpResponse(503, "{}"), MBHttpResponse(503, "{}")])
    with pytest.raises(SourceUnavailableError):
        _enricher(transport, max_retries=1, base_delay=0.01).enrich(_candidate())
    assert transport.calls == 2


def test_transient_429_then_success() -> None:
    transport = ScriptedTransport(
        [MBHttpResponse(429, "{}"), _single_ok_response("mb-ok")]
    )
    sleeper = RecordingSleeper()
    enriched = _enricher(transport, sleeper=sleeper, max_retries=2, base_delay=1.0).enrich(
        _candidate()
    )
    assert enriched.identity is not None and enriched.identity.canonical_id == "mb-ok"
    assert transport.calls == 2
    assert sleeper.delays == [1.0]


def test_non_retryable_status_fails_immediately() -> None:
    transport = ScriptedTransport([MBHttpResponse(403, "{}")])
    with pytest.raises(SourceUnavailableError):
        _enricher(transport).enrich(_candidate())
    assert transport.calls == 1


def test_404_is_empty_result_not_error() -> None:
    transport = ScriptedTransport([MBHttpResponse(404, "{}")])
    enriched = _enricher(transport).enrich(_candidate())
    assert enriched.identity is None


def test_user_agent_is_configured_and_secret_free() -> None:
    transport = ScriptedTransport([_single_ok_response()])
    enricher = _enricher(transport, user_agent=DEFAULT_USER_AGENT)
    enricher.enrich(_candidate())
    ua = transport.last_headers["User-Agent"]
    assert DEFAULT_USER_AGENT in ua
    assert "token" not in ua.lower() and "secret" not in ua.lower()


def test_timeout_tuple_is_bounded() -> None:
    transport = ScriptedTransport([_single_ok_response()])
    _enricher(transport, connect_timeout=5.0, read_timeout=10.0).enrich(_candidate())
    connect, read = transport.last_timeout
    assert connect == 5.0 and read == 10.0


# --- cache semantics -----------------------------------------------------------


def test_fresh_cache_short_circuits_transport() -> None:
    cache = EnrichmentCache()
    cache.put(
        EnrichmentEntry(
            query_key="v1|johncoltrane|bluetrain|1958",
            canonical_id="mb-cached",
            canonical_source="musicbrainz",
            fetched_at=AT0,
            query_version=QUERY_VERSION,
            source="musicbrainz",
        )
    )
    transport = ScriptedTransport([_single_ok_response("mb-would-be")]
    )  # must NOT be called
    enriched = _enricher(transport, clock=AT1, cache=cache).enrich(_candidate())
    assert enriched.identity is not None and enriched.identity.canonical_id == "mb-cached"
    assert transport.calls == 0


def test_stale_cache_refreshes_with_new_data() -> None:
    cache = EnrichmentCache()
    cache.put(
        EnrichmentEntry(
            query_key="v1|johncoltrane|bluetrain|1958",
            canonical_id="mb-stale",
            canonical_source="musicbrainz",
            fetched_at=AT0,
            query_version=QUERY_VERSION,
            source="musicbrainz",
        )
    )
    transport = ScriptedTransport([_single_ok_response("mb-fresh")])
    enriched = _enricher(transport, clock=LATER, cache=cache).enrich(_candidate())
    assert enriched.identity is not None and enriched.identity.canonical_id == "mb-fresh"
    assert transport.calls == 1  # refresh did query
    assert cache.get("v1|johncoltrane|bluetrain|1958").canonical_id == "mb-fresh"


def test_stale_cache_refresh_failure_degrades_explicitly() -> None:
    cache = EnrichmentCache()
    cache.put(
        EnrichmentEntry(
            query_key="v1|johncoltrane|bluetrain|1958",
            canonical_id="mb-stale",
            canonical_source="musicbrainz",
            fetched_at=AT0,
            query_version=QUERY_VERSION,
            source="musicbrainz",
        )
    )
    transport = ScriptedTransport([TimeoutError("down")])
    # Refresh fails -> explicit stale degradation (no blind re-query, no error).
    enriched = _enricher(transport, clock=LATER, cache=cache, max_retries=0).enrich(
        _candidate()
    )
    assert enriched.identity is not None and enriched.identity.canonical_id == "mb-stale"
    assert transport.calls == 1


def test_no_cache_refresh_failure_raises_unavailable() -> None:
    transport = ScriptedTransport([TimeoutError("down")])
    with pytest.raises(SourceUnavailableError):
        _enricher(transport, max_retries=0).enrich(_candidate())


def test_cache_entry_carries_full_provenance() -> None:
    transport = ScriptedTransport([_single_ok_response("mb-p")])
    cache = EnrichmentCache()
    _enricher(transport, clock=AT0, cache=cache).enrich(_candidate())
    entry = cache.get("v1|johncoltrane|bluetrain|1958")
    assert entry is not None
    assert entry.source == "musicbrainz"
    assert entry.fetched_at == AT0
    assert entry.query_version == QUERY_VERSION
    assert entry.canonical_source == "musicbrainz"


def test_enrichment_is_per_candidate_not_batch() -> None:
    # One candidate, one query: no bulk/batch enrichment behaviour. Distinct
    # candidates (different normalized keys) each trigger exactly one query.
    transport = ScriptedTransport([_single_ok_response("mb-1"), _single_ok_response("mb-2")])
    enricher = _enricher(transport)
    enricher.enrich(_candidate(album_id="x", title="Blue Train"))
    enricher.enrich(_candidate(album_id="y", title="Giant Steps"))
    assert transport.calls == 2  # exactly one query per candidate
