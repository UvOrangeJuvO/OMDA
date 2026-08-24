"""G4-002 — DeliveryOperation/Attempt/Resolution model, SQLite v1→v2 (ADR-0001).

Covers: schema migration to user_version 2 with the three new tables, the
atomic begin claim (created vs existing), CAS finalize, append-only attempt/
receipt/resolution, resolution transitions per §15 constraint 4, payload
digest binding, and v1 rows remaining readable after migration.
"""

from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

import pytest

from omda.ports.errors import InvariantFailureError
from omda.storage import SqliteHistory


def _digest(payload: str = "hello") -> str:
    import hashlib

    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _begin(history, run_id="run-1", key="run-1:pushplus", channel="pushplus"):
    return history.begin_delivery_operation(
        run_id=run_id, idempotency_key=key, channel=channel, payload_digest=_digest()
    )


def test_sqlite_migrates_to_v3_with_new_tables() -> None:
    with tempfile.TemporaryDirectory() as d:
        store = SqliteHistory(Path(d) / "runtime.db")
        try:
            assert store.schema_version() == 3
            names = set(store.table_names())
            assert {"delivery_operation", "delivery_attempt", "delivery_resolution"} <= names
            assert "delivery_receipt" in names  # v1 table preserved
        finally:
            store.close()


def test_v1_database_migrates_and_preserves_rows() -> None:
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "runtime.db"
        # Build a COMPLETE v1 physical layout (ADR-0002 D7 fingerprint contract:
        # four base tables, receipt WITHOUT attempt_id) with one receipt row.
        conn = sqlite3.connect(path)
        conn.execute(
            "CREATE TABLE run_journal ("
            "journal_id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL, "
            "transition TEXT NOT NULL, at TEXT NOT NULL, detail TEXT)"
        )
        conn.execute(
            "CREATE TABLE genre_pick_history ("
            "pick_index INTEGER PRIMARY KEY, run_id TEXT NOT NULL, "
            "genre_id TEXT NOT NULL, committed_at TEXT NOT NULL)"
        )
        conn.execute(
            "CREATE TABLE album_history ("
            "album_id TEXT PRIMARY KEY, canonical_id TEXT, canonical_source TEXT, "
            "identity_confidence TEXT NOT NULL, run_id TEXT NOT NULL, "
            "recommended_at TEXT NOT NULL)"
        )
        conn.execute(
            "CREATE TABLE delivery_receipt ("
            "idempotency_key TEXT PRIMARY KEY, run_id TEXT NOT NULL, "
            "delivered_at TEXT NOT NULL, channel TEXT NOT NULL, "
            "status TEXT NOT NULL, target TEXT)"
        )
        conn.execute(
            "INSERT INTO delivery_receipt VALUES "
            "('old:markdown', 'old', '2026-01-01T00:00:00Z', 'markdown', 'ok', 'old.md')"
        )
        conn.execute("PRAGMA user_version = 1")
        conn.commit()
        conn.close()

        store = SqliteHistory(path)
        try:
            assert store.schema_version() == 3
            old = store.find_delivery_receipt("old:markdown")
            assert old is not None and old.status == "ok" and old.run_id == "old"
            assert old.attempt_id is None  # pre-v3 rows keep null (no synthesis)
        finally:
            store.close()


def test_begin_creates_in_flight_operation_and_delivering_journal() -> None:
    with tempfile.TemporaryDirectory() as d:
        store = SqliteHistory(Path(d) / "runtime.db")
        try:
            snapshot = _begin(store)
            assert snapshot.created is True
            op = snapshot.operation
            assert op.idempotency_key == "run-1:pushplus"
            assert op.state == "IN_FLIGHT_OR_MAY_HAVE_SENT"
            assert op.version == 1
            assert op.payload_digest == _digest()
            assert op.run_id == "run-1" and op.channel == "pushplus"
            transitions = [e.transition for e in store.journal_after("run-1", 0)]
            assert "DELIVERING" in transitions
        finally:
            store.close()


def test_begin_existing_returns_snapshot_without_second_claim() -> None:
    with tempfile.TemporaryDirectory() as d:
        store = SqliteHistory(Path(d) / "runtime.db")
        try:
            first = _begin(store)
            second = _begin(store)
            assert second.created is False
            assert second.operation.idempotency_key == first.operation.idempotency_key
            assert second.operation.version == 1  # no second claim row
            # journal DELIVERING appended only once
            delivering = [
                e
                for e in store.journal_after("run-1", 0)
                if e.transition == "DELIVERING"
            ]
            assert len(delivering) == 1
        finally:
            store.close()


