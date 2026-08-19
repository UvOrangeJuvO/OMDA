"""T1.5 SQLite runtime adapter tests: migration, atomic commit, immutable
receipts, persistence, no deletes (G1-001/G1-002 repaired behavior)."""

from __future__ import annotations

import sqlite3

import pytest

from omda.ports.domain import AlbumIdentity, DeliveryReceipt, GenrePickRecord
from omda.ports.errors import InvariantFailureError, StateCommitFailureError
from omda.storage import SqliteHistory

EXPECTED_TABLES = {
    "album_history",
    "delivery_receipt",
    "genre_pick_history",
    "run_journal",
}

AT = "2026-08-19T09:00:00+00:00"


def _picks(*indices_and_genres: tuple[int, str]) -> list[GenrePickRecord]:
    return [GenrePickRecord(index, genre) for index, genre in indices_and_genres]


def _albums(*album_ids: str) -> list[AlbumIdentity]:
    return [AlbumIdentity(aid) for aid in album_ids]


# --- migration ---


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
    entry = db.append_journal("run-1", "PLANNED", AT)
    assert entry.journal_id == 1


# --- journal ---


def test_journal_append_and_read_back(tmp_path) -> None:
    db = SqliteHistory(tmp_path / "state.sqlite3")
    e1 = db.append_journal("run-1", "PLANNED", AT, {"seed": "s"})
    e2 = db.append_journal("run-1", "DELIVERED", "2026-08-19T09:05:00+00:00")
    assert (e1.journal_id, e2.journal_id) == (1, 2)
    assert [e.transition for e in db.journal_after("run-1", 1)] == ["DELIVERED"]
    assert db.journal_after("run-2", 0) == []
    assert e1.detail == {"seed": "s"}


def test_journal_detail_is_immutable_mapping(tmp_path) -> None:
    db = SqliteHistory(tmp_path / "state.sqlite3")
    detail = {"seed": "s"}
    entry = db.append_journal("run-1", "PLANNED", AT, detail)
    # Mutating the caller's dict must not change the stored snapshot.
    detail["seed"] = "tampered"
    assert entry.detail == {"seed": "s"}
    with pytest.raises(TypeError):
        entry.detail["seed"] = "tampered"  # type: ignore[index]


# --- official history: atomic commit (G1-001) ---


def test_commit_history_writes_all_three_areas_atomically(tmp_path) -> None:
    db = SqliteHistory(tmp_path / "state.sqlite3")
    assert db.latest_pick_index() == 0
    db.commit_history(
        "run-1",
        _picks((1, "ambient"), (2, "jazz"), (3, "krautrock")),
        _albums("alb-1", "alb-2", "alb-3"),
        "2026-08-19T09:06:00+00:00",
    )
    assert db.latest_pick_index() == 3
    assert db.cooldown_pick_indices("ambient") == [1]
    assert db.excluded_album_identities() == frozenset(_albums("alb-1", "alb-2", "alb-3"))
    assert [e.transition for e in db.journal_after("run-1", 0)] == ["HISTORY_COMMITTED"]


def test_commit_history_failure_leaves_all_areas_unchanged(tmp_path) -> None:
    db = SqliteHistory(tmp_path / "state.sqlite3")
    # Seed a pre-existing album row to force a conflict with stored state.
    conn = sqlite3.connect(tmp_path / "state.sqlite3")
    conn.execute(
        "INSERT INTO album_history (album_id, identity_confidence, run_id, recommended_at) "
        "VALUES ('alb-99', 'exact', 'old-run', ?)",
        (AT,),
    )
    conn.commit()
    conn.close()

    with pytest.raises(InvariantFailureError):
        db.commit_history(
            "run-1",
            _picks((1, "ambient"), (2, "jazz"), (3, "krautrock")),
            _albums("alb-1", "alb-2", "alb-99"),  # conflicts with pre-seeded alb-99
            "2026-08-19T09:06:00+00:00",
        )
    # All three areas unchanged: no picks, no new albums, no HISTORY_COMMITTED.
    assert db.latest_pick_index() == 0
    assert db.cooldown_pick_indices("ambient") == []
    assert db.excluded_album_identities() == frozenset(_albums("alb-99"))
    assert db.journal_after("run-1", 0) == []


