"""T2.6 Run state machine and recovery integration tests.

Uses G1 Port contracts, fakes and the local SQLite adapter only — no live
external services. Covers success, per-step failure injection (history must
stay untouched), delivered-but-not-committed recovery without re-delivery,
crash-replay at every durable transition and idempotency.
"""

from __future__ import annotations

import contextlib

import pytest
from tests.fakes import (
    FakeAlbumSource,
    FakeDelivery,
    FakeGenreSource,
    FakeLLM,
    InMemoryHistory,
)

from omda.config import Config, load_config
from omda.orchestrator import (
    COMPLETE,
    DELIVERED,
    FAILED,
    RECOVERING,
    RunEngine,
)
from omda.ports.domain import (
    AlbumCandidate,
    DeliveryReceipt,
    GenreRef,
)
from omda.ports.errors import (
    DeliveryFailureError,
    GenerationFailureError,
    SourceUnavailableError,
    StateCommitFailureError,
)
from omda.storage import SqliteHistory

AT = "2026-08-19T09:00:00+00:00"


def _genres() -> list[GenreRef]:
    return [
        GenreRef("ambient", "Ambient", "Electronic"),
        GenreRef("bebop", "Bebop", "Jazz"),
        GenreRef("krautrock", "Krautrock", "Rock"),
        GenreRef("tuareg", "Tuareg Music", "Regional"),
        GenreRef("idm", "IDM", "Electronic"),
    ]


def _albums(genre_id: str) -> list[AlbumCandidate]:
    return [
        AlbumCandidate(f"{genre_id}-1", f"{genre_id} Album 1", "Artist", 2015),
        AlbumCandidate(f"{genre_id}-2", f"{genre_id} Album 2", "Artist", 2000),
        AlbumCandidate(f"{genre_id}-3", f"{genre_id} Album 3", "Artist", 1990),
        AlbumCandidate(f"{genre_id}-4", f"{genre_id} Album 4", "Artist", 2020),
    ]


def _album_source() -> FakeAlbumSource:
    return FakeAlbumSource({g.genre_id: _albums(g.genre_id) for g in _genres()})


def _engine(
    history,
    delivery=None,
    album_source=None,
    llm=None,
    seed: str | None = None,
    config=None,
) -> RunEngine:
    return RunEngine(
        config=config or load_config(),
        history=history,
        genre_source=FakeGenreSource(_genres()),
        album_source=album_source or _album_source(),
        llm=llm or FakeLLM("Explanatory text."),
        delivery=delivery or FakeDelivery(),
        seed=seed,
    )


# --- success path -------------------------------------------------------------

HISTORY_FACTORIES = [
    pytest.param(InMemoryHistory, id="in-memory"),
    pytest.param(lambda: SqliteHistory(":memory:"), id="sqlite"),
]


@pytest.mark.parametrize("factory", HISTORY_FACTORIES)
def test_successful_run_commits_history_and_completes(factory) -> None:
    history = factory()
    delivery = FakeDelivery()
    outcome = _engine(history, delivery=delivery).run("run-1")

    assert outcome.state == COMPLETE
    assert outcome.plan is not None
    assert len(outcome.plan.genres) == 3
    assert len(outcome.plan.albums) == 9
    assert history.latest_pick_index() == 3
    assert len(history.excluded_album_identities()) == 9
    transitions = [e.transition for e in history.journal_after("run-1", 0)]
    assert transitions[-1] == COMPLETE
    assert DELIVERED in transitions
    # Official history committed exactly once; delivery happened exactly once.
    assert len(delivery.delivered) == 1


@pytest.mark.parametrize("factory", HISTORY_FACTORIES)
def test_successful_run_never_repeats_album_within_run(factory) -> None:
    history = factory()
    outcome = _engine(history).run("run-1")
    ids = [a.album_id for a in outcome.plan.albums]
    assert len(ids) == len(set(ids)) == 9


# --- failure injection: history must stay untouched ---------------------------


class FailingAlbumSource:
    def candidates_for_genre(self, genre, limit=None):
        raise SourceUnavailableError("simulated fetch failure")


class FailingLLM:
    def generate_narrative(self, fact_packet):
        raise GenerationFailureError("simulated llm failure")


class EmptyLLM:
    def generate_narrative(self, fact_packet):
        return "   "


class FailingDelivery:
    def deliver(self, payload, idempotency_key, target=None):
        raise DeliveryFailureError("simulated delivery failure")