def test_finalize_cas_succeeds_writes_attempt_and_receipt() -> None:
    with tempfile.TemporaryDirectory() as d:
        store = SqliteHistory(Path(d) / "runtime.db")
        try:
            snapshot = _begin(store)
            op = store.finalize_delivery_attempt(
                operation_key="run-1:pushplus",
                expected_version=snapshot.operation.version,
                outcome="ok",
                evidence='{"code":200}',
                attempted_at="2026-08-21T00:00:01Z",
            )
            assert op.state == "SUCCEEDED"
            assert op.version == 2
            receipt = store.find_delivery_receipt("run-1:pushplus")
            assert receipt is not None and receipt.status == "ok"
            assert receipt.run_id == "run-1" and receipt.channel == "pushplus"
            # append-only attempt record exists
            assert store.find_delivery_operation("run-1:pushplus") is not None
        finally:
            store.close()


def test_finalize_wrong_version_fails_closed() -> None:
    with tempfile.TemporaryDirectory() as d:
        store = SqliteHistory(Path(d) / "runtime.db")
        try:
            _begin(store)
            with pytest.raises(InvariantFailureError):
                store.finalize_delivery_attempt(
                    operation_key="run-1:pushplus",
                    expected_version=99,
                    outcome="ok",
                    evidence="x",
                    attempted_at="2026-08-21T00:00:01Z",
                )
            assert store.find_delivery_operation("run-1:pushplus").state == (
                "IN_FLIGHT_OR_MAY_HAVE_SENT"
            )
            assert store.find_delivery_receipt("run-1:pushplus") is None
        finally:
            store.close()


def test_finalize_ambiguous_then_resolution_delivered() -> None:
    with tempfile.TemporaryDirectory() as d:
        store = SqliteHistory(Path(d) / "runtime.db")
        try:
            snapshot = _begin(store)
            store.finalize_delivery_attempt(
                operation_key="run-1:pushplus",
                expected_version=snapshot.operation.version,
                outcome="ambiguous",
                evidence="timeout",
                attempted_at="2026-08-21T00:00:01Z",
            )
            assert store.find_delivery_operation("run-1:pushplus").state == "AMBIGUOUS"
            op = store.record_delivery_resolution(
                operation_key="run-1:pushplus",
                run_id="run-1",
                idempotency_key="run-1:pushplus",
                outcome="CONFIRMED_DELIVERED",
                attempt_id=None,
                actor="owner",
                reason="wechat shows the push",
                decided_at="2026-08-21T12:00:00Z",
            )
            assert op.state == "RESOLVED_DELIVERED"
        finally:
            store.close()


def test_resolution_still_unknown_keeps_ambiguous() -> None:
    with tempfile.TemporaryDirectory() as d:
        store = SqliteHistory(Path(d) / "runtime.db")
        try:
            snapshot = _begin(store)
            store.finalize_delivery_attempt(
                operation_key="run-1:pushplus",
                expected_version=snapshot.operation.version,
                outcome="ambiguous",
                evidence="timeout",
                attempted_at="2026-08-21T00:00:01Z",
            )
            op = store.record_delivery_resolution(
                operation_key="run-1:pushplus",
                run_id="run-1",
                idempotency_key="run-1:pushplus",
                outcome="STILL_UNKNOWN",
                attempt_id=None,
                actor="owner",
                reason="cannot reach phone",
                decided_at="2026-08-21T12:00:00Z",
            )
            assert op.state == "AMBIGUOUS"  # still blocked
        finally:
            store.close()


