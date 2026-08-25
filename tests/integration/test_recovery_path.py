"""G4 T4.4 — delivered-but-not-committed recovery path (SPEC §4; MP §6).

Recovery must check DURABLE evidence (journal + immutable receipt) rather than
inferring success from memory, must never blind re-deliver, and must never claim
cross-system absolute atomicity. The decision layer is exercised here against
the G2 state machine with the real Orchestrator + fakes.
"""

from __future__ import annotations

from tests.fakes import FakeAlbumSource, FakeDelivery, FakeGenreSource, FakeLLM, InMemoryHistory

from omda.config import load_config
from omda.orchestrator.recovery import (
    COMMIT_HISTORY,
    COMPLETE_ALREADY,
    REQUIRE_HUMAN,
    resolve_recovery_action,
)
from omda.orchestrator.run import COMPLETE, RECOVERING, RunEngine, utc_now
from omda.ports.domain import AlbumCandidate, GenreRef
from omda.ports.errors import StateCommitFailureError


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


def _engine(history, delivery=None):
    return RunEngine(
        config=load_config(),
        history=history,
        genre_source=FakeGenreSource(_genres()),
        album_source=FakeAlbumSource({g.genre_id: _albums(g.genre_id) for g in _genres()}),
        llm=FakeLLM("Explanatory text."),
        delivery=delivery or FakeDelivery(),
        seed="recovery",
    )


class OnceFailHistory(InMemoryHistory):
    """History whose FIRST official commit fails, later ones succeed.

    Simulates the delivered-but-not-committed window: the external push
    happened, the receipt is durable, but the local commit failed once.
    """

    def __init__(self) -> None:
        super().__init__()
        self.failures_left = 1

    def commit_history(self, run_id, genre_picks, album_identities, committed_at):
        if self.failures_left > 0:
            self.failures_left -= 1
            raise StateCommitFailureError("simulated commit failure")
        super().commit_history(run_id, genre_picks, album_identities, committed_at)


def test_resolve_commits_history_after_delivery_without_redelivery() -> None:
    # Deliver succeeds but local history commit is forced to fail -> RECOVERING.
    # The decision layer must choose COMMIT_HISTORY (never RE_DELIVER).
    history = OnceFailHistory()
    delivery = FakeDelivery()
    engine = _engine(history, delivery)
    outcome = engine.run("run-1")
    assert outcome.state == RECOVERING
    assert delivery.calls == 1

    decision = resolve_recovery_action(history, "run-1")
    assert decision.action == COMMIT_HISTORY
    assert decision.receipt is not None and decision.receipt.status == "ok"
    assert decision.reason == "delivered-but-not-committed"


def test_resolve_requires_human_when_evidence_missing() -> None:
    history = InMemoryHistory()
    decision = resolve_recovery_action(history, "run-missing")
    assert decision.action == REQUIRE_HUMAN


def test_resolve_requires_human_on_mismatched_receipt() -> None:
    # A receipt exists but belongs to another run/channel -> ambiguous; human.
    from tests.fakes import bound_receipt

    history = InMemoryHistory()
    bound_receipt(
        history, run_id="other-run", key="other-run:markdown", channel="markdown"
    )
    decision = resolve_recovery_action(history, "run-1")
    assert decision.action == REQUIRE_HUMAN


def test_resolve_returns_complete_for_finished_run() -> None:
    history = InMemoryHistory()
    outcome = _engine(history).run("run-ok")
    assert outcome.state == COMPLETE
    decision = resolve_recovery_action(history, "run-ok")
    assert decision.action == COMPLETE_ALREADY


def test_recovery_never_blindly_redelivers() -> None:
    # SPEC §4: recovery checks durable evidence; the delivery adapter is never
    # re-invoked just because a run is in RECOVERING.
    history = OnceFailHistory()
    delivery = FakeDelivery()
    outcome = _engine(history, delivery).run("run-1")
    assert outcome.state == RECOVERING
    # Real G2 recovery path: commits history, does NOT call deliver() twice.
    recovered = _engine(history, delivery).recover("run-1")
    assert recovered.state == COMPLETE
    assert delivery.calls == 1  # no second external delivery


