"""T1.4 contract tests: Port shapes, domain error taxonomy, fake implementations.

Contract tests pin the application boundary so Adapters (G3/G4) and Core (G2)
cannot drift from it, and so ordinary CI never needs live RYM/MusicBrainz/LLM.
"""

from __future__ import annotations

import inspect
from typing import Protocol

import pytest
from tests.fakes import (
    FakeAlbumSource,
    FakeDelivery,
    FakeGenreSource,
    FakeLLM,
    InMemoryHistory,
)

from omda.ports import (
    LLM,
    AlbumEnricher,
    AlbumSource,
    CriticRatingSource,
    Delivery,
    DeliveryFailureError,
    DomainError,
    GenerationFailureError,
    GenreSource,
    HistoryPort,
    InsufficientCandidatesError,
    InvalidInputError,
    InvariantFailureError,
    SourceUnavailableError,
    StateCommitFailureError,
    ValidationFailureError,
)
from omda.ports.domain import (
    AlbumCandidate,
    AlbumIdentity,
    DeliveryReceipt,
    GenrePickRecord,
    GenreRef,
)

EXPECTED_PORTS = {
    "GenreSource": GenreSource,
    "AlbumSource": AlbumSource,
    "AlbumEnricher": AlbumEnricher,
    "CriticRatingSource": CriticRatingSource,
    "HistoryPort": HistoryPort,
    "LLM": LLM,
    "Delivery": Delivery,
}


def _protocol_methods(proto: type[Protocol]) -> set[str]:
    return {
        name
        for name in dir(proto)
        if not name.startswith("_") and callable(getattr(proto, name))
    }


# --- domain error taxonomy (SPEC §8) ---

EXPECTED_ERRORS = [
    InvalidInputError,
    SourceUnavailableError,
    InsufficientCandidatesError,
    InvariantFailureError,
    GenerationFailureError,
    ValidationFailureError,
    DeliveryFailureError,
    StateCommitFailureError,
]


def test_error_taxonomy_has_eight_distinct_domain_errors() -> None:
    assert len(EXPECTED_ERRORS) == 8
    for error in EXPECTED_ERRORS:
        assert issubclass(error, DomainError)
    assert len({e.__name__ for e in EXPECTED_ERRORS}) == 8


def test_domain_error_carries_message_and_detail() -> None:
    err = InvalidInputError("bad record", detail={"field": "genre_id"})
    assert err.message == "bad record"
    assert err.detail == {"field": "genre_id"}
    assert "bad record" in str(err)


# --- port shapes ---

def test_all_ports_define_minimal_method_sets() -> None:
    assert _protocol_methods(GenreSource) == {"list_eligible_genres"}
    # G3-007-004: the ADR-authorized provider-neutral source-envelope contract
    # is part of the public Port (not a concrete-only parallel API).
    assert _protocol_methods(AlbumSource) == {"candidates_for_genre", "source_batch"}
    assert _protocol_methods(AlbumEnricher) == {"enrich"}
    assert _protocol_methods(CriticRatingSource) == {"ratings_for"}
    assert _protocol_methods(LLM) == {"generate_narrative"}
    assert _protocol_methods(Delivery) == {"deliver"}
    # HistoryPort intentionally hosts journal + history + receipts (G0-007 decision).
    # Official history has a single atomic commit path only (G1-001).
    assert _protocol_methods(HistoryPort) == {
        "append_journal",
        "journal_after",
        "latest_pick_index",
        "cooldown_pick_indices",
        "excluded_album_identities",
        "commit_history",
        "save_delivery_receipt",
        "find_delivery_receipt",
        # ADR-0001 v2: atomic delivery claim / CAS finalize / resolution.
        "begin_delivery_operation",
        "finalize_delivery_attempt",
        "record_delivery_resolution",
        "find_delivery_operation",
    }


def test_ports_are_protocols_not_classes() -> None:
    for name, port in EXPECTED_PORTS.items():
        assert inspect.isclass(port), name
        assert issubclass(port, Protocol), name


# --- fakes satisfy the contracts ---

def test_inmemory_history_satisfies_history_port_shape() -> None:
    missing = _protocol_methods(HistoryPort) - {
        m for m in dir(InMemoryHistory) if not m.startswith("_")
    }
    assert missing == set()


