"""SQLite implementation of HistoryPort (T1.5).

Runtime state only — official history, run journal, delivery receipts and caches
live here. This is NEVER the community source of truth (SPEC §3.3): community
data stays in Git-reviewable text under ``data/``.

Data protection: this adapter is append/read only — there are no delete, update,
drop or reset operations. Real history/journal/receipt/recovery records are
protected user state; rollback is backup/migration/recovery, never deletion.

Transactions: every mutating method runs inside a single SQLite transaction
(autocommit via context manager) so partial writes cannot be observed.
Migration: schema ``user_version`` with a linear migration list; each open runs
pending migrations idempotently inside one transaction.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from omda.ports.domain import AlbumIdentity, DeliveryReceipt, JournalEntry

_SCHEMA_VERSION = 1

_MIGRATIONS: dict[int, list[str]] = {
    1: [
        """
        CREATE TABLE IF NOT EXISTS run_journal (
            journal_id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT NOT NULL,
            transition TEXT NOT NULL,
            at TEXT NOT NULL,
            detail TEXT
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS genre_pick_history (
            pick_index INTEGER PRIMARY KEY,
            run_id TEXT NOT NULL,
            genre_id TEXT NOT NULL,
            committed_at TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS album_history (
            album_id TEXT PRIMARY KEY,
            canonical_id TEXT,
            canonical_source TEXT,
            identity_confidence TEXT NOT NULL,
            run_id TEXT NOT NULL,
            recommended_at TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS delivery_receipt (
            idempotency_key TEXT PRIMARY KEY,
            run_id TEXT NOT NULL,
            delivered_at TEXT NOT NULL,
            channel TEXT NOT NULL,
            status TEXT NOT NULL,
            target TEXT
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_journal_run ON run_journal (run_id)",
        "CREATE INDEX IF NOT EXISTS idx_pick_genre ON genre_pick_history (genre_id)",
    ],
}


class SqliteHistory:
    """HistoryPort over SQLite. ``path`` may be a file path or ``":memory:"``.

    A single connection is held for the lifetime of the adapter so ``:memory:``
    databases behave correctly; call :meth:`close` when done.
    """

    def __init__(self, path: str | Path) -> None:
        self._path = str(path)
        self._conn = sqlite3.connect(self._path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._migrate(self._conn)

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> SqliteHistory:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # -- connection lifecycle -------------------------------------------------

    @staticmethod
    def _migrate(conn: sqlite3.Connection) -> None:
        current = conn.execute("PRAGMA user_version").fetchone()[0]
        for version in range(current + 1, _SCHEMA_VERSION + 1):
            statements = _MIGRATIONS[version]
            for statement in statements:
                conn.execute(statement)
            conn.execute(f"PRAGMA user_version = {version}")

    # -- run journal -----------------------------------------------------------

    def append_journal(
        self,
        run_id: str,
        transition: str,
        at: str,
        detail: dict | None = None,
    ) -> JournalEntry:
        with self._conn as conn:
            cursor = conn.execute(
                "INSERT INTO run_journal (run_id, transition, at, detail) VALUES (?, ?, ?, ?)",
                (run_id, transition, at, json.dumps(detail) if detail is not None else None),
            )
            journal_id = int(cursor.lastrowid)
        return JournalEntry(
            journal_id=journal_id,
            run_id=run_id,
            transition=transition,
            at=at,
            detail=detail,
        )

    def journal_after(self, run_id: str, after_journal_id: int) -> list[JournalEntry]:
        with self._conn as conn:
            rows = conn.execute(
                "SELECT journal_id, run_id, transition, at, detail FROM run_journal "
                "WHERE run_id = ? AND journal_id > ? ORDER BY journal_id ASC",
                (run_id, after_journal_id),
            ).fetchall()
        return [
            JournalEntry(
                journal_id=int(row["journal_id"]),
                run_id=row["run_id"],
                transition=row["transition"],
                at=row["at"],
                detail=json.loads(row["detail"]) if row["detail"] is not None else None,
            )
            for row in rows
        ]

    # -- official genre pick history (cooldown source) -------------------------

    def latest_pick_index(self) -> int:
        with self._conn as conn:
            row = conn.execute(
                "SELECT COALESCE(MAX(pick_index), 0) AS m FROM genre_pick_history"
            ).fetchone()
        return int(row["m"])

    def record_genre_pick(
        self, run_id: str, genre_id: str, pick_index: int, committed_at: str
    ) -> None:
        with self._conn as conn:
            conn.execute(
                "INSERT INTO genre_pick_history (pick_index, run_id, genre_id, committed_at) "
                "VALUES (?, ?, ?, ?)",
                (pick_index, run_id, genre_id, committed_at),
            )

    def cooldown_pick_indices(self, genre_id: str) -> list[int]:
        with self._conn as conn:
            rows = conn.execute(
                "SELECT pick_index FROM genre_pick_history "
                "WHERE genre_id = ? ORDER BY pick_index ASC",
                (genre_id,),
            ).fetchall()
        return [int(row["pick_index"]) for row in rows]

    # -- official album history (permanent exclusion) --------------------------

    def record_album(self, run_id: str, identity: AlbumIdentity, recommended_at: str) -> None:
        with self._conn as conn:
            conn.execute(
                "INSERT INTO album_history (album_id, canonical_id, canonical_source, "
                "identity_confidence, run_id, recommended_at) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    identity.album_id,
                    identity.canonical_id,
                    identity.canonical_source,
                    identity.identity_confidence,
                    run_id,
                    recommended_at,
                ),
            )

    def excluded_album_identities(self) -> set[AlbumIdentity]:
        with self._conn as conn:
            rows = conn.execute(
                "SELECT album_id, canonical_id, canonical_source, identity_confidence "
                "FROM album_history"
            ).fetchall()
        return {
            AlbumIdentity(
                album_id=row["album_id"],
                canonical_id=row["canonical_id"],
                canonical_source=row["canonical_source"],
                identity_confidence=row["identity_confidence"],
            )
            for row in rows
        }

    # -- delivery receipts (idempotency) ---------------------------------------

    def save_delivery_receipt(self, receipt: DeliveryReceipt) -> None:
        with self._conn as conn:
            conn.execute(
                "INSERT OR REPLACE INTO delivery_receipt "
                "(idempotency_key, run_id, delivered_at, channel, status, target) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    receipt.idempotency_key,
                    receipt.run_id,
                    receipt.delivered_at,
                    receipt.channel,
                    receipt.status,
                    receipt.target,
                ),
            )

    def find_delivery_receipt(self, idempotency_key: str) -> DeliveryReceipt | None:
        with self._conn as conn:
            row = conn.execute(
                "SELECT idempotency_key, run_id, delivered_at, channel, status, target "
                "FROM delivery_receipt WHERE idempotency_key = ?",
                (idempotency_key,),
            ).fetchone()
        if row is None:
            return None
        return DeliveryReceipt(
            run_id=row["run_id"],
            idempotency_key=row["idempotency_key"],
            delivered_at=row["delivered_at"],
            channel=row["channel"],
            status=row["status"],
            target=row["target"],
        )

    # -- introspection (tests/ops only, not part of the Port) ------------------

    def schema_version(self) -> int:
        with self._conn as conn:
            return int(conn.execute("PRAGMA user_version").fetchone()[0])

    def table_names(self) -> list[str]:
        with self._conn as conn:
            rows = conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name"
            ).fetchall()
        return [row["name"] for row in rows]


__all__ = ["SqliteHistory"]