# --- G4-004 re-review: recovery requires bound durable evidence ----------------



def _journal_after_delivery(history, run_id: str, at: str = "2026-08-21T00:00:00+00:00") -> None:
    """Simulate a run whose journal shows it reached the post-delivery window."""
    history.append_journal(run_id, "PLANNED", at)
    history.append_journal(run_id, "SELECTED", at)
    history.append_journal(run_id, "DELIVERING", at)
    history.append_journal(run_id, "DELIVERED", at)


def test_recovery_without_post_delivery_journal_is_require_human() -> None:
    # G4-004: without a durable post-delivery journal tail the run never
    # durably reached delivery, so COMMIT_HISTORY is forbidden. (G4-002F: an
    # unbound receipt can no longer be CREATED on a v3 store — the
    # "receipt exists but no delivery journal" legacy case is exercised below
    # via a real migrated v1 row, see
    # test_legacy_migrated_receipt_without_journal_is_require_human.)
    history = InMemoryHistory()
    history.append_journal("run-1", "PLANNED", utc_now())
    history.append_journal("run-1", "SELECTED", utc_now())
    decision = resolve_recovery_action(history, "run-1")
    assert decision.action == REQUIRE_HUMAN
    assert decision.reason != "delivered-but-not-committed"


def test_legacy_migrated_receipt_without_journal_is_require_human(tmp_path) -> None:
    # G4-002F: a GENUINE pre-v3 receipt (migrated from a v1 store, NULL
    # attempt_id, no operation, no delivery journal) remains readable and
    # immutable — but it never authorizes COMMIT_HISTORY without a delivery
    # journal tail: REQUIRE_HUMAN.
    import sqlite3

    from omda.storage import SqliteHistory

    path = tmp_path / "legacy.db"
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE run_journal (journal_id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "run_id TEXT NOT NULL, transition TEXT NOT NULL, at TEXT NOT NULL, detail TEXT)"
    )
    conn.execute(
        "CREATE TABLE genre_pick_history (pick_index INTEGER PRIMARY KEY, "
        "run_id TEXT NOT NULL, genre_id TEXT NOT NULL, committed_at TEXT NOT NULL)"
    )
    conn.execute(
        "CREATE TABLE album_history (album_id TEXT PRIMARY KEY, canonical_id TEXT, "
        "canonical_source TEXT, identity_confidence TEXT NOT NULL, run_id TEXT NOT NULL, "
        "recommended_at TEXT NOT NULL)"
    )
    conn.execute(
        "CREATE TABLE delivery_receipt (idempotency_key TEXT PRIMARY KEY, "
        "run_id TEXT NOT NULL, delivered_at TEXT NOT NULL, channel TEXT NOT NULL, "
        "status TEXT NOT NULL, target TEXT)"
    )
    conn.execute(
        "INSERT INTO delivery_receipt VALUES "
        "('run-1:markdown', 'run-1', '2026-01-01T00:00:00Z', 'markdown', 'ok', 'old.md')"
    )
    conn.execute("PRAGMA user_version = 1")
    conn.commit()
    conn.close()
    store = SqliteHistory(path)
    try:
        assert store.schema_version() == 3
        legacy = store.find_delivery_receipt("run-1:markdown")
        assert legacy is not None and legacy.attempt_id is None
        # Exact replay of the migrated row is a no-op (never changed).
        assert store.save_delivery_receipt(legacy) == legacy
        decision = resolve_recovery_action(store, "run-1")
        assert decision.action == REQUIRE_HUMAN  # no delivery journal tail
    finally:
        store.close()