def _assert_history_untouched(history, run_id: str) -> None:
    assert history.latest_pick_index() == 0
    assert history.excluded_album_identities() == frozenset()
    transitions = [e.transition for e in history.journal_after(run_id, 0)]
    assert "HISTORY_COMMITTED" not in transitions
    assert transitions[-1] == FAILED


@pytest.mark.parametrize("factory", HISTORY_FACTORIES)
def test_fetch_failure_does_not_pollute_history(factory) -> None:
    history = factory()
    outcome = _engine(history, album_source=FailingAlbumSource()).run("run-1")
    assert outcome.state == FAILED
    _assert_history_untouched(history, "run-1")


@pytest.mark.parametrize("factory", HISTORY_FACTORIES)
def test_generation_failure_does_not_pollute_history(factory) -> None:
    history = factory()
    outcome = _engine(history, llm=FailingLLM()).run("run-1")
    assert outcome.state == FAILED
    _assert_history_untouched(history, "run-1")


@pytest.mark.parametrize("factory", HISTORY_FACTORIES)
def test_validation_failure_does_not_pollute_history(factory) -> None:
    history = factory()
    outcome = _engine(history, llm=EmptyLLM()).run("run-1")
    assert outcome.state == FAILED
    _assert_history_untouched(history, "run-1")


@pytest.mark.parametrize("factory", HISTORY_FACTORIES)
def test_delivery_failure_does_not_pollute_history(factory) -> None:
    history = factory()
    outcome = _engine(history, delivery=FailingDelivery()).run("run-1")
    assert outcome.state == FAILED
    _assert_history_untouched(history, "run-1")


@pytest.mark.parametrize("factory", HISTORY_FACTORIES)
def test_candidate_shortage_fails_without_history_write(factory) -> None:
    history = factory()
    scarce = FakeAlbumSource({g.genre_id: _albums(g.genre_id)[:1] for g in _genres()})
    outcome = _engine(history, album_source=scarce).run("run-1")
    assert outcome.state == FAILED
    _assert_history_untouched(history, "run-1")


# --- delivered-but-not-committed recovery -------------------------------------


class FlakyCommitHistory:
    """Wraps a HistoryPort: first commit_history fails, later ones succeed."""

    def __init__(self, inner) -> None:
        self._inner = inner
        self.commits = 0

    def __getattr__(self, name):
        return getattr(self._inner, name)

    def commit_history(self, *args, **kwargs) -> None:
        self.commits += 1
        if self.commits == 1:
            raise StateCommitFailureError("simulated commit failure")
        return self._inner.commit_history(*args, **kwargs)


@pytest.mark.parametrize("factory", HISTORY_FACTORIES)
def test_delivered_but_not_committed_recovers_without_redelivery(factory) -> None:
    history = factory()
    delivery = FakeDelivery()
    flaky = FlakyCommitHistory(history)
    engine = _engine(flaky, delivery=delivery)

    first = engine.run("run-1")
    assert first.state == RECOVERING  # delivered, history commit failed
    assert len(delivery.delivered) == 1
    assert delivery.calls == 1

    # Recovery uses durable journal + immutable receipt; must NOT re-deliver.
    second = engine.recover("run-1")
    assert second.state == COMPLETE
    assert len(delivery.delivered) == 1  # no second external push
    assert delivery.calls == 1  # no second deliver() call either
    assert flaky.commits == 2
    assert history.latest_pick_index() == 3
    assert len(history.excluded_album_identities()) == 9


# --- G2-005: real crash harness (durable write first, then process death) ------


class SimulatedCrash(Exception):
    """Raised AFTER the transition/evidence is durably persisted."""


class CrashPointHistory:
    """Wraps a HistoryPort: persists the operation first, then simulates death."""

    def __init__(self, inner, crash_after: str | None = None) -> None:
        self._inner = inner
        self._crash_after = crash_after

    def __getattr__(self, name):
        return getattr(self._inner, name)

    def append_journal(self, run_id, transition, at, detail=None):
        entry = self._inner.append_journal(run_id, transition, at, detail)  # durable FIRST
        if self._crash_after is not None and transition == self._crash_after:
            raise SimulatedCrash(f"crash after durable {transition}")
        return entry

    def save_delivery_receipt(self, receipt):
        self._inner.save_delivery_receipt(receipt)  # durable FIRST
        if self._crash_after == "receipt-saved":
            raise SimulatedCrash("crash after durable receipt saved")

    def commit_history(self, *args, **kwargs):
        self._inner.commit_history(*args, **kwargs)  # durable FIRST
        if self._crash_after == "history-committed":
            raise SimulatedCrash("crash after durable history commit")


