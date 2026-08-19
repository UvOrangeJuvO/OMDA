"""T1.5 SQLite runtime adapter tests: migration, transactions, persistence, no deletes."""

from __future__ import annotations

import sqlite3

import pytest

from omda.ports.domain import AlbumIdentity, DeliveryReceipt
from omda.storage import SqliteHistory

EXPECTED_TABLES = {
    "album_history",
    "delivery_receipt",
    "genre_pick_history",
    "run_journal",
}


def test_fresh_database_migrates_to_v1(tmp_path) -> None:
    db = SqliteHistory(tmp_path / "state.sqlite3")
    assert db.schema_version() == 1
    assert set(db.table_names()) >= EXPECTED_TABLES


def test_migration_is_idempotent_on_reopen(tmp_path) -> None:
    path = tmp_path / "state.sqlite3"
    SqliteHistory(path)
    reopened = SqliteHistory(path)  # must not raise
    assert reopened.schema_version() == 1


def test_memory_database_works() -> None:
    db = SqliteHistory(":memory:")
    entry = db.append_journal("run-1", "PLANNED", "2026-08-19T09:00:00+00:00")
    assert entry.journal_id == 1


def test_journal_append_and_read_back(tmp_path) -> None:
    db = SqliteHistory(tmp_path / "state.sqlite3")
    e1 = db.append_journal("run-1", "PLANNED", "2026-08-19T09:00:00+00:00", {"seed": "s"})
    e2 = db.append_journal("run-1", "DELIVERED", "2026-08-19T09:05:00+00:00")
    assert (e1.journal_id, e2.journal_id) == (1, 2)
    assert [e.transition for e in db.journal_after("run-1", 1)] == ["DELIVERED"]
    assert db.journal_after("run-2", 0) == []
    assert e1.detail == {"seed": "s"}


def test_pick_history_and_cooldown_indices(tmp_path) -> None:
    db = SqliteHistory(tmp_path / "state.sqlite3")
    assert db.latest_pick_index() == 0
    db.record_genre_pick("run-1", "ambient", 1, "2026-08-19T09:06:00+00:00")
    db.record_genre_pick("run-1", "jazz", 2, "2026-08-19T09:06:00+00:00")
    db.record_genre_pick("run-2", "ambient", 31, "2026-08-19T10:00:00+00:00")
    assert db.latest_pick_index() == 31
    assert db.cooldown_pick_indices("ambient") == [1, 31]
    assert db.cooldown_pick_indices("jazz") == [2]


def test_album_history_exclusion_set(tmp_path) -> None:
    db = SqliteHistory(tmp_path / "state.sqlite3")
    identity = AlbumIdentity("alb-1", canonical_id="mb-1", canonical_source="musicbrainz")
    db.record_album("run-1", identity, "2026-08-19T09:06:00+00:00")
    assert db.excluded_album_identities() == {identity}


def test_delivery_receipt_round_trip(tmp_path) -> None:
    db = SqliteHistory(tmp_path / "state.sqlite3")
    assert db.find_delivery_receipt("run-1/markdown") is None
    receipt = DeliveryReceipt(
        run_id="run-1",
        idempotency_key="run-1/markdown",
        delivered_at="2026-08-19T09:05:00+00:00",
        channel="markdown",
        status="ok",
        target="out/run-1.md",
    )
    db.save_delivery_receipt(receipt)
    assert db.find_delivery_receipt("run-1/markdown") == receipt


def test_transaction_rolls_back_on_constraint_violation(tmp_path) -> None:
    db = SqliteHistory(tmp_path / "state.sqlite3")
    db.record_genre_pick("run-1", "ambient", 1, "2026-08-19T09:06:00+00:00")
    # Duplicate primary key (pick_index=1) must fail and roll back atomically.
    with pytest.raises(sqlite3.IntegrityError):
        db.record_genre_pick("run-1", "jazz", 1, "2026-08-19T09:06:00+00:00")
    # No partial write survived the failed transaction.
    assert db.cooldown_pick_indices("jazz") == []
    assert db.latest_pick_index() == 1


def test_file_persistence_across_reopen(tmp_path) -> None:
    path = tmp_path / "state.sqlite3"
    db = SqliteHistory(path)
    db.record_genre_pick("run-1", "ambient", 1, "2026-08-19T09:06:00+00:00")
    reopened = SqliteHistory(path)
    assert reopened.latest_pick_index() == 1
    assert reopened.cooldown_pick_indices("ambient") == [1]


def test_adapter_is_append_only_no_delete_methods(tmp_path) -> None:
    db = SqliteHistory(tmp_path / "state.sqlite3")
    destructive = {
        name
        for name in dir(db)
        if any(token in name.lower() for token in ("delete", "drop", "clear", "reset", "truncate"))
    }
    assert destructive == set()