def test_recovery_with_mismatched_receipt_key_is_require_human() -> None:
    # A returned receipt with the right run id but WRONG idempotency key/channel
    # must not authorize COMMIT_HISTORY (the stored receipt is looked up by the
    # expected key, so a corrupt entry with the correct key is the real probe).
    from tests.fakes import bound_receipt

    history = InMemoryHistory()
    history.append_journal("run-1", "DELIVERING", utc_now())
    history.append_journal("run-1", "DELIVERED", utc_now())
    bound_receipt(
        history, run_id="run-1", key="run-1:markdown", channel="pushplus"
    )  # WRONG channel for the expected key
    decision = resolve_recovery_action(history, "run-1")
    assert decision.action == REQUIRE_HUMAN


def test_recovery_with_failed_status_is_require_human() -> None:
    from tests.fakes import bound_receipt

    history = InMemoryHistory()
    _journal_after_delivery(history, "run-1")
    bound_receipt(
        history, run_id="run-1", key="run-1:markdown", channel="markdown",
        outcome="failed",
    )
    decision = resolve_recovery_action(history, "run-1")
    assert decision.action == REQUIRE_HUMAN


def test_recovery_only_commits_on_bound_ok_receipt_plus_delivery_journal() -> None:
    # The ONLY path to COMMIT_HISTORY: exact run/key/channel binding, status ok,
    # AND a journal that durably reached the post-delivery window.
    from tests.fakes import bound_receipt

    history = InMemoryHistory()
    _journal_after_delivery(history, "run-1")
    bound_receipt(
        history, run_id="run-1", key="run-1:markdown", channel="markdown",
        outcome="ok",
    )
    decision = resolve_recovery_action(history, "run-1")
    assert decision.action == COMMIT_HISTORY
    assert decision.reason == "delivered-but-not-committed"


# --- G4-004R re-review 3: human-confirmed delivered completes in the REAL engine ---


def test_real_engine_crash_human_confirmed_delivered_completes() -> None:
    # Reviewer reproduction: claim committed -> external call happened ->
    # finalize/evidence write "crashed" (IN_FLIGHT, no receipt) -> owner records
    # CONFIRMED_DELIVERED -> restarting the REAL engine must COMPLETE with one
    # external effect and one atomic history commit (ADR §6/§11, acceptance 8).
    from omda.ports.errors import StateCommitFailureError

    class FinalizeCrashHistory(InMemoryHistory):
        """First finalize fails (simulated crash) so the operation stays
        IN_FLIGHT with no attempt/receipt; later calls succeed."""

        def __init__(self) -> None:
            super().__init__()
            self.finalize_failures_left = 1

        def finalize_delivery_attempt(self, **kw):
            if self.finalize_failures_left > 0:
                self.finalize_failures_left -= 1
                raise StateCommitFailureError("simulated crash after external call")
            return super().finalize_delivery_attempt(**kw)

    history = FinalizeCrashHistory()
    delivery = FakeDelivery()
    engine = _engine(history, delivery)
    outcome = engine.run("run-crash")
    # The claim was committed, the external call happened, but the evidence
    # write crashed -> IN_FLIGHT, no receipt, RECOVERING.
    assert outcome.state == RECOVERING
    op = history.find_delivery_operation("run-crash:markdown")
    assert op is not None and op.state == "IN_FLIGHT_OR_MAY_HAVE_SENT"
    assert history.find_delivery_receipt("run-crash:markdown") is None
    assert delivery.calls == 1

    # Owner confirms delivery (append-only resolution, no receipt required).
    history.record_delivery_resolution(
        operation_key="run-crash:markdown",
        run_id="run-crash",
        idempotency_key="run-crash:markdown",
        attempt_id=None,
        outcome="CONFIRMED_DELIVERED",
        actor="owner",
        reason="wechat shows the push",
        decided_at="2026-08-21T12:00:00Z",
    )

    # Restart the real engine: recover() must complete via the resolution.
    restarted = _engine(history, delivery)
    recovered = restarted.recover("run-crash")
    assert recovered.state == COMPLETE
    assert delivery.calls == 1  # no second external delivery
    assert history.latest_pick_index() == 3  # one atomic history commit