CRASH_WINDOWS = [
    "PLANNED",
    "FETCHED",
    "SELECTED",
    "GENERATED",
    "VALIDATED",
    "DELIVERING",
    "receipt-saved",
    "DELIVERED",
    "history-committed",
    "COMPLETE",
]


@pytest.mark.parametrize("window", CRASH_WINDOWS)
def test_crash_recovery_table(window) -> None:
    inner = InMemoryHistory()
    history = CrashPointHistory(inner, crash_after=window)
    delivery = FakeDelivery()
    engine = _engine(history, delivery=delivery)

    with contextlib.suppress(SimulatedCrash):
        engine.run("run-1")  # the persisted state at the crash point stays durable

    # Recovery in a "fresh process" against the same durable store.
    recovered = _engine(inner, delivery=delivery).recover("run-1")
    assert recovered.state in (COMPLETE, FAILED, RECOVERING)
    # Delivery happened at most once (calls) and at most one external side effect.
    assert delivery.calls <= 1
    assert len(delivery.delivered) <= 1
    # A COMPLETE outcome has a durable COMPLETE tail and committed history.
    if recovered.state == COMPLETE:
        tail = inner.journal_after("run-1", 0)[-1].transition
        assert tail == COMPLETE
        assert inner.latest_pick_index() == 3
    else:
        # Non-COMPLETE: history must not be partially committed.
        assert inner.journal_after("run-1", 0)[-1].transition != "COMPLETE"
        if recovered.state == FAILED:
            assert inner.latest_pick_index() == 0


def test_missing_receipt_for_delivered_run_fails_closed() -> None:
    inner = InMemoryHistory()
    history = CrashPointHistory(inner, crash_after="DELIVERED")
    delivery = FakeDelivery()
    engine = _engine(history, delivery=delivery)
    with contextlib.suppress(SimulatedCrash):
        engine.run("run-1")
    assert inner.journal_after("run-1", 0)[-1].transition == DELIVERED

    # Evidence lost after delivery: recovery must fail closed, never re-push.
    inner._receipts.clear()  # test-only access to simulate lost evidence
    recovered = _engine(inner, delivery=delivery).recover("run-1")
    assert recovered.state == RECOVERING
    assert len(delivery.delivered) <= 1
    assert inner.latest_pick_index() == 0  # history never committed


class BoundFailedReceiptDelivery:
    """A correctly bound, explicitly failed receipt (confirmed current-run failure)."""

    def __init__(self):
        self.calls = 0

    def deliver(self, payload, idempotency_key, target=None):
        self.calls += 1
        run_id, _, channel = idempotency_key.partition(":")
        return DeliveryReceipt(
            run_id=run_id,
            idempotency_key=idempotency_key,
            delivered_at=AT,
            channel=channel or "markdown",
            status="failed",
        )


class MisboundFailedReceiptDelivery:
    """A failed-status receipt bound to ANOTHER operation: malformed/ambiguous."""

    def __init__(self):
        self.calls = 0

    def deliver(self, payload, idempotency_key, target=None):
        self.calls += 1
        return DeliveryReceipt(
            run_id="other-run",
            idempotency_key="other-key",
            delivered_at=AT,
            channel="fake",
            status="failed",
        )


def test_bound_failed_receipt_is_ordinary_terminal_failure() -> None:
    # Correctly bound + explicitly failed: confirmed current-run failure.
    history = InMemoryHistory()
    delivery = BoundFailedReceiptDelivery()
    outcome = _engine(history, delivery=delivery).run("run-1")
    assert outcome.state == FAILED
    assert delivery.calls == 1
    assert history.latest_pick_index() == 0
    assert history.excluded_album_identities() == frozenset()


def test_misbound_failed_receipt_enters_recovery() -> None:
    # A failed receipt bound to ANOTHER operation is malformed/ambiguous
    # evidence — the external call may have delivered; never terminal FAILED.
    history = InMemoryHistory()
    delivery = MisboundFailedReceiptDelivery()
    outcome = _engine(history, delivery=delivery).run("run-1")
    assert outcome.state == RECOVERING
    assert delivery.calls == 1
    assert history.latest_pick_index() == 0
    tails = [e.transition for e in history.journal_after("run-1", 0)]
    assert tails[-1] == RECOVERING


