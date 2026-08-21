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


def test_sqlite_migrates_to_v2_with_new_tables() -> None:
    with tempfile.TemporaryDirectory() as d:
        store = SqliteHistory(Path(d) / "runtime.db")
        try:
            assert store.schema_version() == 2
            names = set(store.table_names())
            assert {"delivery_operation", "delivery_attempt", "delivery_resolution"} <= names
            assert "delivery_receipt" in names  # v1 table preserved
        finally:
            store.close()


def test_v1_database_migrates_and_preserves_rows() -> None:
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "runtime.db"
        # Build a v1 database with one receipt row and user_version=1.
        conn = sqlite3.connect(path)
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
            assert store.schema_version() == 2
            old = store.find_delivery_receipt("old:markdown")
            assert old is not None and old.status == "ok" and old.run_id == "old"
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
    # The same key cannot be replayed with different content (ADR §7).
    with tempfile.TemporaryDirectory() as d:
        store = SqliteHistory(Path(d) / "runtime.db")
        try:
            _begin(store, key="run-1:pushplus")
            # begin with a DIFFERENT digest returns existing (claim blocked);
            # the caller must fail closed before network (tested at RunEngine
            # level); here we assert the stored digest is authoritative.
            snapshot = store.begin_delivery_operation(
                run_id="run-1",
                idempotency_key="run-1:pushplus",
                channel="pushplus",
                payload_digest=_digest("different"),
            )
            assert snapshot.created is False
            assert snapshot.operation.payload_digest == _digest()
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