def test_inmemory_history_journal_and_atomic_commit() -> None:
    history = InMemoryHistory()
    e1 = history.append_journal("run-1", "PLANNED", "2026-08-19T09:00:00+00:00")
    e2 = history.append_journal("run-1", "DELIVERED", "2026-08-19T09:05:00+00:00")
    assert e1.journal_id == 1 and e2.journal_id == 2
    assert [e.transition for e in history.journal_after("run-1", 1)] == ["DELIVERED"]

    picks = [
        GenrePickRecord(1, "ambient"),
        GenrePickRecord(2, "jazz"),
        GenrePickRecord(3, "krautrock"),
    ]
    identities = [AlbumIdentity(f"alb-{i}") for i in range(1, 4)]
    history.commit_history("run-1", picks, identities, "2026-08-19T09:06:00+00:00")
    assert history.latest_pick_index() == 3
    assert history.cooldown_pick_indices("ambient") == [1]
    assert history.excluded_album_identities() == frozenset(identities)
    assert [e.transition for e in history.journal_after("run-1", 2)] == ["HISTORY_COMMITTED"]

    receipt = DeliveryReceipt(
        run_id="run-1",
        idempotency_key="run-1/markdown",
        delivered_at="2026-08-19T09:05:00+00:00",
        channel="markdown",
        status="ok",
    )
    history.save_delivery_receipt(receipt)
    assert history.find_delivery_receipt("run-1/markdown") == receipt
    assert history.find_delivery_receipt("missing") is None


def test_inmemory_history_commit_is_all_or_nothing() -> None:
    history = InMemoryHistory()
    existing = AlbumIdentity("alb-9")
    history.commit_history("run-0", [], [existing], "2026-08-19T09:00:00+00:00")

    from omda.ports.errors import InvariantFailureError

    picks = [GenrePickRecord(1, "ambient"), GenrePickRecord(2, "jazz")]
    conflicting = [AlbumIdentity("alb-9"), AlbumIdentity("alb-10")]  # alb-9 duplicates
    try:
        history.commit_history("run-1", picks, conflicting, "2026-08-19T09:06:00+00:00")
        raise AssertionError("expected InvariantFailureError")
    except InvariantFailureError:
        pass
    # Nothing changed: picks not written, journal has no HISTORY_COMMITTED for run-1.
    assert history.latest_pick_index() == 0
    assert history.cooldown_pick_indices("ambient") == []
    assert history.journal_after("run-1", 0) == []
    assert history.excluded_album_identities() == frozenset({existing})


def test_fake_delivery_is_idempotent() -> None:
    delivery = FakeDelivery()
    first = delivery.deliver("payload", "run-1/key")
    second = delivery.deliver("payload", "run-1/key")
    assert first.status == "ok" and second.status == "ok"
    assert len(delivery.delivered) == 1  # same key never delivers a second external push


def test_inmemory_receipts_immutable_exact_replay_and_conflict() -> None:
    history = InMemoryHistory()
    ok_receipt = DeliveryReceipt(
        run_id="run-1",
        idempotency_key="k",
        delivered_at="2026-08-19T09:05:00+00:00",
        channel="markdown",
        status="ok",
    )
    assert history.save_delivery_receipt(ok_receipt) == ok_receipt
    # Exact replay: no-op, original preserved.
    assert history.save_delivery_receipt(ok_receipt) == ok_receipt
    # Success -> failed overwrite attempt must fail closed.
    failed_receipt = DeliveryReceipt(
        run_id="run-1",
        idempotency_key="k",
        delivered_at="2026-08-19T09:06:00+00:00",
        channel="markdown",
        status="failed",
    )
    from omda.ports.errors import InvariantFailureError

    with pytest.raises(InvariantFailureError):
        history.save_delivery_receipt(failed_receipt)
    assert history.find_delivery_receipt("k") == ok_receipt  # original unchanged


def test_fake_genre_source_respects_eligibility() -> None:
    source = FakeGenreSource(
        [
            GenreRef("ambient", "Ambient", "Electronic", eligible=True),
            GenreRef("tiny", "Tiny Micro", "Experimental", eligible=False),
        ]
    )
    assert [g.genre_id for g in source.list_eligible_genres()] == ["ambient"]


def test_fake_album_source_filters_by_genre_and_limit() -> None:
    source = FakeAlbumSource(
        {
            "ambient": [
                AlbumCandidate("a1", "Album One", "Artist One"),
                AlbumCandidate("a2", "Album Two", "Artist Two"),
            ]
        }
    )
    genre = GenreRef("ambient", "Ambient", "Electronic")
    assert [a.album_id for a in source.candidates_for_genre(genre)] == ["a1", "a2"]
    assert [a.album_id for a in source.candidates_for_genre(genre, limit=1)] == ["a1"]
    assert source.candidates_for_genre(GenreRef("jazz", "Jazz", "Jazz")) == []


def test_fake_llm_returns_fixed_text() -> None:
    llm = FakeLLM("Explanatory text.")
    assert llm.generate_narrative({"fact": "packet"}) == "Explanatory text."
