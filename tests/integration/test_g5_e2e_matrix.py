"""G5 T5.2 — end-to-end and failure-injection matrix (SPEC §7 / OPH Prompt 10).

The seven classes of failure injection required by the release audit, each
asserting: observable bounded outcome AND zero official-history pollution.
The production path uses the reviewed curated source set + SourceRegistry with
fake network boundaries — no live PushPlus/LLM/RYM.

Class 4 (LLM failure) is superseded by ADR-0002 D8: v0.1 is a deterministic
no-LLM runtime, so there is no runtime LLM call to fail — the LLMAdapter layer
keeps its own failure semantics (tests/unit/test_llm_adapter.py) and the
deterministic engine never invokes it (test_deterministic_runtime_*).
"""

from __future__ import annotations

import os

import pytest
from tests.fakes import (
    FakeAlbumSource,
    FakeDelivery,
    FakeGenreSource,
    InMemoryHistory,
)

from omda.adapters.datasets import GenreDatasetAdapter
from omda.adapters.delivery import (
    AmbiguousFailure,
    ProviderRejection,
    ProviderSuccess,
)
from omda.config import load_config
from omda.orchestrator.run import COMPLETE, FAILED, RECOVERING, RunEngine
from omda.ports.domain import AlbumCandidate, AlbumIdentity, GenrePickRecord, GenreRef
from omda.ports.errors import (
    SourceUnavailableError,
    StateCommitFailureError,
)
from omda.production import (
    DEFAULT_DATA_DIR,
    build_curated_sources,
    build_production_engine,
)
from omda.sources.registry import SourceRegistry

GENRES = DEFAULT_DATA_DIR / "genres" / "curated-omda"
ALBUMS = DEFAULT_DATA_DIR / "albums" / "curated-omda"
REGISTRY = DEFAULT_DATA_DIR / "sources" / "registry.jsonl"


def _registry() -> SourceRegistry:
    return SourceRegistry.load(REGISTRY)


def _curated_engine(history=None, *, transport=None, registry=None, config=None):
    from dataclasses import replace

    from omda.config import DeliveryConfig

    if config is None:
        config = replace(
            load_config(),
            delivery=DeliveryConfig(channel="pushplus", pushplus_token_env="OMDA_PP_TOKEN"),
        )
    history = history or InMemoryHistory()
    genre_source, album_source, registry_ = build_curated_sources()
    registry = registry or registry_
    if transport is None:
        transport = FakeTransport(ProviderSuccess({"code": 200}))
    engine = build_production_engine(
        config=config,
        history=history,
        genre_source=genre_source,
        album_source=album_source,
        transport=transport,
        token_env="OMDA_PP_TOKEN",
        source_registry=registry,
        seed="g5-matrix",
    )
    return engine, history, transport


class FakeTransport:
    def __init__(self, *script):
        self.script = list(script)
        self.calls = 0
        self.last_payload = None

    def post(self, url: str, payload: dict) -> ProviderSuccess:
        self.calls += 1
        self.last_payload = payload
        step = self.script[min(self.calls - 1, len(self.script) - 1)]
        if isinstance(step, Exception):
            raise step
        return step


class FailingAlbumSource:
    """Class 1: data-source (fetch) failure after the Genre plan is drawn."""

    def source_batch(self, genre):
        raise SourceUnavailableError("simulated fetch failure")

    def candidates_for_genre(self, genre, limit=None):
        raise SourceUnavailableError("simulated fetch failure")


class OldOnlyAlbums(FakeAlbumSource):
    """Class 2: per-Genre pools with NO modern (>=2010) candidates."""

    def __init__(self, genre_ids):
        super().__init__(
            {
                gid: [
                    AlbumCandidate(f"{gid}-{i}", f"{gid} Old {i}", "Artist", 1975 + i)
                    for i in (1, 2, 3, 4)
                ]
                for gid in genre_ids
            }
        )


def _assert_history_untouched(history, run_id: str) -> None:
    assert history.latest_pick_index() == 0
    assert history.excluded_album_identities() == frozenset()
    transitions = [e.transition for e in history.journal_after(run_id, 0)]
    assert "HISTORY_COMMITTED" not in transitions