def test_conflicting_receipt_fails_closed_without_overwrite() -> None:
    history = InMemoryHistory()
    # Durable evidence already exists for this idempotency key (delivery happened),
    # but no run journal exists — the engine must fail closed on a conflicting
    # receipt instead of overwriting evidence or writing history.
    existing = DeliveryReceipt(
        run_id="prior-run",
        idempotency_key="run-1:markdown",
        delivered_at=AT,
        channel="markdown",
        status="ok",
    )
    history.save_delivery_receipt(existing)

    outcome = _engine(history, delivery=MisboundFailedReceiptDelivery()).run("run-1")
    # The delivery attempt already happened -> ambiguous -> RECOVERING.
    assert outcome.state == RECOVERING
    # Original success evidence intact; no official history written.
    assert history.find_delivery_receipt("run-1:markdown") == existing
    assert history.latest_pick_index() == 0


def test_repeated_completed_run_id_is_idempotent_replay() -> None:
    history = InMemoryHistory()
    engine = _engine(history)
    first = engine.run("run-1")
    assert first.state == COMPLETE
    second = engine.run("run-1")  # same id: durable terminal state, no fresh plan
    assert second.state == COMPLETE
    assert history.latest_pick_index() == 3  # no duplicate commit
    assert len(history.excluded_album_identities()) == 9
    tails = [e.transition for e in history.journal_after("run-1", 0)]
    assert tails.count("COMPLETE") == 1  # durable COMPLETE exactly once


def test_history_committed_tail_gets_durable_complete() -> None:
    inner = InMemoryHistory()
    history = CrashPointHistory(inner, crash_after="history-committed")
    delivery = FakeDelivery()
    engine = _engine(history, delivery=delivery)
    with contextlib.suppress(SimulatedCrash):
        engine.run("run-1")
    assert inner.journal_after("run-1", 0)[-1].transition == "HISTORY_COMMITTED"
    # Recovery appends durable COMPLETE exactly once.
    recovered = _engine(inner, delivery=delivery).recover("run-1")
    assert recovered.state == COMPLETE
    assert inner.journal_after("run-1", 0)[-1].transition == "COMPLETE"
    assert inner.journal_after("run-1", 0)[-1].transition == "COMPLETE"
    # Calling again never appends a second COMPLETE.
    _engine(inner, delivery=delivery).recover("run-1")
    tails = [e.transition for e in inner.journal_after("run-1", 0)]
    assert tails.count("COMPLETE") == 1


# --- G2-001: global ordered pick indices --------------------------------------


@pytest.mark.parametrize("factory", HISTORY_FACTORIES)
def test_three_consecutive_runs_commit_global_indices(factory) -> None:
    history = factory()
    # A pool large enough to satisfy cooldown 30 for 9 successive picks.
    many_genres = [GenreRef(f"g{i:02d}", f"Genre {i}", f"F{i % 3}") for i in range(12)]
    album_source = FakeAlbumSource({g.genre_id: _albums(g.genre_id) for g in many_genres})
    genre_source = FakeGenreSource(many_genres)
    picks_seen: list[int] = []
    for run_index in range(1, 4):
        engine = RunEngine(
            config=load_config(),
            history=history,
            genre_source=genre_source,
            album_source=album_source,
            llm=FakeLLM("Explanatory text."),
            delivery=FakeDelivery(),
            seed=f"run-seed-{run_index}",
        )
        outcome = engine.run(f"run-{run_index}")
        assert outcome.state == COMPLETE, f"run {run_index} failed"
        assert outcome.plan is not None
        picks_seen.extend(p.pick_index for p in outcome.plan.genre_picks())
    # Runs commit indices 1-3, 4-6, 7-9 respectively (global, never restarting).
    assert picks_seen == [1, 2, 3, 4, 5, 6, 7, 8, 9]
    assert history.latest_pick_index() == 9
    assert len(history.excluded_album_identities()) == 27


def test_historical_latest_pick_from_absent_genre_advances_global_index() -> None:
    # A historical pick for a Genre no longer visible in the current source must
    # still advance the next global index (G2-001: never infer from visible set).
    history = InMemoryHistory()
    engine = _engine(history)
    # Simulate a historical committed pick 30 for a Genre absent from the source.
    history.record_pick_directly(30, "ghost-genre")

    outcome = engine.run("run-1")
    assert outcome.state == COMPLETE
    assert outcome.plan is not None
    assert [p.pick_index for p in outcome.plan.genre_picks()] == [31, 32, 33]
    assert history.latest_pick_index() == 33


