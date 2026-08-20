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
from omda.ports.domain import AlbumCandidate, DeliveryReceipt, GenreRef
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
    history = InMemoryHistory()
    history.save_delivery_receipt(
        DeliveryReceipt(
            run_id="other-run",
            idempotency_key="other-run:markdown",
            delivered_at=utc_now(),
            channel="markdown",
            status="ok",
        )
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
