"""G1-005 failure-injection tests: no ``sqlite3.Error`` escapes any public
HistoryPort operation of ``SqliteHistory``.

Every operation translates unexpected persistence failures to the domain
taxonomy — writes surface ``StateCommitFailureError``, reads/availability
surface ``SourceUnavailableError`` — with the provider exception preserved as
``__cause__``. Intentional ``InvariantFailureError`` conflicts are never
caught or replaced.
"""

from __future__ import annotations

import sqlite3

import pytest

from omda.ports.domain import AlbumIdentity, DeliveryReceipt, GenrePickRecord
from omda.ports.errors import (
    InvariantFailureError,
    SourceUnavailableError,
    StateCommitFailureError,
)
from omda.storage import SqliteHistory

AT = "2026-08-19T09:00:00+00:00"

RECEIPT = DeliveryReceipt(
    run_id="run-1",
    idempotency_key="k",
    delivered_at=AT,
    channel="markdown",
    status="ok",
)


def _drop_table(path, table: str) -> None:
    conn = sqlite3.connect(path)
    conn.execute(f"DROP TABLE {table}")
    conn.commit()
    conn.close()


# Each case: (operation call, table to drop, expected domain error).
CASE_PATHS = [
    pytest.param(
        lambda db: db.append_journal("run-1", "PLANNED", AT),
        "run_journal",
        StateCommitFailureError,
        id="append_journal",
    ),
    pytest.param(
        lambda db: db.journal_after("run-1", 0),
        "run_journal",
        SourceUnavailableError,
        id="journal_after",
    ),
    pytest.param(
        lambda db: db.latest_pick_index(),
        "genre_pick_history",
        SourceUnavailableError,
        id="latest_pick_index",
    ),
    pytest.param(
        lambda db: db.cooldown_pick_indices("ambient"),
        "genre_pick_history",
        SourceUnavailableError,
        id="cooldown_pick_indices",
    ),
    pytest.param(
        lambda db: db.excluded_album_identities(),
        "album_history",
        SourceUnavailableError,
        id="excluded_album_identities",
    ),
    pytest.param(
        lambda db: db.commit_history(
            "run-1",
            [GenrePickRecord(1, "ambient")],
            [AlbumIdentity("alb-1")],
            AT,
        ),
        "genre_pick_history",
        StateCommitFailureError,
        id="commit_history",
    ),
    pytest.param(
        lambda db: db.save_delivery_receipt(RECEIPT),
        "delivery_receipt",
        StateCommitFailureError,
        id="save_delivery_receipt",
    ),
    pytest.param(
        lambda db: db.find_delivery_receipt("k"),
        "delivery_receipt",
        SourceUnavailableError,
        id="find_delivery_receipt",
    ),
]


@pytest.mark.parametrize("operation,drop_table,expected", CASE_PATHS)
def test_public_operations_never_leak_sqlite_errors(
    tmp_path, operation, drop_table, expected
) -> None:
    path = tmp_path / "state.sqlite3"
    db = SqliteHistory(path)
    _drop_table(path, drop_table)

    with pytest.raises(expected) as exc:
        operation(db)
    assert isinstance(exc.value.__cause__, sqlite3.Error)
    assert isinstance(exc.value, expected)
    db.close()


def test_initialization_migration_failure_is_source_unavailable(tmp_path) -> None:
    # A directory in place of a database file makes sqlite open/migrate fail.
    target = tmp_path / "not-a-db.sqlite3"
    target.mkdir()
    with pytest.raises(SourceUnavailableError) as exc:
        SqliteHistory(target)
    assert isinstance(exc.value.__cause__, sqlite3.Error)