@pytest.mark.parametrize("factory", HISTORY_FACTORIES)
def test_failed_run_consumes_no_pick_indices(factory) -> None:
    history = factory()
    engine = _engine(history, llm=FailingLLM())
    outcome = engine.run("run-1")
    assert outcome.state == FAILED
    assert history.latest_pick_index() == 0  # nothing consumed
    assert history.excluded_album_identities() == frozenset()


# --- G2-004: year-constraint observability is durable in the journal ----------


def test_year_fallback_status_is_persisted_in_journal() -> None:
    history = InMemoryHistory()
    # All-old album pools force the fallback_no_modern path for every genre.
    old_only = FakeAlbumSource(
        {
            g.genre_id: [
                AlbumCandidate(f"{g.genre_id}-1", f"{g.genre_id} Album 1", "Artist", 1980),
                AlbumCandidate(f"{g.genre_id}-2", f"{g.genre_id} Album 2", "Artist", 1985),
                AlbumCandidate(f"{g.genre_id}-3", f"{g.genre_id} Album 3", "Artist", 1990),
            ]
            for g in _genres()
        }
    )
    engine = _engine(history, album_source=old_only)
    outcome = engine.run("run-1")
    assert outcome.state == COMPLETE
    # The SELECTED journal entry persists per-genre constraint/fallback evidence.
    entries = history.journal_after("run-1", 0)
    selected = next(e for e in entries if e.transition == "SELECTED")
    assert selected.detail is not None
    statuses = [s["status"] for s in selected.detail["album_selection"]]
    assert statuses and all(s == "fallback_no_modern" for s in statuses)
    assert all(s["reason"] for s in selected.detail["album_selection"])


# --- G2-006: provenance in the journal reproduces the exact plan --------------


def test_provenance_recorded_without_consuming_rng() -> None:
    history = InMemoryHistory()
    engine = _engine(history, seed="provenance-seed", )
    outcome = engine.run("run-1")
    assert outcome.state == COMPLETE

    entries = history.journal_after("run-1", 0)
    planned = next(e for e in entries if e.transition == "PLANNED")
    assert planned.detail is not None
    # The journaled seed is the ACTUAL construction seed, not a consumed draw.
    assert planned.detail["seed"] == "provenance-seed"
    assert planned.detail["input_version"] == "unknown"
    assert planned.detail["config_version"]


def test_fresh_process_reproduces_exact_plan_from_journal_evidence() -> None:
    history = InMemoryHistory()
    engine = _engine(history, seed="provenance-seed")
    outcome = engine.run("run-1")
    assert outcome.state == COMPLETE

    entries = history.journal_after("run-1", 0)
    planned = next(e for e in entries if e.transition == "PLANNED")
    original_selected = next(e for e in entries if e.transition == "SELECTED")

    # A brand-new process uses ONLY the journaled provenance (seed + input +
    # config) against the same sources to recreate the exact ordered plan.
    # A fresh process must reproduce the exact plan using the journaled seed AND
    # the same run id (the per-run RNG is derived from seed + run id, G2-008).
    fresh_history = InMemoryHistory()
    fresh_engine = _engine(fresh_history, seed=planned.detail["seed"])
    fresh = fresh_engine.run("run-1")
    assert fresh.state == COMPLETE
    fresh_entries = fresh_history.journal_after("run-1", 0)
    fresh_selected = next(e for e in fresh_entries if e.transition == "SELECTED")
    assert fresh_selected.detail is not None
    assert fresh_selected.detail["genres"] == original_selected.detail["genres"]
    assert fresh_selected.detail["albums"] == original_selected.detail["albums"]


# --- G2-008: per-run randomness is reproducible across a process restart -------


def _selected_digest(history, run_id: str):
    entries = history.journal_after(run_id, 0)
    selected = next(e for e in entries if e.transition == "SELECTED")
    return selected.detail