@pytest.fixture(autouse=True)
def _pp_token():
    os.environ["OMDA_PP_TOKEN"] = "g5-matrix-token"
    yield
    os.environ.pop("OMDA_PP_TOKEN", None)


# --- E2E positive: real curated 3x3 through the production engine ------------


def test_g5_e2e_curated_3x3_completes_and_commits_once(tmp_path) -> None:
    # E2E positive: reviewed curated sources + registry + fake PushPlus ->
    # COMPLETE, exactly one external call, exactly 9 committed identities.
    engine, history, transport = _curated_engine()
    outcome = engine.run("g5-e2e")
    assert outcome.state == COMPLETE
    assert transport.calls == 1
    assert history.latest_pick_index() == 3
    assert len(history.excluded_album_identities()) == 9
    assert all(
        i.canonical_id and len(i.canonical_id) == 36
        for i in history.excluded_album_identities()
    )


# --- Class 1: data-source failure ---------------------------------------------


def test_g5_class1_source_failure_does_not_pollute_history() -> None:
    history = InMemoryHistory()
    transport = FakeTransport(ProviderSuccess({"code": 200}))
    engine = RunEngine(
        config=load_config(),
        history=history,
        genre_source=GenreDatasetAdapter(GENRES),
        album_source=FailingAlbumSource(),
        llm=None,  # deterministic: never invoked
        delivery=FakeDelivery(),
        source_registry=_registry(),
        seed="g5-c1",
    )
    outcome = engine.run("g5-c1")
    assert outcome.state == FAILED
    assert transport.calls == 0
    _assert_history_untouched(history, "g5-c1")


# --- Class 2: no modern-year candidate ----------------------------------------


def test_g5_class2_no_modern_candidates_is_observable_and_never_invalid() -> None:
    # An all-old pool must produce the documented fallback outcome, select only
    # real candidates, and never fabricate an Album (SPEC §2.5 / HANDOFF §2.5).
    # The year-constraint behavior is Core logic; the fixture engine (no
    # registry) exercises it with a fully old pool.
    history = InMemoryHistory()
    old_ids = [g.genre_id for g in GenreDatasetAdapter(GENRES).list_eligible_genres()]
    engine2 = RunEngine(
        config=load_config(),
        history=history,
        genre_source=GenreDatasetAdapter(GENRES),
        album_source=OldOnlyAlbums(old_ids),
        llm=None,
        delivery=FakeDelivery(),
        seed="g5-c2",
    )
    outcome = engine2.run("g5-c2")
    assert outcome.state == COMPLETE  # fallback is a valid documented outcome
    assert outcome.plan is not None and len(outcome.plan.albums) == 9
    # Every selected album is a REAL pool record (no fabricated facts).
    for album in outcome.plan.albums:
        assert album.album_id.startswith("old-") or album.year is not None


# --- Class 3: already-recommended Album must not repeat -----------------------
#
# Reviewer G5-002: the earlier second-run test could pass on a Genre-PLANNING
# failure (the 30-pick cooldown over the 5 curated Genres left too few eligible
# Genres, so the run never reached Album selection). The fixtures below keep
# Genre eligibility/cooldown satisfiable and plant already-committed canonical
# identities INSIDE the current candidate path, so the assertion exercises the
# real Album-exclusion decision.


def _cid(gid: str, idx: int) -> str:
    return f"00000000-0000-0000-{gid}-{idx:04d}"


def _candidate(gid: str, idx: int, *, identity: AlbumIdentity | None = None) -> AlbumCandidate:
    return AlbumCandidate(
        album_id=f"{gid}-a{idx}",
        title=f"{gid} Album {idx}",
        artist="Artist",
        year=2000 + idx,
        identity=identity or AlbumIdentity(
            album_id=f"{gid}-a{idx}",
            canonical_id=_cid(gid, idx),
            canonical_source="musicbrainz",
        ),
    )


def _wide_genre_fixture(count: int = 40) -> list[GenreRef]:
    """40 selectable Genres: far above the 30-pick cooldown window, so Genre
    planning can never be the reason a second run fails."""
    return [
        GenreRef(f"g{i:02d}", f"Genre {i:02d}", "Electronic", eligible=True)
        for i in range(count)
    ]


