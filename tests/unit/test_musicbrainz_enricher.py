"""G3 T3.3 — MusicBrainz enrichment adapter tests (SPEC §7-12).

Ordinary tests use a scripted fake transport + fake clock + recording sleeper;
no live network is ever touched. Covers: bounded timeout/retry/backoff, 429/5xx/
network classification, malformed JSON / missing fields / empty / ambiguity,
fresh / stale / refresh-failure cache semantics, provenance, User-Agent.
"""

from __future__ import annotations

import json

import pytest

from omda.adapters.musicbrainz import (
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

# G3-005: a contactable test User-Agent (MusicBrainz policy requires one).
TEST_USER_AGENT = "omda-test/0.1 (+https://example.invalid/omda-test)"


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
    kw.setdefault("user_agent", TEST_USER_AGENT)
    return MusicBrainzEnricher(
        transport=transport,
        clock=FixedClock(clock),
        sleeper=sleeper or RecordingSleeper(),
        cache=cache,
        **kw,
    )


def _single_ok_response(
    canonical_id="mb-release-1",
    title="Blue Train",
    artist="John Coltrane",
    first_release_date="1958-01-01",
    score=100,
) -> MBHttpResponse:
    return MBHttpResponse(
        200,
        json.dumps(
            {
                "release-groups": [
                    {
                        "id": canonical_id,
                        "title": title,
                        "artist-credit": [{"name": artist}],
                        "first-release-date": first_release_date,
                        "score": score,
                    }
                ]
            }
        ),
    )


def _empty_ok_response() -> MBHttpResponse:
    return MBHttpResponse(200, '{"release-groups": []}')


def _multi_ok_response() -> MBHttpResponse:
    # Two results that BOTH strongly match the candidate (e.g. reissues): true
    # ambiguity that must never be collapsed into one canonical ID.
    return MBHttpResponse(
        200,
        json.dumps(
            {
                "release-groups": [
                    {
                        "id": "mb-1",
                        "title": "Blue Train",
                        "artist-credit": [{"name": "John Coltrane"}],
                    },
                    {
                        "id": "mb-2",
                        "title": "Blue Train",
                        "artist-credit": [{"name": "John Coltrane"}],
                    },
                ]
            }
        ),
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
    # backoff after 429 + pacing after the successful call (G3-005)
    assert sleeper.delays == [1.0, 1.0]


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
    enricher = _enricher(transport, user_agent=TEST_USER_AGENT)
    enricher.enrich(_candidate())
    ua = transport.last_headers["User-Agent"]
    assert TEST_USER_AGENT in ua
    assert "token" not in ua.lower() and "secret" not in ua.lower()


def test_placeholder_user_agent_is_rejected() -> None:
    # G3-005: no placeholder default is offered — a live adapter MUST be given
    # an explicit contactable User-Agent at construction.
    with pytest.raises(ValueError):
        MusicBrainzEnricher(
            transport=ScriptedTransport([]),
            clock=FixedClock(AT0),
            sleeper=RecordingSleeper(),
            user_agent=None,
        )


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
            query_key=f"{QUERY_VERSION}|johncoltrane|bluetrain|1958",
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
            query_key=f"{QUERY_VERSION}|johncoltrane|bluetrain|1958",
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
    assert cache.get(f"{QUERY_VERSION}|johncoltrane|bluetrain|1958").canonical_id == "mb-fresh"


def test_stale_cache_refresh_failure_fails_clearly_with_evidence() -> None:
    # G3-004: the Port return value cannot carry cache evidence, so a stale
    # refresh failure FAILS CLEARLY with the stale evidence in the error detail
    # instead of silently serving unlabelled old data.
    cache = EnrichmentCache()
    cache.put(
        EnrichmentEntry(
            query_key=f"{QUERY_VERSION}|johncoltrane|bluetrain|1958",
            canonical_id="mb-stale",
            canonical_source="musicbrainz",
            fetched_at=AT0,
            query_version=QUERY_VERSION,
            source="musicbrainz",
        )
    )
    transport = ScriptedTransport([TimeoutError("down")])
    with pytest.raises(SourceUnavailableError) as exc:
        _enricher(transport, clock=LATER, cache=cache, max_retries=0).enrich(_candidate())
    detail = exc.value.detail
    assert detail["kind"] == "stale-refresh-failure"
    assert detail["cache_status"] == "stale"
    assert detail["fetched_at"] == AT0
    assert detail["source"] == "musicbrainz"
    assert transport.calls == 1


def test_no_cache_refresh_failure_raises_unavailable() -> None:
    transport = ScriptedTransport([TimeoutError("down")])
    with pytest.raises(SourceUnavailableError):
        _enricher(transport, max_retries=0).enrich(_candidate())


def test_cache_entry_carries_full_provenance() -> None:
    transport = ScriptedTransport([_single_ok_response("mb-p")])
    cache = EnrichmentCache()
    _enricher(transport, clock=AT0, cache=cache).enrich(_candidate())
    entry = cache.get(f"{QUERY_VERSION}|johncoltrane|bluetrain|1958")
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


# --- G3-003 re-review: exact identity requires real matching evidence ----------


def test_unrelated_single_result_is_not_exact() -> None:
    # Reviewer counter-example: one fabricated result for a DIFFERENT album must
    # never install a canonical identity with confidence "exact".
    transport = ScriptedTransport(
        [_single_ok_response("WRONG", title="Unrelated Album", artist="Other Artist")]
    )
    enriched = _enricher(transport).enrich(_candidate())
    assert enriched.identity is None  # no-match: no canonical ID installed


def test_same_title_different_artist_is_not_exact() -> None:
    transport = ScriptedTransport(
        [_single_ok_response("mb-x", title="Blue Train", artist="Someone Else")]
    )
    enriched = _enricher(transport).enrich(_candidate())
    assert enriched.identity is None


def test_conflicting_year_prevents_exact() -> None:
    # Same title+artist but conflicting first-release year: corroboration fails,
    # so no destructive canonical identity may be installed.
    transport = ScriptedTransport(
        [
            _single_ok_response(
                "mb-x",
                title="Blue Train",
                artist="John Coltrane",
                first_release_date="1999-01-01",
            )
        ]
    )
    enriched = _enricher(transport).enrich(_candidate())  # candidate year 1958
    assert enriched.identity is None


def test_malformed_list_item_is_unavailable() -> None:
    # A response item without title/artist evidence is malformed -> domain error.
    transport = ScriptedTransport(
        [MBHttpResponse(200, json.dumps({"release-groups": [{"id": "mb-no-title"}]}))]
    )
    with pytest.raises(SourceUnavailableError):
        _enricher(transport).enrich(_candidate())


def test_multiple_plausible_matches_are_ambiguous() -> None:
    # Two results that both match title+artist (e.g. reissues) -> ambiguity is
    # never silently collapsed into one canonical ID.
    body = json.dumps(
        {
            "release-groups": [
                {
                    "id": "mb-1",
                    "title": "Blue Train",
                    "artist-credit": [{"name": "John Coltrane"}],
                },
                {
                    "id": "mb-2",
                    "title": "Blue Train",
                    "artist-credit": [{"name": "John Coltrane"}],
                },
            ]
        }
    )
    transport = ScriptedTransport([MBHttpResponse(200, body)])
    enriched = _enricher(transport).enrich(_candidate())
    assert enriched.identity is None


def test_genuinely_exact_match_sets_exact() -> None:
    transport = ScriptedTransport([_single_ok_response("mb-release-1")])
    enriched = _enricher(transport).enrich(_candidate())
    assert enriched.identity is not None
    assert enriched.identity.canonical_id == "mb-release-1"
    assert enriched.identity.identity_confidence == "exact"


# --- G3-005/G3-006 re-review: pacing and bounded cache --------------------------


def test_consecutive_successful_calls_are_paced() -> None:
    # G3-005: client-side pacing applies to EVERY successful call, not just
    # retry backoff — consecutive lookups never exceed ~1 req/s.
    sleeper = RecordingSleeper()
    transport = ScriptedTransport([_single_ok_response("m1"), _single_ok_response("m2")])
    enricher = MusicBrainzEnricher(
        transport=transport,
        clock=FixedClock(AT0),
        sleeper=sleeper,
        user_agent=TEST_USER_AGENT,
        pacing_seconds=1.0,
    )
    enricher.enrich(_candidate(album_id="a", title="Blue Train"))
    enricher.enrich(_candidate(album_id="b", title="Giant Steps"))
    assert transport.calls == 2
    assert sleeper.delays == [1.0, 1.0]  # one pacing sleep per successful call


@pytest.mark.parametrize(
    "bad",
    [0, -1, float("inf"), float("nan"), None, "one"],
    ids=["zero", "negative", "inf", "nan", "none", "string"],
)
def test_non_finite_or_zero_pacing_rejected(bad) -> None:
    # G3-005: pacing must be finite and strictly positive — zero/NaN/infinity
    # would disable the promised 1-req/s bound.
    with pytest.raises(ValueError):
        MusicBrainzEnricher(
            transport=ScriptedTransport([_single_ok_response("m1")]),
            clock=FixedClock(AT0),
            sleeper=RecordingSleeper(),
            user_agent=TEST_USER_AGENT,
            pacing_seconds=bad,
        )


def test_enrichment_cache_evicts_oldest_entries() -> None:
    # G3-006: capacity is bounded with deterministic FIFO eviction.
    cache = EnrichmentCache(max_entries=2)
    cache.put(
        EnrichmentEntry("k1", "mb-1", "musicbrainz", AT0, QUERY_VERSION, "musicbrainz")
    )
    cache.put(
        EnrichmentEntry("k2", "mb-2", "musicbrainz", AT0, QUERY_VERSION, "musicbrainz")
    )
    cache.put(
        EnrichmentEntry("k3", "mb-3", "musicbrainz", AT0, QUERY_VERSION, "musicbrainz")
    )
    assert cache.get("k1") is None  # oldest evicted
    assert cache.get("k2") is not None
    assert cache.get("k3") is not None


# --- G3-003 re-review 1: year/score corroboration before exact ------------------


def test_missing_year_prevents_exact_when_candidate_year_known() -> None:
    # Candidate year is known (1958); the item has NO first-release-date and a
    # positive score — missing corroboration is NOT neutral, so no destructive ID.
    transport = ScriptedTransport(
        [_single_ok_response("mb-self", first_release_date=None)]
    )
    enriched = _enricher(transport).enrich(_candidate())
    assert enriched.identity is None


def test_malformed_year_prevents_exact() -> None:
    # first-release-date="unknown" is unusable corroboration -> no exact.
    transport = ScriptedTransport(
        [_single_ok_response("mb-self", first_release_date="unknown")]
    )
    enriched = _enricher(transport).enrich(_candidate())
    assert enriched.identity is None


def test_missing_score_prevents_exact() -> None:
    # Matching title/artist/year but NO search score: evidence insufficient.
    transport = ScriptedTransport(
        [_single_ok_response("mb-self", score=None)]
    )
    enriched = _enricher(transport).enrich(_candidate())
    assert enriched.identity is None


def test_zero_score_prevents_exact() -> None:
    transport = ScriptedTransport([_single_ok_response("mb-self", score=0)])
    enriched = _enricher(transport).enrich(_candidate())
    assert enriched.identity is None


def test_malformed_score_is_unavailable() -> None:
    body = json.dumps(
        {
            "release-groups": [
                {
                    "id": "mb-x",
                    "title": "Blue Train",
                    "artist-credit": [{"name": "John Coltrane"}],
                    "first-release-date": "1958-01-01",
                    "score": "high",
                }
            ]
        }
    )
    transport = ScriptedTransport([MBHttpResponse(200, body)])
    with pytest.raises(SourceUnavailableError):
        _enricher(transport).enrich(_candidate())


def test_fully_corroborated_self_titled_exact() -> None:
    # Self-titled album with matching year AND positive score: exact is safe.
    transport = ScriptedTransport(
        [
            _single_ok_response(
                "mb-weezer", title="Weezer", artist="Weezer", first_release_date="1994-01-01"
            )
        ]
    )
    candidate = _candidate(album_id="w1", title="Weezer", artist="Weezer", year=1994)
    enriched = _enricher(transport).enrich(candidate)
    assert enriched.identity is not None
    assert enriched.identity.canonical_id == "mb-weezer"
    assert enriched.identity.identity_confidence == "exact"



@pytest.mark.parametrize(
    "bad",
    [0, -1, float("inf"), float("nan"), None, True],
    ids=["zero", "negative", "inf", "nan", "none", "bool"],
)
def test_non_finite_timeout_rejected(bad) -> None:
    # G3-005: connect/read timeouts, backoff and TTL must be finite and positive.
    with pytest.raises(ValueError):
        MusicBrainzEnricher(
            transport=ScriptedTransport([]),
            clock=FixedClock(AT0),
            sleeper=RecordingSleeper(),
            user_agent=TEST_USER_AGENT,
            connect_timeout=bad,
        )


# --- G3-003 re-review 2: provider-shaped string score + conservative threshold --


def test_provider_shaped_string_score_is_accepted() -> None:
    # MusicBrainz documents search score as a DECIMAL STRING ("100"). A real
    # provider-shaped result must enrich, not fail as "malformed score".
    body = json.dumps(
        {
            "release-groups": [
                {
                    "id": "mb-100",
                    "title": "Blue Train",
                    "artist-credit": [{"name": "John Coltrane"}],
                    "first-release-date": "1958-01-01",
                    "score": "100",
                }
            ]
        }
    )
    enriched = _enricher(ScriptedTransport([MBHttpResponse(200, body)])).enrich(
        _candidate()
    )
    assert enriched.identity is not None
    assert enriched.identity.canonical_id == "mb-100"
    assert enriched.identity.identity_confidence == "exact"


@pytest.mark.parametrize(
    "low",
    ["10", 0.01, 89],
    ids=["string-10", "tiny-numeric", "below-threshold"],
)
def test_low_score_never_installs_exact(low) -> None:
    # Conservative threshold: a destructive canonical ID requires a STRONG search
    # match; weak confidence must never become the permanent exclusion key.
    body = json.dumps(
        {
            "release-groups": [
                {
                    "id": "mb-low",
                    "title": "Blue Train",
                    "artist-credit": [{"name": "John Coltrane"}],
                    "first-release-date": "1958-01-01",
                    "score": low,
                }
            ]
        }
    )
    enriched = _enricher(ScriptedTransport([MBHttpResponse(200, body)])).enrich(
        _candidate()
    )
    assert enriched.identity is None


def test_boundary_score_exactly_at_threshold_is_accepted() -> None:
    from omda.adapters.musicbrainz import MIN_EXACT_SCORE

    body = json.dumps(
        {
            "release-groups": [
                {
                    "id": "mb-boundary",
                    "title": "Blue Train",
                    "artist-credit": [{"name": "John Coltrane"}],
                    "first-release-date": "1958-01-01",
                    "score": str(MIN_EXACT_SCORE),
                }
            ]
        }
    )
    enriched = _enricher(ScriptedTransport([MBHttpResponse(200, body)])).enrich(
        _candidate()
    )
    assert enriched.identity is not None
    assert enriched.identity.canonical_id == "mb-boundary"


@pytest.mark.parametrize(
    "bad",
    [float("nan"), float("inf"), float("-inf")],
    ids=["nan", "inf", "neg-inf"],
)
def test_non_finite_score_is_rejected(bad) -> None:
    # NaN/Infinity must fail through the typed source boundary, never pass a
    # positivity check (NaN <= 0 is False in Python).
    body = json.dumps(
        {
            "release-groups": [
                {
                    "id": "mb-nf",
                    "title": "Blue Train",
                    "artist-credit": [{"name": "John Coltrane"}],
                    "first-release-date": "1958-01-01",
                    "score": bad,
                }
            ]
        }
    )
    with pytest.raises(SourceUnavailableError):
        _enricher(ScriptedTransport([MBHttpResponse(200, body)])).enrich(_candidate())


@pytest.mark.parametrize(
    "bad",
    [True, False, "high", "1O0", "-5", "101", "abc", []],
    ids=[
        "bool-true",
        "bool-false",
        "word",
        "letter-o",
        "negative-string",
        "over-100",
        "word2",
        "list",
    ],
)
def test_malformed_or_out_of_range_score_rejected(bad) -> None:
    # Booleans, non-numeric strings, out-of-range values and wrong types are
    # malformed confidence evidence -> typed source failure (never "exact").
    body = json.dumps(
        {
            "release-groups": [
                {
                    "id": "mb-bad",
                    "title": "Blue Train",
                    "artist-credit": [{"name": "John Coltrane"}],
                    "first-release-date": "1958-01-01",
                    "score": bad,
                }
            ]
        }
    )
    with pytest.raises(SourceUnavailableError):
        _enricher(ScriptedTransport([MBHttpResponse(200, body)])).enrich(_candidate())


@pytest.mark.parametrize(
    "bad",
    [True, 1.5, float("nan"), float("inf"), -1, "3"],
    ids=["bool", "fractional", "nan", "inf", "negative", "string"],
)
def test_max_retries_must_be_non_negative_integer(bad) -> None:
    # G3-005: max_retries is an INTEGER count — booleans, fractions, non-finite
    # values, strings and negatives must fail at construction, never leak a raw
    # TypeError from range()/comparisons later.
    with pytest.raises(ValueError):
        MusicBrainzEnricher(
            transport=ScriptedTransport([]),
            clock=FixedClock(AT0),
            sleeper=RecordingSleeper(),
            user_agent="omda-test/0.1 (+https://example.invalid/contact)",
            max_retries=bad,
        )


@pytest.mark.parametrize(
    "bad",
    [True, 1.5, float("nan"), float("inf"), 0, -1],
    ids=["bool", "fractional", "nan", "inf", "zero", "negative"],
)
def test_enrichment_cache_max_entries_must_be_positive_integer(bad) -> None:
    # G3-006: NaN/Infinity/fractions/booleans would disable the capacity bound.
    with pytest.raises(ValueError):
        EnrichmentCache(max_entries=bad)


# --- G3-003 re-review 3: cache policy version invalidates weaker entries ---------


def test_old_version_cache_entry_does_not_bypass_threshold() -> None:
    # Reviewer counter-example: a canonical ID accepted by the PREVIOUS weak
    # rule (any positive score) must NOT be served as "exact" from a fresh
    # cache hit under the current 90-point policy — the policy change must
    # invalidate the old cache namespace and force a current lookup.
    transport = ScriptedTransport([_single_ok_response("mb-current")])
    cache = EnrichmentCache()
    # Seed the OLD "v1" namespace with an entry the old rule accepted (weak
    # evidence), as if produced before the threshold repair.
    cache.put(
        EnrichmentEntry(
            query_key="v1|johncoltrane|bluetrain|1958",
            canonical_id="pre-threshold-id",
            canonical_source="musicbrainz",
            fetched_at=AT0,
            query_version="v1",
            source="musicbrainz",
        )
    )
    enricher = _enricher(transport, clock=AT0, cache=cache)
    enriched = enricher.enrich(_candidate())
    # The old-version entry is NOT served: a current lookup happened instead.
    assert enriched.identity is not None
    assert enriched.identity.canonical_id == "mb-current"
    assert transport.calls == 1


def test_old_version_cache_entry_is_never_served_directly() -> None:
    # Even when the current lookup FAILS, an old-version entry must not become
    # an "exact" canonical identity — version mismatch means stale-by-policy.
    transport = ScriptedTransport([TimeoutError("down")])
    cache = EnrichmentCache()
    cache.put(
        EnrichmentEntry(
            query_key="v1|johncoltrane|bluetrain|1958",
            canonical_id="pre-threshold-id",
            canonical_source="musicbrainz",
            fetched_at=AT0,
            query_version="v1",
            source="musicbrainz",
        )
    )
    with pytest.raises(SourceUnavailableError):
        _enricher(transport, clock=LATER, cache=cache, max_retries=0).enrich(_candidate())


def test_same_key_old_query_version_entry_is_not_served() -> None:
    # Defensive: even a current-key entry whose query_version field is stale
    # (e.g. injected by a buggy persistent backend) must NOT serve as exact.
    transport = ScriptedTransport([_single_ok_response("mb-current")])
    cache = EnrichmentCache()
    cache.put(
        EnrichmentEntry(
            query_key=f"{QUERY_VERSION}|johncoltrane|bluetrain|1958",
            canonical_id="pre-threshold-id",
            canonical_source="musicbrainz",
            fetched_at=AT0,
            query_version="v1",
            source="musicbrainz",
        )
    )
    enricher = _enricher(transport, clock=AT0, cache=cache)
    enriched = enricher.enrich(_candidate())
    assert enriched.identity is not None
    assert enriched.identity.canonical_id == "mb-current"
    assert transport.calls == 1


# --- G3-005 re-review 3: contactable User-Agent shape is validated -------------


@pytest.mark.parametrize(
    "bad",
    ["x", "omda/0.1", "not contactable", "anonymous/1.0", "app/1.0 (no contact)"],
    ids=["single-char", "no-contact", "nonsense", "anonymous", "no-contact-parens"],
)
def test_non_contactable_user_agent_rejected(bad) -> None:
    # G3-005: an explicit value alone is NOT enough — MusicBrainz requires a
    # contactable identity (Application/version (contact URL or email)).
    with pytest.raises(ValueError):
        MusicBrainzEnricher(
            transport=ScriptedTransport([]),
            clock=FixedClock(AT0),
            sleeper=RecordingSleeper(),
            user_agent=bad,
        )


@pytest.mark.parametrize(
    "good",
    [
        "omda-test/0.1 (+https://example.invalid/omda-test)",
        "omda/1.0 (+mailto:omda@example.org)",
        "omda/1.0 <maintainer@example.org>",
    ],
    ids=["url", "mailto", "email-angle"],
)
def test_contactable_user_agent_accepted(good) -> None:
    # Application/version with a contact URL or email is a valid UA.
    enricher = MusicBrainzEnricher(
        transport=ScriptedTransport([_single_ok_response()]),
        clock=FixedClock(AT0),
        sleeper=RecordingSleeper(),
        user_agent=good,
    )
    enricher.enrich(_candidate())
    assert enricher is not None


# --- G3-005 re-review 4: complete User-Agent shape validation ------------------


@pytest.mark.parametrize(
    "bad",
    [
        "x(+https://)",  # no app/version separation, empty URL
        "x <@>",  # empty local part and domain
        "anonymous/1.0 (+https://)",  # anonymous app token + empty contact
        "app (+mailto:)",  # no version, empty mailbox
        "app/1 (+https://example.org)\r\nX-Test: injected",  # trailing CRLF/header
        "app/1 (+https://example.org)\nX-Test: injected",  # trailing LF/header
        "app/1\r\nX-Test: injected (+https://example.org)",  # CRLF before contact
        "app/1 (+https://)",  # http(s) URL without hostname
        "app/1 (+mailto:@example.org)",  # mailto empty local part
        "app/1 <@example.org>",  # angle-email empty local part
        "app/1 <user@>",  # angle-email empty domain
    ],
    ids=[
        "no-app-version-empty-url",
        "empty-angle-email",
        "anonymous-empty-contact",
        "no-version-empty-mailto",
        "trailing-crlf",
        "trailing-lf",
        "crlf-before-contact",
        "https-no-host",
        "mailto-empty-local",
        "angle-empty-local",
        "angle-empty-domain",
    ],
)
def test_incomplete_or_unsafe_user_agent_rejected(bad) -> None:
    # G3-005: the WHOLE UA value must be validated — control characters/CRLF,
    # missing application/version, empty contacts and "anonymous" app tokens
    # are rejected at the configuration boundary.
    with pytest.raises(ValueError):
        MusicBrainzEnricher(
            transport=ScriptedTransport([]),
            clock=FixedClock(AT0),
            sleeper=RecordingSleeper(),
            user_agent=bad,
        )


# --- G3-005 re-review 5: untrimmed controls + hostname-only URL validation -------


@pytest.mark.parametrize(
    "bad",
    [
        "omda/1 (+https://example.org)\r\n",  # trailing CRLF
        "\nomda/1 (+https://example.org)",  # leading LF
        "\tomda/1 (+https://example.org)\t",  # leading/trailing tab
        "omda/1 (+https://@)",  # userinfo-only authority, no host
        "omda/1 (+https://user@)",  # userinfo-only authority, no host
        "omda/1 (+https://:443)",  # port-only authority, no host
    ],
    ids=[
        "trailing-crlf",
        "leading-lf",
        "leading-trailing-tab",
        "userinfo-only",
        "userinfo-only-named",
        "port-only",
    ],
)
def test_untrimmed_controls_and_hostless_url_rejected(bad) -> None:
    # G3-005: control characters are checked on the ORIGINAL untrimmed value
    # (no silent header rewriting), and a contact URL needs a real hostname —
    # userinfo-only/port-only authorities are NOT a host.
    with pytest.raises(ValueError):
        MusicBrainzEnricher(
            transport=ScriptedTransport([]),
            clock=FixedClock(AT0),
            sleeper=RecordingSleeper(),
            user_agent=bad,
        )