def test_run2_reproducible_across_process_restart() -> None:
    # A pool large enough for two successive 3-pick runs (cooldown 30).
    many_genres = [GenreRef(f"g{i:02d}", f"Genre {i}", f"F{i % 3}") for i in range(12)]
    album_source = FakeAlbumSource({g.genre_id: _albums(g.genre_id) for g in many_genres})
    genre_source = FakeGenreSource(many_genres)

    def make_engine(history) -> RunEngine:
        return RunEngine(
            config=load_config(),
            history=history,
            genre_source=genre_source,
            album_source=album_source,
            llm=FakeLLM("Explanatory text."),
            delivery=FakeDelivery(),
            seed="g2-008-seed",
        )

    # Process A (long-lived): run 1 then run 2.
    history_a = InMemoryHistory()
    engine_a = make_engine(history_a)
    assert engine_a.run("run-1").state == COMPLETE
    planned_a = next(
        e for e in history_a.journal_after("run-1", 0) if e.transition == "PLANNED"
    )
    assert planned_a.detail is not None
    assert planned_a.detail["seed"] == "g2-008-seed"
    assert planned_a.detail["run_id"] == "run-1"
    assert planned_a.detail["config_version"]
    run2_a = engine_a.run("run-2")
    assert run2_a.state == COMPLETE
    digest_a = _selected_digest(history_a, "run-2")

    # Process restart: a brand-new engine reproduces run 2 using ONLY the
    # journaled seed/input/config provenance and the same official history —
    # its output must exactly match the long-lived process (G2-008).
    history_b = InMemoryHistory()
    engine_b = make_engine(history_b)
    assert engine_b.run("run-1").state == COMPLETE
    run2_b = engine_b.run("run-2")
    assert run2_b.state == COMPLETE
    digest_b = _selected_digest(history_b, "run-2")

    assert digest_a == digest_b  # exact ordered Genres and Albums


def test_config_seed_is_bound_to_rng_construction() -> None:
    # With no explicit caller seed, Config.seed drives RNG construction (G2-008).
    history = InMemoryHistory()
    engine = _engine(history, seed=None, config=Config(seed="config-bound-seed"))
    outcome = engine.run("run-1")
    assert outcome.state == COMPLETE
    planned = next(
        e for e in history.journal_after("run-1", 0) if e.transition == "PLANNED"
    )
    assert planned.detail is not None
    assert planned.detail["seed"] == "config-bound-seed"


# --- G2-009: receipt must be bound to run id / key / channel / status ----------


class MisboundReceiptDelivery:
    """Returns an ok-format receipt but with configurable wrong bindings."""

    def __init__(
        self,
        run_id: str | None = None,
        idempotency_key: str | None = None,
        channel: str | None = None,
        status: str = "ok",
    ) -> None:
        self._run_id = run_id
        self._key = idempotency_key
        self._channel = channel
        self._status = status
        self.calls = 0

    def deliver(self, payload, idempotency_key, target=None):
        self.calls += 1
        return DeliveryReceipt(
            run_id=self._run_id if self._run_id is not None else "",
            idempotency_key=self._key if self._key is not None else idempotency_key,
            delivered_at=AT,
            channel=self._channel if self._channel is not None else "markdown",
            status=self._status,
        )


MISBOUND_CASES = [
    pytest.param(
        {"run_id": "another-run"}, "wrong run id", id="wrong-run-id"
    ),
    pytest.param(
        {"idempotency_key": "another-key"}, "wrong key", id="wrong-key"
    ),
    pytest.param(
        {"channel": "pushplus"}, "wrong channel", id="wrong-channel"
    ),
]


@pytest.mark.parametrize("factory", HISTORY_FACTORIES)
@pytest.mark.parametrize("overrides,label", MISBOUND_CASES)
def test_misbound_receipt_never_commits_history(factory, overrides, label) -> None:
    history = factory()
    delivery = MisboundReceiptDelivery(**overrides)
    outcome = _engine(history, delivery=delivery).run("run-1")
    # G2-012/ADR-0001: an ok-but-misbound receipt is delivery AMBIGUITY ->
    # RECOVERING (manual review), never an ordinary terminal failure and never
    # history. The attempt IS recorded as ambiguous (durable at-most-one
    # evidence), so no re-push can ever happen after restart.
    assert outcome.state == RECOVERING, f"{label} must enter recovery"
    assert history.latest_pick_index() == 0
    assert history.excluded_album_identities() == frozenset()
    stored = history.find_delivery_receipt("run-1:markdown")
    assert stored is None or stored.status != "ok"
    tails = [e.transition for e in history.journal_after("run-1", 0)]
    assert tails[-1] == RECOVERING
    # Anomaly is auditable in the journal.
    anomaly = next(e for e in history.journal_after("run-1", 0) if e.transition == "RECOVERING")
    assert anomaly.detail is not None
    assert "does not match run/key/channel" in anomaly.detail["reason"]