def test_commit_history_mid_batch_duplicate_pick_is_invariant_error(tmp_path) -> None:
    db = SqliteHistory(tmp_path / "state.sqlite3")
    conn = sqlite3.connect(tmp_path / "state.sqlite3")
    conn.execute(
        "INSERT INTO genre_pick_history (pick_index, run_id, genre_id, committed_at) "
        "VALUES (5, 'old-run', 'jazz', ?)",
        (AT,),
    )
    conn.commit()
    conn.close()

    with pytest.raises(InvariantFailureError):
        db.commit_history(
            "run-1",
            _picks((1, "ambient"), (5, "jazz"), (6, "krautrock")),  # pick 5 conflicts
            _albums("alb-1", "alb-2", "alb-3"),
            "2026-08-19T09:06:00+00:00",
        )
    assert db.latest_pick_index() == 5
    assert db.excluded_album_identities() == frozenset()
    assert db.journal_after("run-1", 0) == []


def test_commit_history_sqlite_error_translated_to_state_commit_failure(tmp_path) -> None:
    # Force an unexpected persistence failure (drop a table out from under the
    # adapter) and prove the provider exception never crosses the Port (G1-005).
    path = tmp_path / "state.sqlite3"
    db = SqliteHistory(path)
    conn = sqlite3.connect(path)
    conn.execute("DROP TABLE genre_pick_history")
    conn.commit()
    conn.close()

    with pytest.raises(StateCommitFailureError) as exc:
        db.commit_history("run-1", _picks((1, "ambient")), _albums("alb-1"), AT)
    assert isinstance(exc.value.__cause__, sqlite3.Error)
    assert "commit" in str(exc.value)
    # Nothing was partially written (genre_pick_history table was dropped, so
    # verify the surviving areas only).
    assert db.journal_after("run-1", 0) == []
    assert db.excluded_album_identities() == frozenset()


def test_no_public_per_row_history_write_methods(tmp_path) -> None:
    db = SqliteHistory(tmp_path / "state.sqlite3")
    public = {name for name in dir(db) if not name.startswith("_")}
    assert "record_genre_pick" not in public
    assert "record_album" not in public
    assert "commit_history" in public  # the ONLY official write path


# --- delivery receipts: immutable evidence (G1-002) ---


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
    assert db.save_delivery_receipt(receipt) == receipt
    assert db.find_delivery_receipt("run-1/markdown") == receipt


def test_delivery_receipt_exact_replay_is_noop(tmp_path) -> None:
    db = SqliteHistory(tmp_path / "state.sqlite3")
    receipt = DeliveryReceipt(
        run_id="run-1",
        idempotency_key="k",
        delivered_at=AT,
        channel="markdown",
        status="ok",
    )
    db.save_delivery_receipt(receipt)
    # Exact replay returns the original record and leaves storage unchanged.
    assert db.save_delivery_receipt(receipt) == receipt
    assert db.find_delivery_receipt("k") == receipt


def test_delivery_receipt_conflict_fails_closed(tmp_path) -> None:
    db = SqliteHistory(tmp_path / "state.sqlite3")
    ok_receipt = DeliveryReceipt(
        run_id="run-1",
        idempotency_key="k",
        delivered_at=AT,
        channel="markdown",
        status="ok",
    )
    db.save_delivery_receipt(ok_receipt)

    # Same key, different run: conflict must fail closed.
    other_run = DeliveryReceipt(
        run_id="run-2",
        idempotency_key="k",
        delivered_at=AT,
        channel="markdown",
        status="ok",
    )
    with pytest.raises(InvariantFailureError):
        db.save_delivery_receipt(other_run)

    # Same key, success -> failed: must never overwrite the ok evidence.
    failed_receipt = DeliveryReceipt(
        run_id="run-1",
        idempotency_key="k",
        delivered_at=AT,
        channel="markdown",
        status="failed",
    )
    with pytest.raises(InvariantFailureError):
        db.save_delivery_receipt(failed_receipt)

    # Original evidence byte-for-byte identical.
    assert db.find_delivery_receipt("k") == ok_receipt


def test_file_persistence_across_reopen(tmp_path) -> None:
    path = tmp_path / "state.sqlite3"
    db = SqliteHistory(path)
    db.commit_history("run-1", _picks((1, "ambient")), _albums("alb-1"), AT)
    db.close()
    reopened = SqliteHistory(path)
    assert reopened.latest_pick_index() == 1
    assert reopened.cooldown_pick_indices("ambient") == [1]
    assert reopened.excluded_album_identities() == frozenset(_albums("alb-1"))


def test_adapter_is_append_only_no_delete_methods(tmp_path) -> None:
    db = SqliteHistory(tmp_path / "state.sqlite3")
    destructive = {
        name
        for name in dir(db)
        if any(token in name.lower() for token in ("delete", "drop", "clear", "reset", "truncate"))
    }
    assert destructive == set()