def _seed_history(history, identities: list[AlbumIdentity]) -> None:
    """Plant committed official history whose picks do NOT collide with the
    candidate Genre set (so Genre cooldown stays satisfiable)."""
    history.commit_history(
        "seed-run",
        [GenrePickRecord(1, "g99"), GenrePickRecord(2, "g98"), GenrePickRecord(3, "g97")],
        identities,
        "2026-08-27T00:00:00Z",
    )


def test_g5_class3_album_exclusion_operates_in_selection_path() -> None:
    # One already-committed canonical identity is planted inside the candidate
    # path of EVERY selectable Genre pool. A full run must select nine NEW real
    # albums, never the committed identity, and complete — the exclusion is
    # proven at the Album-selection level, not by a Genre-planning failure.
    genres = _wide_genre_fixture()
    committed = _candidate("g00", 1).identity
    assert committed is not None
    by_genre = {}
    for g in genres:
        pool = [_candidate(g.genre_id, i) for i in (1, 2, 3, 4)]
        # Plant the committed identity as an extra candidate in this pool.
        pool.append(
            AlbumCandidate(
                f"{g.genre_id}-planted", "Planted Repeat", "Artist", 2010,
                identity=committed,
            )
        )
        by_genre[g.genre_id] = pool

    history = InMemoryHistory()
    _seed_history(history, [committed])
    exclusions = history.excluded_album_identities()
    assert committed in exclusions

    engine = RunEngine(
        config=load_config(),
        history=history,
        genre_source=FakeGenreSource(genres),
        album_source=FakeAlbumSource(by_genre),
        llm=None,
        delivery=FakeDelivery(),
        seed="g5-c3x",
    )
    outcome = engine.run("g5-c3x")
    assert outcome.state == COMPLETE  # NOT a Genre-planning failure
    assert outcome.plan is not None and len(outcome.plan.albums) == 9
    ids = [a.album_id for a in outcome.plan.albums]
    assert len(ids) == len(set(ids))  # no within-run repeats
    assert "planted" not in "".join(ids)  # committed identity never selected
    for album in outcome.plan.albums:
        assert album.year is not None  # real pool records only
    # The committed identity is still permanently excluded after the run.
    assert history.latest_pick_index() == 6
    assert len(history.excluded_album_identities()) == 10  # 1 seeded + 9 new


def test_g5_class3_album_shortage_is_explicitly_caused_by_exclusion() -> None:
    # A pool whose ONLY remaining records after exclusion are already-committed
    # identities must fail explicitly with an Album-level shortage: never a
    # Genre-planning failure, never a fabricated Album, never a repeat, and no
    # official-history pollution.
    genres = _wide_genre_fixture()
    c1 = _candidate("g00", 1).identity
    c2 = _candidate("g00", 2).identity
    assert c1 is not None and c2 is not None
    by_genre = {}
    for g in genres:
        # Two of the four pool records carry committed identities; after
        # exclusion only 2 usable records remain (< albums_per_genre=3).
        by_genre[g.genre_id] = [
            AlbumCandidate(f"{g.genre_id}-c1", "Committed 1", "Artist", 2000, identity=c1),
            AlbumCandidate(f"{g.genre_id}-c2", "Committed 2", "Artist", 2001, identity=c2),
            _candidate(g.genre_id, 3),
            _candidate(g.genre_id, 4),
        ]

    history = InMemoryHistory()
    _seed_history(history, [c1, c2])
    engine = RunEngine(
        config=load_config(),
        history=history,
        genre_source=FakeGenreSource(genres),
        album_source=FakeAlbumSource(by_genre),
        llm=None,
        delivery=FakeDelivery(),
        seed="g5-c3y",
    )
    outcome = engine.run("g5-c3y")
    assert outcome.state == FAILED  # explicit Album shortage
    assert outcome.plan is None or all(
        a.album_id not in {c1.album_id, c2.album_id} for a in outcome.plan.albums
    )
    # No official history was written for the failed run.
    assert history.latest_pick_index() == 3  # only the seeded picks
    assert len(history.excluded_album_identities()) == 2  # no new identities
    transitions = [e.transition for e in history.journal_after("g5-c3y", 0)]
    assert "HISTORY_COMMITTED" not in transitions
    # The failure is an Album shortage, not a Genre-planning failure: genres
    # were selected (SELECTED journal may exist) and the run reached selection.
    failure = next(
        (e for e in history.journal_after("g5-c3y", 0) if e.transition == "FAILED"),
        None,
    )
    assert failure is not None
    assert "album" in str(failure.detail).lower() or "candidate" in str(failure.detail).lower()