@pytest.mark.parametrize("factory", HISTORY_FACTORIES)
def test_exact_matching_receipt_still_succeeds(factory) -> None:
    history = factory()
    outcome = _engine(history, delivery=FakeDelivery()).run("run-1")
    assert outcome.state == COMPLETE
    assert history.latest_pick_index() == 3
    receipt = history.find_delivery_receipt("run-1:markdown")
    assert receipt is not None and receipt.status == "ok"


def test_misbound_receipt_on_recovery_fails_closed() -> None:
    inner = InMemoryHistory()
    history = CrashPointHistory(inner, crash_after="DELIVERED")
    engine = _engine(history, delivery=FakeDelivery())
    with contextlib.suppress(SimulatedCrash):
        engine.run("run-1")
    assert inner.journal_after("run-1", 0)[-1].transition == DELIVERED
    # Tamper the stored receipt to bind it to another run (evidence mismatch).
    inner._receipts["run-1:markdown"] = DeliveryReceipt(
        run_id="evil-run",
        idempotency_key="run-1:markdown",
        delivered_at=AT,
        channel="markdown",
        status="ok",
    )
    recovered = _engine(inner, delivery=FakeDelivery()).recover("run-1")
    assert recovered.state == RECOVERING  # fail closed, no history commit
    assert inner.latest_pick_index() == 0


# --- G2-010: parent taxonomy flows Port -> Orchestrator -> Core -----------------


def test_parent_diversity_enforced_through_orchestrated_run() -> None:
    # Pool of 4 genres where 2 share a limited parent: an unconstrained planner
    # would include g1+g2 together in ~50% of runs (2 of 4 possible 3-sets), so
    # 30 runs must NEVER co-select them — proving the configured parent limit
    # actually reaches the Core through the Port/Orchestrator path (G2-010).
    genres = [
        GenreRef("g1", "G1", "Electronic", parents=("electronic",)),
        GenreRef("g2", "G2", "Electronic", parents=("electronic",)),
        GenreRef("g3", "G3", "Jazz"),
        GenreRef("g4", "G4", "Rock"),
    ]
    album_source = FakeAlbumSource({g.genre_id: _albums(g.genre_id) for g in genres})
    config = Config(genre_parent_limits={"electronic": 1})
    for i in range(30):
        history = InMemoryHistory()
        engine = RunEngine(
            config=config,
            history=history,
            genre_source=FakeGenreSource(genres),
            album_source=album_source,
            llm=FakeLLM("Explanatory text."),
            delivery=FakeDelivery(),
            seed=f"parent-{i}",
        )
        outcome = engine.run("run-1")
        assert outcome.state == COMPLETE
        assert outcome.plan is not None
        picked = {g.genre_id for g in outcome.plan.genres}
        assert not ({"g1", "g2"} <= picked), f"run {i} violated parent limit"


def test_parent_unsatisfiable_fails_explicitly() -> None:
    # Two genres share the only limited parent and the pool cannot satisfy the
    # constraint -> explicit FAILED (bounded), never an invalid selection.
    genres = [
        GenreRef("g1", "G1", "Electronic", parents=("electronic",)),
        GenreRef("g2", "G2", "Electronic", parents=("electronic",)),
        GenreRef("g3", "G3", "Jazz"),
    ]
    album_source = FakeAlbumSource({g.genre_id: _albums(g.genre_id) for g in genres})
    config = Config(genre_parent_limits={"electronic": 1})
    history = InMemoryHistory()
    engine = RunEngine(
        config=config,
        history=history,
        genre_source=FakeGenreSource(genres),
        album_source=album_source,
        llm=FakeLLM("Explanatory text."),
        delivery=FakeDelivery(),
        seed="unsat-parent",
    )
    outcome = engine.run("run-1")
    assert outcome.state == FAILED
    assert history.latest_pick_index() == 0  # nothing committed


# --- G2-012: ambiguous successful delivery enters recovery, never terminal -----


