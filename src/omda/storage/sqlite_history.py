"""SQLite implementation of HistoryPort (T1.5; repaired G1-001/G1-002/G1-004).

Runtime state only — official history, run journal, delivery receipts and caches
live here. This is NEVER the community source of truth (SPEC §3.3): community
data stays in Git-reviewable text under ``data/``.

Data protection:
- append/read only for official history — the ONLY write path is
  ``commit_history``, an all-or-nothing unit of work (G1-001);
- delivery receipts are immutable per idempotency key (G1-002) — no
  INSERT OR REPLACE; conflicts fail closed with ``InvariantFailureError``;
- there are no delete, update, drop or reset operations.

Transactions: every mutating method runs inside a single SQLite transaction
(autocommit via context manager) so partial writes cannot be observed.
Migration: schema ``user_version`` with a linear migration list; each open runs
pending migrations idempotently inside one transaction.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from omda.ports.domain import (
    OP_AMBIGUOUS,
    OP_CONFIRMED_FAILED,
    OP_IN_FLIGHT_OR_MAY_HAVE_SENT,
    OP_RESOLVED_DELIVERED,
    OP_RESOLVED_NOT_DELIVERED,
    OP_SUCCEEDED,
    RESOLUTION_CONFIRMED_DELIVERED,
    RESOLUTION_CONFIRMED_NOT_DELIVERED,
    RESOLUTION_STILL_UNKNOWN,
    AlbumIdentity,
    DeliveryOperation,
    DeliveryOperationSnapshot,
    DeliveryReceipt,
    GenrePickRecord,
    JournalEntry,
    thaw_json,
)
from omda.ports.errors import (
    InvariantFailureError,
    SourceUnavailableError,
    StateCommitFailureError,
)

_SCHEMA_VERSION = 3

# Marker statement for the idempotent receipt-attempt column addition (G4-002B);
# handled specially by ``_migrate`` so it is a no-op when the column exists.
_ALTER_RECEIPT_ATTEMPT_ID = "ALTER TABLE delivery_receipt ADD COLUMN attempt_id TEXT"


def _utc_now() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).isoformat().replace("+00:00", "Z")

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
    # ADR-0001 v2 (G4-002): durable per-key delivery operations, append-only
    # attempt/resolution ledgers. v1 tables are untouched (rows stay valid).
    2: [
        """
        CREATE TABLE IF NOT EXISTS delivery_operation (
            operation_key   TEXT PRIMARY KEY,
            run_id          TEXT NOT NULL,
            channel         TEXT NOT NULL
                CHECK (channel IN ('markdown', 'pushplus')),
            payload_digest  TEXT NOT NULL,
            state           TEXT NOT NULL CHECK (state IN (
                'IN_FLIGHT_OR_MAY_HAVE_SENT', 'SUCCEEDED',
                'CONFIRMED_FAILED', 'AMBIGUOUS',
                'RESOLVED_DELIVERED', 'RESOLVED_NOT_DELIVERED')),
            version         INTEGER NOT NULL DEFAULT 1,
            created_at      TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS delivery_attempt (
            attempt_id      TEXT PRIMARY KEY,
            operation_key   TEXT NOT NULL
                REFERENCES delivery_operation(operation_key),
            outcome         TEXT NOT NULL
                CHECK (outcome IN ('ok', 'failed', 'ambiguous')),
            evidence        TEXT NOT NULL,
            attempted_at    TEXT NOT NULL
        )
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_attempt_op
            ON delivery_attempt (operation_key)
        """,
        """
        CREATE TABLE IF NOT EXISTS delivery_resolution (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            operation_key   TEXT NOT NULL
                REFERENCES delivery_operation(operation_key),
            run_id          TEXT NOT NULL,
            idempotency_key TEXT NOT NULL,
            attempt_id      TEXT,
            outcome         TEXT NOT NULL CHECK (outcome IN (
                'CONFIRMED_DELIVERED', 'CONFIRMED_NOT_DELIVERED',
                'STILL_UNKNOWN')),
            actor           TEXT NOT NULL,
            reason          TEXT NOT NULL,
            decided_at      TEXT NOT NULL
        )
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_resolution_op
            ON delivery_resolution (operation_key)
        """,
    ],
    # G4-002B: the immutable receipt binds its generated attempt id (v1 rows
    # stay NULL); the migration is a plain additive column (idempotent marker).
    3: [
        _ALTER_RECEIPT_ATTEMPT_ID,
    ],
}


class SqliteHistory:
    """HistoryPort over SQLite. ``path`` may be a file path or ``":memory:"``.

    A single connection is held for the lifetime of the adapter so ``:memory:``
    databases behave correctly; call :meth:`close` when done.

    Error boundary (G1-005): every public HistoryPort operation translates
    unexpected ``sqlite3.Error`` into the domain taxonomy — state writes surface
    ``StateCommitFailureError``, reads/availability surface
    ``SourceUnavailableError``, and the provider exception is preserved as
    ``__cause__``. Intentional ``InvariantFailureError`` conflicts are never
    caught or replaced.
    """

    def __init__(self, path: str | Path) -> None:
        self._path = str(path)
        conn: sqlite3.Connection | None = None
        try:
            conn = sqlite3.connect(self._path)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            # ADR-0001 v2 acceptance: concurrent independent connections race
            # on the same key; wait for the writer instead of failing instantly.
            conn.execute("PRAGMA busy_timeout = 5000")
            self._migrate(conn)
        except SourceUnavailableError:
            # G4-002D: a migration fail-closed (unknown/future fingerprint) must
            # still release the connection before propagating.
            if conn is not None:
                conn.close()
            raise
        except sqlite3.Error as exc:
            # Hygiene (G1-005): close a successfully-created connection when
            # migration later fails, then surface the domain error.
            if conn is not None:
                conn.close()
            raise SourceUnavailableError(
                f"cannot open/migrate runtime store at {self._path!r}"
            ) from exc
        self._conn = conn

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> SqliteHistory:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # -- connection lifecycle -------------------------------------------------

    @staticmethod
    def _migrate(conn: sqlite3.Connection) -> None:
        # BEGIN IMMEDIATE serializes concurrent migrations on the same file:
        # the second connection waits for the first to commit, then observes
        # the updated user_version and skips the (already applied) steps —
        # so non-idempotent steps such as ALTER TABLE ADD COLUMN run exactly
        # once even under two independent connections (ADR acceptance 1/9).
        conn.execute("BEGIN IMMEDIATE")
        try:
            current = conn.execute("PRAGMA user_version").fetchone()[0]
            # ADR-0002 D7 / G4-002D: unknown FUTURE versions fail closed —
            # a newer binary wrote this store; this binary must never guess.
            if current > _SCHEMA_VERSION:
                raise SourceUnavailableError(
                    f"runtime store schema version {current} is newer than supported "
                    f"{_SCHEMA_VERSION}; refusing to open (fail closed, no migration)"
                )
            # ADR-0002 D7 / ADR2-007: the version number alone is not a sufficient
            # migration precondition — the CURRENT physical layout is checked
            # BEFORE any write:
            #   v1 layout: four base tables, receipt WITHOUT attempt_id
            #   v2 layout: + delivery_operation/attempt/resolution
            #   v3 layout: v2 + receipt.attempt_id column
            # A stored version whose tables are missing is an UNKNOWN fingerprint
            # (corrupt/foreign schema) and fails closed — never silently
            # recreated as if it were a fresh database.
            if current >= 1:
                for table in (
                    "run_journal",
                    "genre_pick_history",
                    "album_history",
                    "delivery_receipt",
                ):
                    SqliteHistory._assert_table(conn, table, current, current)
            if current >= 2:
                for table in (
                    "delivery_operation",
                    "delivery_attempt",
                    "delivery_resolution",
                ):
                    SqliteHistory._assert_table(conn, table, current, current)
            for version in range(current + 1, _SCHEMA_VERSION + 1):
                statements = _MIGRATIONS[version]
                for statement in statements:
                    if statement == _ALTER_RECEIPT_ATTEMPT_ID:
                        cols = {
                            row[1]
                            for row in conn.execute(
                                "PRAGMA table_info(delivery_receipt)"
                            )
                        }
                        if "attempt_id" in cols:
                            continue
                    conn.execute(statement)
                conn.execute(f"PRAGMA user_version = {version}")
            if current == _SCHEMA_VERSION:
                # v3 is the final layout: a v3 store WITHOUT the attempt_id column
                # is an unknown fingerprint — fail closed instead of guessing.
                cols = {
                    row[1] for row in conn.execute("PRAGMA table_info(delivery_receipt)")
                }
                if "attempt_id" not in cols:
                    raise SourceUnavailableError(
                        f"runtime store user_version={current} lacks the v3 "
                        "delivery_receipt.attempt_id column; unknown schema "
                        "fingerprint (fail closed, no migration)"
                    )
            conn.commit()
        except BaseException:
            conn.rollback()
            raise

    @staticmethod
    def _assert_table(
        conn: sqlite3.Connection, table: str, user_version: int, target_version: int
    ) -> None:
        row = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)
        ).fetchone()
        if row is None:
            raise SourceUnavailableError(
                f"runtime store user_version={user_version} cannot migrate to v"
                f"{target_version}: required table {table!r} is missing "
                "(unknown schema fingerprint; fail closed, no migration)"
            )

    # -- run journal -----------------------------------------------------------

    def append_journal(
        self,
        run_id: str,
        transition: str,
        at: str,
        detail: dict | None = None,
    ) -> JournalEntry:
        try:
            with self._conn as conn:
                cursor = conn.execute(
                    "INSERT INTO run_journal (run_id, transition, at, detail) VALUES (?, ?, ?, ?)",
                    (
                        run_id,
                        transition,
                        at,
                        json.dumps(thaw_json(detail)) if detail is not None else None,
                    ),
                )
                journal_id = int(cursor.lastrowid)
        except sqlite3.Error as exc:
            raise StateCommitFailureError(
                f"append_journal failed for run {run_id!r}",
                detail={"run_id": run_id},
            ) from exc
        return JournalEntry(
            journal_id=journal_id,
            run_id=run_id,
            transition=transition,
            at=at,
            detail=detail,
        )

    def journal_after(self, run_id: str, after_journal_id: int) -> list[JournalEntry]:
        try:
            with self._conn as conn:
                rows = conn.execute(
                    "SELECT journal_id, run_id, transition, at, detail FROM run_journal "
                    "WHERE run_id = ? AND journal_id > ? ORDER BY journal_id ASC",
                    (run_id, after_journal_id),
                ).fetchall()
        except sqlite3.Error as exc:
            raise SourceUnavailableError(
                f"journal read failed for run {run_id!r}",
                detail={"run_id": run_id},
            ) from exc
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

    # -- official history reads -------------------------------------------------

    def latest_pick_index(self) -> int:
        try:
            with self._conn as conn:
                row = conn.execute(
                    "SELECT COALESCE(MAX(pick_index), 0) AS m FROM genre_pick_history"
                ).fetchone()
        except sqlite3.Error as exc:
            raise SourceUnavailableError(
                "latest_pick_index read failed"
            ) from exc
        return int(row["m"])

    def cooldown_pick_indices(self, genre_id: str) -> list[int]:
        try:
            with self._conn as conn:
                rows = conn.execute(
                    "SELECT pick_index FROM genre_pick_history "
                    "WHERE genre_id = ? ORDER BY pick_index ASC",
                    (genre_id,),
                ).fetchall()
        except sqlite3.Error as exc:
            raise SourceUnavailableError(
                f"cooldown_pick_indices read failed for genre {genre_id!r}",
                detail={"genre_id": genre_id},
            ) from exc
        return [int(row["pick_index"]) for row in rows]

    def excluded_album_identities(self) -> frozenset[AlbumIdentity]:
        try:
            with self._conn as conn:
                rows = conn.execute(
                    "SELECT album_id, canonical_id, canonical_source, identity_confidence "
                    "FROM album_history"
                ).fetchall()
        except sqlite3.Error as exc:
            raise SourceUnavailableError("excluded_album_identities read failed") from exc
        return frozenset(
            AlbumIdentity(
                album_id=row["album_id"],
                canonical_id=row["canonical_id"],
                canonical_source=row["canonical_source"],
                identity_confidence=row["identity_confidence"],
            )
            for row in rows
        )

    # -- ATOMIC official history commit (G1-001: the ONLY write path) ----------

    def commit_history(
        self,
        run_id: str,
        genre_picks: list[GenrePickRecord],
        album_identities: list[AlbumIdentity],
        committed_at: str,
    ) -> None:
        # The try/except wraps the ENTIRE transaction context (entry, SQL body,
        # commit and rollback) so no sqlite3.Error — including one raised on
        # context exit — can escape the Port (G1-005).
        try:
            with self._conn as conn:
                # Full pre-check: intra-batch duplicates and conflicts with
                # stored state raise the same domain exception as
                # InMemoryHistory (InvariantFailureError). Any unexpected SQLite
                # failure — including in the pre-check — is translated below.
                seen_picks: set[int] = set()
                for pick in genre_picks:
                    if pick.pick_index in seen_picks:
                        raise InvariantFailureError(
                            f"duplicate pick_index {pick.pick_index} within commit batch"
                        )
                    seen_picks.add(pick.pick_index)
                    if conn.execute(
                        "SELECT 1 FROM genre_pick_history WHERE pick_index = ?",
                        (pick.pick_index,),
                    ).fetchone():
                        raise InvariantFailureError(
                            f"pick_index {pick.pick_index} already in official history"
                        )
                seen_albums: set[str] = set()
                for identity in album_identities:
                    if identity.album_id in seen_albums:
                        raise InvariantFailureError(
                            f"duplicate album_id {identity.album_id!r} within commit batch"
                        )
                    seen_albums.add(identity.album_id)
                    if conn.execute(
                        "SELECT 1 FROM album_history WHERE album_id = ?",
                        (identity.album_id,),
                    ).fetchone():
                        raise InvariantFailureError(
                            f"album {identity.album_id!r} already in official history"
                        )
                for pick in genre_picks:
                    conn.execute(
                        "INSERT INTO genre_pick_history "
                        "(pick_index, run_id, genre_id, committed_at) VALUES (?, ?, ?, ?)",
                        (pick.pick_index, run_id, pick.genre_id, committed_at),
                    )
                for identity in album_identities:
                    conn.execute(
                        "INSERT INTO album_history (album_id, canonical_id, canonical_source, "
                        "identity_confidence, run_id, recommended_at) VALUES (?, ?, ?, ?, ?, ?)",
                        (
                            identity.album_id,
                            identity.canonical_id,
                            identity.canonical_source,
                            identity.identity_confidence,
                            run_id,
                            committed_at,
                        ),
                    )
                conn.execute(
                    "INSERT INTO run_journal (run_id, transition, at, detail) VALUES (?, ?, ?, ?)",
                    (
                        run_id,
                        "HISTORY_COMMITTED",
                        committed_at,
                        json.dumps(
                            {"picks": len(genre_picks), "albums": len(album_identities)}
                        ),
                    ),
                )
        except sqlite3.Error as exc:
            # Unexpected persistence failure — including transaction commit or
            # rollback failure — translates to the domain taxonomy, preserving
            # the provider exception as the cause (SPEC §3.2/§8).
            raise StateCommitFailureError(
                f"official history commit failed for run {run_id!r}",
                detail={"run_id": run_id},
            ) from exc
        # Any exception above rolls back all three areas; a successful context
        # exit commits them atomically inside the `with` block.

    # -- delivery receipts (immutable idempotency evidence, G1-002) -------------

    def save_delivery_receipt(self, receipt: DeliveryReceipt) -> DeliveryReceipt:
        try:
            with self._conn as conn:
                # G4-002F (ADR-0002 D7/D9): immutable existing evidence is
                # consulted FIRST. An already-migrated row (pre-v3, null
                # attempt_id) may be read and exactly replayed but NEVER
                # changed; every NEW v3 receipt must carry and transactionally
                # validate its matching operation/run/channel/attempt
                # association — a fresh key can never become "legacy" merely
                # by omitting the attempt field.
                row = conn.execute(
                    "SELECT run_id, delivered_at, channel, status, target, attempt_id "
                    "FROM delivery_receipt WHERE idempotency_key = ?",
                    (receipt.idempotency_key,),
                ).fetchone()
                if row is not None:
                    existing = DeliveryReceipt(
                        run_id=row["run_id"],
                        idempotency_key=receipt.idempotency_key,
                        delivered_at=row["delivered_at"],
                        channel=row["channel"],
                        status=row["status"],
                        target=row["target"],
                        attempt_id=row["attempt_id"],
                    )
                    if existing == receipt:
                        return existing  # exact replay (incl. legacy rows): no-op
                    raise InvariantFailureError(
                        f"delivery receipt conflict for key {receipt.idempotency_key!r}; "
                        "evidence is immutable (G1-002)"
                    )
                # New key: a v3 receipt MUST be bound to a real operation/attempt.
                if receipt.attempt_id is None:
                    raise InvariantFailureError(
                        f"cannot create a new delivery receipt for key "
                        f"{receipt.idempotency_key!r} without a bound delivery "
                        "attempt: only pre-v3 rows migrated from an older store "
                        "may carry a NULL attempt_id (ADR-0002 D7/D9); new v3 "
                        "receipts must finalize through an operation (G4-002F)"
                    )
                op = conn.execute(
                    "SELECT run_id, channel FROM delivery_operation "
                    "WHERE operation_key = ?",
                    (receipt.idempotency_key,),
                ).fetchone()
                if op is None:
                    raise InvariantFailureError(
                        f"receipt attempt_id {receipt.attempt_id!r} references "
                        f"no delivery operation {receipt.idempotency_key!r}"
                    )
                if op["run_id"] != receipt.run_id or op["channel"] != receipt.channel:
                    raise InvariantFailureError(
                        f"receipt attempt_id {receipt.attempt_id!r} is bound to "
                        f"operation {receipt.idempotency_key!r} "
                        f"(run {op['run_id']!r}, channel {op['channel']!r}) but "
                        f"the receipt declares ({receipt.run_id!r}, "
                        f"{receipt.channel!r}) — mismatched binding (§15-5)"
                    )
                bound = conn.execute(
                    "SELECT 1 FROM delivery_attempt "
                    "WHERE attempt_id = ? AND operation_key = ?",
                    (receipt.attempt_id, receipt.idempotency_key),
                ).fetchone()
                if bound is None:
                    raise InvariantFailureError(
                        f"receipt attempt_id {receipt.attempt_id!r} does not "
                        f"belong to operation {receipt.idempotency_key!r}"
                    )
                conn.execute(
                    "INSERT INTO delivery_receipt "
                    "(idempotency_key, run_id, delivered_at, channel, status, target, "
                    " attempt_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        receipt.idempotency_key,
                        receipt.run_id,
                        receipt.delivered_at,
                        receipt.channel,
                        receipt.status,
                        receipt.target,
                        receipt.attempt_id,
                    ),
                )
                return receipt
        except sqlite3.Error as exc:
            # InvariantFailureError above is not a sqlite3.Error and passes through.
            raise StateCommitFailureError(
                f"save_delivery_receipt failed for key {receipt.idempotency_key!r}",
                detail={"idempotency_key": receipt.idempotency_key},
            ) from exc

    def find_delivery_receipt(self, idempotency_key: str) -> DeliveryReceipt | None:
        try:
            with self._conn as conn:
                row = conn.execute(
                    "SELECT idempotency_key, run_id, delivered_at, channel, status, target, "
                    "       attempt_id "
                    "FROM delivery_receipt WHERE idempotency_key = ?",
                    (idempotency_key,),
                ).fetchone()
        except sqlite3.Error as exc:
            raise SourceUnavailableError(
                f"find_delivery_receipt failed for key {idempotency_key!r}",
                detail={"idempotency_key": idempotency_key},
            ) from exc
        if row is None:
            return None
        return DeliveryReceipt(
            run_id=row["run_id"],
            idempotency_key=row["idempotency_key"],
            delivered_at=row["delivered_at"],
            channel=row["channel"],
            status=row["status"],
            target=row["target"],
            attempt_id=row["attempt_id"],
        )

    # -- delivery operations (ADR-0001 v2: atomic claim / CAS / resolution) ----

    def begin_delivery_operation(
        self,
        *,
        run_id: str,
        idempotency_key: str,
        channel: str,
        payload_digest: str,
    ) -> DeliveryOperationSnapshot:
        # BEGIN IMMEDIATE (not the deferred ``with conn`` default) so the write
        # lock is taken at transaction start: two independent connections racing
        # on the same absent key serialize deterministically and only one can
        # ever insert (ADR-0001 §12 acceptance 1).
        conn = self._conn
        try:
            conn.execute("BEGIN IMMEDIATE")
            try:
                cursor = conn.execute(
                    "INSERT INTO delivery_operation "
                    "(operation_key, run_id, channel, payload_digest, state, version, "
                    " created_at) "
                    "VALUES (?, ?, ?, ?, ?, 1, ?) "
                    "ON CONFLICT DO NOTHING",
                    (
                        idempotency_key,
                        run_id,
                        channel,
                        payload_digest,
                        OP_IN_FLIGHT_OR_MAY_HAVE_SENT,
                        _utc_now(),
                    ),
                )
                created = cursor.rowcount == 1
                if created:
                    conn.execute(
                        "INSERT INTO run_journal (run_id, transition, at, detail) "
                        "VALUES (?, ?, ?, ?)",
                        (
                            run_id,
                            "DELIVERING",
                            _utc_now(),
                            json.dumps(
                                {
                                    "idempotency_key": idempotency_key,
                                    "payload_digest": payload_digest,  # G4-002B
                                }
                            ),
                        ),
                    )
                row = conn.execute(
                    "SELECT operation_key, run_id, channel, payload_digest, state, "
                    "       version, created_at "
                    "FROM delivery_operation WHERE operation_key = ?",
                    (idempotency_key,),
                ).fetchone()
                if (
                    not created
                    and row is not None
                    and (
                        row["run_id"] != run_id
                        or row["channel"] != channel
                        or row["payload_digest"] != payload_digest
                    )
                ):
                    # G4-002C (ADR-0001 §15-5): an existing operation row must
                    # bind to the SAME run/channel/payload digest — a caller
                    # replaying the key with different binding fields fails
                    # closed HERE (before any external call), in the same
                    # storage transaction. The operation row is the durable
                    # authority; the caller cannot relabel it.
                    raise InvariantFailureError(
                        f"delivery operation {idempotency_key!r} already exists "
                        f"bound to run/channel/digest "
                        f"({row['run_id']!r}, {row['channel']!r}, "
                        f"{row['payload_digest']!r}); caller supplied "
                        f"({run_id!r}, {channel!r}, {payload_digest!r}) — "
                        "mismatched binding fails closed (§15-5)"
                    )
                conn.commit()
            except BaseException:
                conn.rollback()
                raise
        except sqlite3.Error as exc:
            raise StateCommitFailureError(
                f"begin_delivery_operation failed for key {idempotency_key!r}",
                detail={"idempotency_key": idempotency_key},
            ) from exc
        return DeliveryOperationSnapshot(
            created=created,
            operation=self._row_to_operation(row),
        )

    def finalize_delivery_attempt(
        self,
        *,
        operation_key: str,
        expected_version: int,
        outcome: str,
        evidence: str,
        attempted_at: str,
    ) -> DeliveryOperation:
        state = {
            "ok": OP_SUCCEEDED,
            "failed": OP_CONFIRMED_FAILED,
            "ambiguous": OP_AMBIGUOUS,
        }.get(outcome)
        if state is None:
            raise InvariantFailureError(f"invalid attempt outcome {outcome!r}")
        try:
            with self._conn as conn:
                op_row = conn.execute(
                    "SELECT run_id, channel, payload_digest, state, version "
                    "FROM delivery_operation WHERE operation_key = ?",
                    (operation_key,),
                ).fetchone()
                if op_row is None:
                    raise InvariantFailureError(
                        f"no delivery operation for key {operation_key!r}"
                    )
                if int(op_row["version"]) != expected_version:
                    raise InvariantFailureError(
                        f"delivery operation version mismatch for {operation_key!r}: "
                        f"expected {expected_version}, stored {op_row['version']}"
                    )
                # The attempt is append-only and immutable (ADR-0001 v2 §5).
                seq = conn.execute(
                    "SELECT COUNT(*) AS n FROM delivery_attempt "
                    "WHERE operation_key = ?",
                    (operation_key,),
                ).fetchone()["n"]
                attempt_id = f"{operation_key}#{int(seq) + 1}"
                conn.execute(
                    "INSERT INTO delivery_attempt "
                    "(attempt_id, operation_key, outcome, evidence, attempted_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (attempt_id, operation_key, outcome, evidence, attempted_at),
                )
                # Immutable receipt (G1-002): the key must not already have one.
                if conn.execute(
                    "SELECT 1 FROM delivery_receipt WHERE idempotency_key = ?",
                    (operation_key,),
                ).fetchone():
                    raise InvariantFailureError(
                        f"delivery receipt already exists for key {operation_key!r}; "
                        "evidence is immutable (G1-002)"
                    )
                conn.execute(
                    "INSERT INTO delivery_receipt "
                    "(idempotency_key, run_id, delivered_at, channel, status, target, "
                    " attempt_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        operation_key,
                        op_row["run_id"],
                        attempted_at,
                        op_row["channel"],
                        outcome,
                        evidence,
                        attempt_id,
                    ),
                )
                cursor = conn.execute(
                    "UPDATE delivery_operation SET state = ?, version = version + 1 "
                    "WHERE operation_key = ? AND version = ?",
                    (state, operation_key, expected_version),
                )
                if cursor.rowcount != 1:
                    raise InvariantFailureError(
                        f"delivery operation CAS failed for key {operation_key!r}"
                    )
                updated = conn.execute(
                    "SELECT operation_key, run_id, channel, payload_digest, state, "
                    "       version, created_at "
                    "FROM delivery_operation WHERE operation_key = ?",
                    (operation_key,),
                ).fetchone()
        except sqlite3.Error as exc:
            raise StateCommitFailureError(
                f"finalize_delivery_attempt failed for key {operation_key!r}",
                detail={"operation_key": operation_key},
            ) from exc
        return self._row_to_operation(updated)

    def record_delivery_resolution(
        self,
        *,
        operation_key: str,
        run_id: str,
        idempotency_key: str,
        attempt_id: str | None,
        outcome: str,
        actor: str,
        reason: str,
        decided_at: str,
    ) -> DeliveryOperation:
        if outcome not in {
            RESOLUTION_CONFIRMED_DELIVERED,
            RESOLUTION_CONFIRMED_NOT_DELIVERED,
            RESOLUTION_STILL_UNKNOWN,
        }:
            raise InvariantFailureError(f"invalid resolution outcome {outcome!r}")
        try:
            with self._conn as conn:
                op_row = conn.execute(
                    "SELECT run_id, channel FROM delivery_operation "
                    "WHERE operation_key = ?",
                    (operation_key,),
                ).fetchone()
                if op_row is None:
                    raise InvariantFailureError(
                        f"no delivery operation for key {operation_key!r}"
                    )
                # G4-002B (§15-5): the resolution's redundant fields must bind to
                # the SAME operation — a cross-bound resolution fails closed.
                if op_row["run_id"] != run_id:
                    raise InvariantFailureError(
                        f"resolution run_id {run_id!r} does not match operation "
                        f"{operation_key!r} (stored {op_row['run_id']!r})"
                    )
                if idempotency_key != operation_key:
                    raise InvariantFailureError(
                        f"resolution idempotency_key {idempotency_key!r} does not match "
                        f"operation_key {operation_key!r}"
                    )
                if attempt_id is not None:
                    bound = conn.execute(
                        "SELECT 1 FROM delivery_attempt "
                        "WHERE attempt_id = ? AND operation_key = ?",
                        (attempt_id, operation_key),
                    ).fetchone()
                    if bound is None:
                        raise InvariantFailureError(
                            f"resolution attempt_id {attempt_id!r} does not belong to "
                            f"operation {operation_key!r}"
                        )
                conn.execute(
                    "INSERT INTO delivery_resolution "
                    "(operation_key, run_id, idempotency_key, attempt_id, outcome, "
                    " actor, reason, decided_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        operation_key,
                        run_id,
                        idempotency_key,
                        attempt_id,
                        outcome,
                        actor,
                        reason,
                        decided_at,
                    ),
                )
                new_state = {
                    RESOLUTION_CONFIRMED_DELIVERED: OP_RESOLVED_DELIVERED,
                    RESOLUTION_CONFIRMED_NOT_DELIVERED: OP_RESOLVED_NOT_DELIVERED,
                }.get(outcome)
                if new_state is not None:
                    # §15-4: only advance from in-flight/ambiguous; never
                    # silently rewrite SUCCEEDED/CONFIRMED_FAILED.
                    cursor = conn.execute(
                        "UPDATE delivery_operation SET state = ?, version = version + 1 "
                        "WHERE operation_key = ? AND state IN (?, ?)",
                        (
                            new_state,
                            operation_key,
                            OP_IN_FLIGHT_OR_MAY_HAVE_SENT,
                            OP_AMBIGUOUS,
                        ),
                    )
                    if cursor.rowcount != 1:
                        raise InvariantFailureError(
                            f"resolution cannot advance operation {operation_key!r} "
                            "from its current state (evidence immutable)"
                        )
                row = conn.execute(
                    "SELECT operation_key, run_id, channel, payload_digest, state, "
                    "       version, created_at "
                    "FROM delivery_operation WHERE operation_key = ?",
                    (operation_key,),
                ).fetchone()
        except sqlite3.Error as exc:
            raise StateCommitFailureError(
                f"record_delivery_resolution failed for key {operation_key!r}",
                detail={"operation_key": operation_key},
            ) from exc
        return self._row_to_operation(row)

    def find_delivery_operation(self, idempotency_key: str) -> DeliveryOperation | None:
        try:
            with self._conn as conn:
                row = conn.execute(
                    "SELECT operation_key, run_id, channel, payload_digest, state, "
                    "       version, created_at "
                    "FROM delivery_operation WHERE operation_key = ?",
                    (idempotency_key,),
                ).fetchone()
        except sqlite3.Error as exc:
            raise SourceUnavailableError(
                f"find_delivery_operation failed for key {idempotency_key!r}",
                detail={"idempotency_key": idempotency_key},
            ) from exc
        if row is None:
            return None
        return self._row_to_operation(row)

    @staticmethod
    def _row_to_operation(row: sqlite3.Row) -> DeliveryOperation:
        return DeliveryOperation(
            idempotency_key=row["operation_key"],
            run_id=row["run_id"],
            channel=row["channel"],
            payload_digest=row["payload_digest"],
            state=row["state"],
            version=int(row["version"]),
            created_at=row["created_at"],
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