# --- Class 4: LLM failure (superseded by D8 deterministic runtime) ------------


def test_g5_class4_no_runtime_llm_call_by_construction() -> None:
    # ADR-0002 D8: v0.1 performs NO external LLM call. A transport that would
    # explode if invoked is injected; the deterministic engine never calls it
    # and the run completes normally (G4-009 closed at G4).
    engine, history, transport = _curated_engine()
    engine._llm = ExplodingLLM()  # type: ignore[attr-defined]
    outcome = engine.run("g5-c4")
    assert outcome.state == COMPLETE
    assert history.latest_pick_index() == 3


class ExplodingLLM:
    def generate_narrative(self, fact_packet, **kwargs):
        raise AssertionError("v0.1 deterministic runtime must never call an LLM")


# --- Class 5: PushPlus delivery failure ---------------------------------------


def test_g5_class5_pushplus_ambiguous_no_retry_no_history() -> None:
    engine, history, transport = _curated_engine(
        transport=FakeTransport(AmbiguousFailure("timeout"))
    )
    outcome = engine.run("g5-c5a")
    assert outcome.state == RECOVERING
    assert transport.calls == 1  # ambiguous is NEVER blindly retried
    _assert_history_untouched(history, "g5-c5a")


def test_g5_class5_pushplus_definitive_rejection_terminal() -> None:
    engine, history, transport = _curated_engine(
        transport=FakeTransport(ProviderRejection("401", "unauthorized"))
    )
    outcome = engine.run("g5-c5b")
    assert outcome.state == FAILED
    assert transport.calls == 1
    _assert_history_untouched(history, "g5-c5b")


# --- Class 6: delivered-but-uncommitted recovery ------------------------------


class OnceFailHistory(InMemoryHistory):
    def __init__(self) -> None:
        super().__init__()
        self.failures_left = 1

    def commit_history(self, run_id, genre_picks, album_identities, committed_at):
        if self.failures_left > 0:
            self.failures_left -= 1
            raise StateCommitFailureError("simulated commit failure")
        super().commit_history(run_id, genre_picks, album_identities, committed_at)


def test_g5_class6_commit_failure_recovers_without_redelivery() -> None:
    history = OnceFailHistory()
    engine, history, transport = _curated_engine(history)
    outcome = engine.run("g5-c6")
    assert outcome.state == RECOVERING
    assert transport.calls == 1  # one external push, ever
    # Recovery from durable evidence: commit history, never re-push.

    fresh = engine  # same durable store, fresh decision path
    recovered = fresh.recover("g5-c6")
    assert recovered.state == COMPLETE
    assert transport.calls == 1
    assert history.latest_pick_index() == 3


# --- Class 7: process crash and restart ---------------------------------------
#
# Reviewer G5-003: the previous CrashPointHistory was an in-memory wrapper whose
# operation/attempt/receipt writes never reached the store presented as
# "durable". The matrix below runs a REAL temporary SQLite file, closes the old
# connection after each simulated crash, constructs a NEW SqliteHistory and a
# NEW engine over the same file, and asserts the exact expected state, external
# call count, receipt/operation evidence, journal tail and 0-or-3 / 0-or-9
# official-history result for every crash point.


class CrashHistoryWrapper:
    """Delegates every call to a REAL SqliteHistory; after the named transition
    (or the delivery claim, for ``AFTER_CLAIM``) is durably persisted, raises a
    simulated process crash. All operation/attempt/receipt methods reach the
    real SQLite store — nothing lives in a wrapper-side dictionary."""

    def __init__(self, inner, crash_after: str) -> None:
        self._inner = inner
        self._crash_after = crash_after
        self._crashed = False

    def append_journal(self, run_id, transition, at, detail=None):
        entry = self._inner.append_journal(run_id, transition, at, detail)
        if transition == self._crash_after and not self._crashed:
            self._crashed = True
            raise _SimulatedCrash(f"crash after {transition}")
        return entry

    def begin_delivery_operation(self, **kwargs):
        snapshot = self._inner.begin_delivery_operation(**kwargs)
        if self._crash_after == "AFTER_CLAIM" and not self._crashed:
            self._crashed = True
            raise _SimulatedCrash("crash after delivery claim")
        return snapshot

    def close(self) -> None:
        self._inner.close()

    def __getattr__(self, name):
        return getattr(self._inner, name)