@pytest.mark.parametrize("overrides,label", MISBOUND_CASES)
def test_ambiguous_delivery_records_one_effect_and_never_redelivers(overrides, label) -> None:
    # The external side effect already happened (one deliver call); the misbound
    # ok receipt cannot prove otherwise. Repeated run() must not re-deliver.
    history = InMemoryHistory()
    delivery = MisboundReceiptDelivery(**overrides)
    engine = _engine(history, delivery=delivery)
    first = engine.run("run-1")
    assert first.state == RECOVERING
    assert delivery.calls == 1  # exactly one external delivery attempt
    # Repeated run() of the same id: durable recovery state, no second push.
    second = engine.run("run-1")
    assert second.state == RECOVERING
    assert delivery.calls == 1
    # History never committed.
    assert history.latest_pick_index() == 0
    assert history.excluded_album_identities() == frozenset()


# --- G2-012 re-review: recovery is durably idempotent and bounded ---------------


def test_repeated_recovery_of_unchanged_evidence_is_bounded() -> None:
    # Five identical recovery calls on unchanged evidence must NOT grow the
    # journal with repeated RECOVERING entries (G2-012 bounded retries).
    history = InMemoryHistory()
    delivery = MisboundReceiptDelivery(run_id="another-run")
    engine = _engine(history, delivery=delivery)
    first = engine.run("run-1")
    assert first.state == RECOVERING
    assert delivery.calls == 1

    for _ in range(5):
        again = engine.run("run-1")  # same id, same evidence
        assert again.state == RECOVERING
        assert delivery.calls == 1  # never a second external call

    tails = [e.transition for e in history.journal_after("run-1", 0)]
    # DELIVERING + one RECOVERING entry, no growth across retries.
    assert tails.count(RECOVERING) == 1
    assert history.latest_pick_index() == 0


def test_receipt_conflict_after_external_call_enters_recovery() -> None:
    # A correctly bound ok receipt that CONFLICTS with pre-existing immutable
    # evidence (different delivered_at) after one external effect is ambiguous:
    # the side effect may have happened -> RECOVERING, one delivery call, zero
    # history, original evidence preserved (G2-012).
    history = InMemoryHistory()
    existing = DeliveryReceipt(
        run_id="prior-run",
        idempotency_key="run-1:markdown",
        delivered_at=AT,
        channel="markdown",
        status="ok",
    )
    history.save_delivery_receipt(existing)

    class ConflictingOkDelivery:
        calls = 0

        def deliver(self, payload, idempotency_key, target=None):
            ConflictingOkDelivery.calls += 1
            run_id, _, channel = idempotency_key.partition(":")
            return DeliveryReceipt(
                run_id=run_id,
                idempotency_key=idempotency_key,
                delivered_at="2026-08-20T00:00:00+00:00",
                channel=channel or "markdown",
                status="ok",
            )

    outcome = _engine(history, delivery=ConflictingOkDelivery()).run("run-1")
    assert outcome.state == RECOVERING
    assert ConflictingOkDelivery.calls == 1
    assert history.find_delivery_receipt("run-1:markdown") == existing
    assert history.latest_pick_index() == 0


# --- G2-012 re-review 4: exactly three receipt status classes ------------------


@pytest.mark.parametrize("status", ["unknown", "pending", ""], ids=["unknown", "pending", "empty"])
def test_bound_malformed_status_enters_recovery_not_terminal(status) -> None:
    # Only exactly "ok" may proceed and only exactly "failed" confirms failure;
    # every other status is malformed/ambiguous evidence -> RECOVERING with the
    # anomaly preserved, zero history, one delivery call.
    history = InMemoryHistory()

    class MalformedStatusDelivery:
        calls = 0

        def deliver(self, payload, idempotency_key, target=None):
            MalformedStatusDelivery.calls += 1
            run_id, _, channel = idempotency_key.partition(":")
            return DeliveryReceipt(
                run_id=run_id,
                idempotency_key=idempotency_key,
                delivered_at=AT,
                channel=channel or "markdown",
                status=status,
            )

    outcome = _engine(history, delivery=MalformedStatusDelivery()).run("run-1")
    assert outcome.state == RECOVERING, f"bound status {status!r} must enter recovery"
    assert MalformedStatusDelivery.calls == 1
    assert history.latest_pick_index() == 0
    tails = [e.transition for e in history.journal_after("run-1", 0)]
    assert tails[-1] == RECOVERING
    anomaly = next(
        e for e in history.journal_after("run-1", 0) if e.transition == "RECOVERING"
    )
    assert anomaly.detail is not None
    assert anomaly.detail.get("receipt_status") == status  # durable anomaly evidence
