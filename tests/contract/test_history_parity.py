"""G1-005 parameterized parity tests: identical scenarios against
``InMemoryHistory`` and the SQLite HistoryPort implementation.

Every scenario must produce the same outcome (success, domain exception type and
unchanged state) on both implementations — no provider-specific exception may
leak through the Port.
"""

from __future__ import annotations

import pytest
from tests.fakes import InMemoryHistory

from omda.ports.domain import AlbumIdentity, GenrePickRecord
from omda.ports.errors import InvariantFailureError
from omda.storage import SqliteHistory

AT = "2026-08-19T09:00:00+00:00"

HISTORY_FACTORIES = [
    pytest.param(InMemoryHistory, id="in-memory"),
    pytest.param(lambda: SqliteHistory(":memory:"), id="sqlite"),
]


def _picks(*pairs: tuple[int, str]) -> list[GenrePickRecord]:
    return [GenrePickRecord(index, genre) for index, genre in pairs]


def _albums(*album_ids: str) -> list[AlbumIdentity]:
    return [AlbumIdentity(aid) for aid in album_ids]


def _assert_all_areas_unchanged(history) -> None:
    assert history.latest_pick_index() == 0
    assert history.cooldown_pick_indices("ambient") == []
    assert history.excluded_album_identities() == frozenset()
    assert history.journal_after("run-1", 0) == []


@pytest.mark.parametrize("factory", HISTORY_FACTORIES)
def test_normal_batch_commit_parity(factory) -> None:
    history = factory()
    history.commit_history(
        "run-1",
        _picks((1, "ambient"), (2, "jazz"), (3, "krautrock")),
        _albums("alb-1", "alb-2", "alb-3"),
        AT,
    )
    assert history.latest_pick_index() == 3
    assert history.cooldown_pick_indices("ambient") == [1]
    assert history.excluded_album_identities() == frozenset(_albums("alb-1", "alb-2", "alb-3"))
    assert [e.transition for e in history.journal_after("run-1", 0)] == ["HISTORY_COMMITTED"]


@pytest.mark.parametrize("factory", HISTORY_FACTORIES)
def test_intra_batch_duplicate_pick_index_parity(factory) -> None:
    history = factory()
    with pytest.raises(InvariantFailureError):
        history.commit_history(
            "run-1",
            _picks((1, "ambient"), (1, "jazz"), (3, "krautrock")),  # duplicate pick 1
            _albums("alb-1", "alb-2", "alb-3"),
            AT,
        )
    _assert_all_areas_unchanged(history)


@pytest.mark.parametrize("factory", HISTORY_FACTORIES)
def test_intra_batch_duplicate_album_parity(factory) -> None:
    history = factory()
    with pytest.raises(InvariantFailureError):
        history.commit_history(
            "run-1",
            _picks((1, "ambient"), (2, "jazz"), (3, "krautrock")),
            _albums("alb-1", "alb-1", "alb-3"),  # duplicate album alb-1
            AT,
        )
    _assert_all_areas_unchanged(history)


@pytest.mark.parametrize("factory", HISTORY_FACTORIES)
def test_conflict_with_stored_state_parity(factory) -> None:
    history = factory()
    history.commit_history("run-0", _picks((1, "ambient")), _albums("alb-1"), AT)
    with pytest.raises(InvariantFailureError):
        history.commit_history(
            "run-1",
            _picks((2, "jazz"), (3, "krautrock"), (4, "bebop")),
            _albums("alb-2", "alb-3", "alb-1"),  # alb-1 already stored
            AT,
        )
    # Stored state from run-0 is untouched; run-1 wrote nothing.
    assert history.latest_pick_index() == 1
    assert history.cooldown_pick_indices("ambient") == [1]
    assert history.excluded_album_identities() == frozenset(_albums("alb-1"))
    assert history.journal_after("run-1", 0) == []


@pytest.mark.parametrize("factory", HISTORY_FACTORIES)
def test_failure_never_writes_partial_or_history_committed(factory) -> None:
    history = factory()
    with pytest.raises(InvariantFailureError):
        history.commit_history(
            "run-1",
            _picks((1, "ambient"), (2, "jazz"), (3, "krautrock")),
            _albums("alb-1", "alb-2", "alb-2"),  # duplicate inside batch
            AT,
        )
    # Genre history untouched, Album history untouched, no HISTORY_COMMITTED.
    _assert_all_areas_unchanged(history)


@pytest.mark.parametrize("factory", HISTORY_FACTORIES)
def test_same_domain_exception_type_parity(factory) -> None:
    history = factory()
    try:
        history.commit_history(
            "run-1",
            _picks((1, "ambient"), (1, "jazz")),
            _albums("alb-1"),
            AT,
        )
        raise AssertionError("expected InvariantFailureError")
    except InvariantFailureError as exc:
        assert "pick_index" in str(exc)
        assert not isinstance(exc, Exception) or exc.__cause__ is None  # invariant, not storage