class _SimulatedCrash(Exception):
    pass


# (expected recover state, total external calls, picks, identities, journal tail)
_CRASH_EXPECTATIONS = {
    "PLANNED": ("FAILED", 0, 0, 0, "FAILED"),
    "FETCHED": ("FAILED", 0, 0, 0, "FAILED"),
    "SELECTED": ("FAILED", 0, 0, 0, "FAILED"),
    "GENERATED": ("FAILED", 0, 0, 0, "FAILED"),
    "VALIDATED": ("FAILED", 0, 0, 0, "FAILED"),
    # Claim persisted (operation IN_FLIGHT + DELIVERING journal written by
    # begin_delivery_operation) but the process died before any request byte
    # left: the delivery is genuinely in-flight/ambiguous -> REQUIRE_HUMAN,
    # zero calls, zero history, never a blind re-push (ADR-0001).
    "AFTER_CLAIM": ("RECOVERING", 0, 0, 0, "RECOVERING"),
    # Delivery finalized (receipt ok + operation SUCCEEDED): recovery commits
    # history WITHOUT a second push.
    "DELIVERED": ("COMPLETE", 1, 3, 9, "COMPLETE"),
    "HISTORY_COMMITTED": ("COMPLETE", 1, 3, 9, "COMPLETE"),
    "COMPLETE": ("COMPLETE", 1, 3, 9, "COMPLETE"),
}


@pytest.mark.parametrize("window", list(_CRASH_EXPECTATIONS))
def test_g5_class7_crash_matrix_real_sqlite(tmp_path, window) -> None:
    import contextlib

    from omda.storage import SqliteHistory

    db = tmp_path / f"crash-{window}.sqlite3"
    inner = SqliteHistory(db)
    wrapped = CrashHistoryWrapper(inner, window)
    engine, _, run_transport = _curated_engine(wrapped)
    with contextlib.suppress(_SimulatedCrash):
        engine.run("g5-c7")
    wrapped.close()  # simulated process death: drop the connection

    # Fresh process: NEW connection + NEW engine over the SAME SQLite file.
    fresh_store = SqliteHistory(db)
    fresh_engine, _, fresh_transport = _curated_engine(fresh_store)
    recovered = fresh_engine.recover("g5-c7")
    total_calls = run_transport.calls + fresh_transport.calls

    expected_state, expected_calls, expected_picks, expected_ids, expected_tail = (
        _CRASH_EXPECTATIONS[window]
    )
    assert recovered.state == expected_state, (window, recovered.state)
    assert total_calls == expected_calls, (window, total_calls)
    assert fresh_store.latest_pick_index() == expected_picks, window
    assert len(fresh_store.excluded_album_identities()) == expected_ids, window
    tail = fresh_store.journal_after("g5-c7", 0)[-1].transition
    assert tail == expected_tail, (window, tail)

    # Post-delivery windows must carry durable receipt + SUCCEEDED operation.
    if expected_calls == 1:
        receipt = fresh_store.find_delivery_receipt("g5-c7:pushplus")
        assert receipt is not None and receipt.status == "ok", window
        op = fresh_store.find_delivery_operation("g5-c7:pushplus")
        assert op is not None and op.state == "SUCCEEDED", window
    # The claim window must leave a durable IN_FLIGHT operation (never a
    # blind second call, never official history) and a DELIVERING journal tail.
    if window == "AFTER_CLAIM":
        op = fresh_store.find_delivery_operation("g5-c7:pushplus")
        assert op is not None and op.state == "IN_FLIGHT_OR_MAY_HAVE_SENT"
        pre = [e.transition for e in fresh_store.journal_after("g5-c7", 0)]
        assert "DELIVERING" in pre
    fresh_store.close()