def test_resolution_from_succeeded_fails_closed() -> None:
    # §15 constraint 4: SUCCEEDED must not be silently rewritten by a plain
    # resolution — a correction needs a separate audited decision.
    with tempfile.TemporaryDirectory() as d:
        store = SqliteHistory(Path(d) / "runtime.db")
        try:
            snapshot = _begin(store)
            store.finalize_delivery_attempt(
                operation_key="run-1:pushplus",
                expected_version=snapshot.operation.version,
                outcome="ok",
                evidence="ok",
                attempted_at="2026-08-21T00:00:01Z",
            )
            with pytest.raises(InvariantFailureError):
                store.record_delivery_resolution(
                    operation_key="run-1:pushplus",
                    run_id="run-1",
                    idempotency_key="run-1:pushplus",
                    outcome="CONFIRMED_NOT_DELIVERED",
                    attempt_id=None,
                    actor="owner",
                    reason="mistake",
                    decided_at="2026-08-21T12:00:00Z",
                )
        finally:
            store.close()


def test_begin_requires_matching_digest_on_replay() -> None:
    # G4-002C (ADR-0001 §15-5 / ADR-0002 AC-3): the same key cannot be replayed
    # with different content — begin with a mismatched run/channel/digest
    # binding FAILS CLOSED in the storage transaction, before any network call.
    with tempfile.TemporaryDirectory() as d:
        store = SqliteHistory(Path(d) / "runtime.db")
        try:
            _begin(store, key="run-1:pushplus")
            with pytest.raises(InvariantFailureError):
                store.begin_delivery_operation(
                    run_id="run-1",
                    idempotency_key="run-1:pushplus",
                    channel="pushplus",
                    payload_digest=_digest("different"),
                )
            # The stored binding is authoritative and untouched.
            assert store.find_delivery_operation("run-1:pushplus").payload_digest == _digest()
            # A same-binding replay is still a no-op snapshot (created=False).
            replay = store.begin_delivery_operation(
                run_id="run-1",
                idempotency_key="run-1:pushplus",
                channel="pushplus",
                payload_digest=_digest(),
            )
            assert replay.created is False
        finally:
            store.close()


def test_in_memory_history_matches_semantics() -> None:
    from tests.fakes import InMemoryHistory

    history = InMemoryHistory()
    snap = history.begin_delivery_operation(
        run_id="run-1",
        idempotency_key="run-1:pushplus",
        channel="pushplus",
        payload_digest=_digest(),
    )
    assert snap.created is True and snap.operation.state == "IN_FLIGHT_OR_MAY_HAVE_SENT"
    second = history.begin_delivery_operation(
        run_id="run-1",
        idempotency_key="run-1:pushplus",
        channel="pushplus",
        payload_digest=_digest(),
    )
    assert second.created is False
    op = history.finalize_delivery_attempt(
        operation_key="run-1:pushplus",
        expected_version=1,
        outcome="ambiguous",
        evidence="timeout",
        attempted_at="2026-08-21T00:00:01Z",
    )
    assert op.state == "AMBIGUOUS"
    op2 = history.record_delivery_resolution(
        operation_key="run-1:pushplus",
        run_id="run-1",
        idempotency_key="run-1:pushplus",
        outcome="CONFIRMED_DELIVERED",
        attempt_id=None,
        actor="owner",
        reason="verified",
        decided_at="2026-08-21T12:00:00Z",
    )
    assert op2.state == "RESOLVED_DELIVERED"
    with pytest.raises(InvariantFailureError):
        history.finalize_delivery_attempt(
            operation_key="run-1:pushplus",
            expected_version=99,
            outcome="ok",
            evidence="x",
            attempted_at="2026-08-21T00:00:02Z",
        )


# --- G4-002B re-review 3: §15-5 binding + receipt-attempt association ----------


def test_cross_bound_resolution_fails_closed() -> None:
    # Reviewer reproduction: a resolution for operation A carrying run/key/
    # attempt fields belonging to operation B must FAIL CLOSED (ADR §15-5).
    with tempfile.TemporaryDirectory() as d:
        store = SqliteHistory(Path(d) / "runtime.db")
        try:
            for key in ("run-a:pushplus", "run-b:pushplus"):
                snap = store.begin_delivery_operation(
                    run_id=key.partition(":")[0],
                    idempotency_key=key,
                    channel="pushplus",
                    payload_digest=_digest(key),
                )
                store.finalize_delivery_attempt(
                    operation_key=key,
                    expected_version=snap.operation.version,
                    outcome="ambiguous",
                    evidence="timeout",
                    attempted_at="2026-08-21T00:00:01Z",
                )
            # Operation A resolved with operation B's run/key/attempt fields.
            with pytest.raises(InvariantFailureError):
                store.record_delivery_resolution(
                    operation_key="run-a:pushplus",
                    run_id="run-b",
                    idempotency_key="run-b:pushplus",
                    attempt_id="run-b:pushplus#1",
                    outcome="CONFIRMED_DELIVERED",
                    actor="owner",
                    reason="cross-bound",
                    decided_at="2026-08-21T12:00:00Z",
                )
            assert store.find_delivery_operation("run-a:pushplus").state == "AMBIGUOUS"
        finally:
            store.close()