def test_invariant_conflicts_are_not_translated(tmp_path) -> None:
    db = SqliteHistory(tmp_path / "state.sqlite3")
    # commit_history intra-batch duplicate -> InvariantFailureError (not StateCommitFailureError).
    with pytest.raises(InvariantFailureError) as exc:
        db.commit_history(
            "run-1",
            [GenrePickRecord(1, "ambient"), GenrePickRecord(1, "jazz")],
            [AlbumIdentity("alb-1")],
            AT,
        )
    assert not isinstance(exc.value, StateCommitFailureError)
    assert exc.value.__cause__ is None

    # save_delivery_receipt conflict -> InvariantFailureError.
    db.save_delivery_receipt(RECEIPT)
    conflicting = DeliveryReceipt(
        run_id="run-2",
        idempotency_key="k",
        delivered_at=AT,
        channel="markdown",
        status="ok",
    )
    with pytest.raises(InvariantFailureError):
        db.save_delivery_receipt(conflicting)
    db.close()


# --- closed-connection probes (G1-005): every public operation translates ---

CLOSED_CASES = [
    pytest.param(
        lambda db: db.append_journal("run-1", "PLANNED", AT),
        StateCommitFailureError,
        id="append_journal",
    ),
    pytest.param(
        lambda db: db.journal_after("run-1", 0),
        SourceUnavailableError,
        id="journal_after",
    ),
    pytest.param(
        lambda db: db.latest_pick_index(),
        SourceUnavailableError,
        id="latest_pick_index",
    ),
    pytest.param(
        lambda db: db.cooldown_pick_indices("ambient"),
        SourceUnavailableError,
        id="cooldown_pick_indices",
    ),
    pytest.param(
        lambda db: db.excluded_album_identities(),
        SourceUnavailableError,
        id="excluded_album_identities",
    ),
    pytest.param(
        lambda db: db.commit_history(
            "run-1",
            [GenrePickRecord(1, "ambient")],
            [AlbumIdentity("alb-1")],
            AT,
        ),
        StateCommitFailureError,
        id="commit_history",
    ),
    pytest.param(
        lambda db: db.save_delivery_receipt(RECEIPT),
        StateCommitFailureError,
        id="save_delivery_receipt",
    ),
    pytest.param(
        lambda db: db.find_delivery_receipt("k"),
        SourceUnavailableError,
        id="find_delivery_receipt",
    ),
]


@pytest.mark.parametrize("operation,expected", CLOSED_CASES)
def test_closed_connection_never_leaks_sqlite_errors(operation, expected) -> None:
    db = SqliteHistory(":memory:")
    db.close()  # closed connection: context entry/exit and SQL all raise sqlite3.Error

    with pytest.raises(expected) as exc:
        operation(db)
    assert isinstance(exc.value.__cause__, sqlite3.Error)
    assert isinstance(exc.value, expected)


class _FailingCommitWrapper:
    """Delegates everything to a real sqlite3.Connection but fails on commit.

    Used to inject a transaction-finalization (context-exit) failure without
    patching the immutable C type ``sqlite3.Connection``.
    """

    def __init__(self, inner: sqlite3.Connection) -> None:
        object.__setattr__(self, "_inner", inner)

    def __getattr__(self, name):
        return getattr(self._inner, name)

    def commit(self) -> None:
        raise sqlite3.OperationalError("simulated commit failure")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        if exc_type is None:
            self.commit()
        else:
            self._inner.rollback()
        return False


def test_commit_history_transaction_finalize_failure(tmp_path) -> None:
    # Inject a commit failure on transaction exit; the boundary must translate it
    # to StateCommitFailureError with the provider exception as the cause (G1-005).
    db = SqliteHistory(tmp_path / "state.sqlite3")
    db._conn = _FailingCommitWrapper(db._conn)  # type: ignore[attr-defined]

    with pytest.raises(StateCommitFailureError) as exc:
        db.commit_history(
            "run-1",
            [GenrePickRecord(1, "ambient")],
            [AlbumIdentity("alb-1")],
            AT,
        )
    assert isinstance(exc.value.__cause__, sqlite3.Error)
    assert "commit" in str(exc.value)
    db.close()