def test_resolution_attempt_must_belong_to_operation() -> None:
    with tempfile.TemporaryDirectory() as d:
        store = SqliteHistory(Path(d) / "runtime.db")
        try:
            snap = store.begin_delivery_operation(
                run_id="run-a",
                idempotency_key="run-a:pushplus",
                channel="pushplus",
                payload_digest=_digest(),
            )
            store.finalize_delivery_attempt(
                operation_key="run-a:pushplus",
                expected_version=snap.operation.version,
                outcome="ambiguous",
                evidence="timeout",
                attempted_at="2026-08-21T00:00:01Z",
            )
            # attempt id from a DIFFERENT operation -> fail closed.
            with pytest.raises(InvariantFailureError):
                store.record_delivery_resolution(
                    operation_key="run-a:pushplus",
                    run_id="run-a",
                    idempotency_key="run-a:pushplus",
                    attempt_id="run-other:pushplus#1",
                    outcome="CONFIRMED_DELIVERED",
                    actor="owner",
                    reason="wrong attempt",
                    decided_at="2026-08-21T12:00:00Z",
                )
        finally:
            store.close()


def test_finalized_receipt_binds_generated_attempt_id() -> None:
    # ADR-0001: new finalized receipts bind their generated attempt id; the
    # migrated SQLite table exposes the association (v1 rows may stay null).
    with tempfile.TemporaryDirectory() as d:
        store = SqliteHistory(Path(d) / "runtime.db")
        try:
            assert store.schema_version() == 3  # v3 migration adds the column
            snap = store.begin_delivery_operation(
                run_id="run-a",
                idempotency_key="run-a:pushplus",
                channel="pushplus",
                payload_digest=_digest(),
            )
            store.finalize_delivery_attempt(
                operation_key="run-a:pushplus",
                expected_version=snap.operation.version,
                outcome="ok",
                evidence="ok",
                attempted_at="2026-08-21T00:00:01Z",
            )
            receipt = store.find_delivery_receipt("run-a:pushplus")
            assert receipt is not None
            assert receipt.attempt_id == "run-a:pushplus#1"
        finally:
            store.close()


def test_delivering_journal_records_key_and_digest() -> None:
    with tempfile.TemporaryDirectory() as d:
        store = SqliteHistory(Path(d) / "runtime.db")
        try:
            store.begin_delivery_operation(
                run_id="run-a",
                idempotency_key="run-a:pushplus",
                channel="pushplus",
                payload_digest=_digest(),
            )
            delivering = next(
                e for e in store.journal_after("run-a", 0) if e.transition == "DELIVERING"
            )
            assert delivering.detail is not None
            assert delivering.detail.get("idempotency_key") == "run-a:pushplus"
            assert delivering.detail.get("payload_digest") == _digest()
        finally:
            store.close()


def test_in_memory_cross_bound_resolution_fails_closed() -> None:
    from tests.fakes import InMemoryHistory

    history = InMemoryHistory()
    for key in ("run-a:pushplus", "run-b:pushplus"):
        snap = history.begin_delivery_operation(
            run_id=key.partition(":")[0],
            idempotency_key=key,
            channel="pushplus",
            payload_digest=_digest(key),
        )
        history.finalize_delivery_attempt(
            operation_key=key,
            expected_version=snap.operation.version,
            outcome="ambiguous",
            evidence="timeout",
            attempted_at="2026-08-21T00:00:01Z",
        )
    with pytest.raises(InvariantFailureError):
        history.record_delivery_resolution(
            operation_key="run-a:pushplus",
            run_id="run-b",
            idempotency_key="run-b:pushplus",
            attempt_id="run-b:pushplus#1",
            outcome="CONFIRMED_DELIVERED",
            actor="owner",
            reason="cross-bound",
            decided_at="2026-08-21T12:00:00Z",
        )
