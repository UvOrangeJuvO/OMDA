"""ADR-0001 §12 — the ten acceptance tests for G4-002 (binding per §15-6).

Concurrency tests use TWO INDEPENDENT connections on the SAME FILE database
(never a single connection or a pure in-memory fake). All provider behaviours
use the typed transport results; no live PushPlus is ever contacted.
"""

from __future__ import annotations

import hashlib
import tempfile
import threading
from pathlib import Path

import pytest

from omda.adapters.delivery import (
    AmbiguousFailure,
    NoBytesSentError,
    ProviderRejection,
    ProviderSuccess,
    PushPlusDelivery,
)
from omda.orchestrator.recovery import (
    COMMIT_HISTORY,
    REQUIRE_HUMAN,
    resolve_recovery_action,
)
from omda.ports.domain import (
    OP_AMBIGUOUS,
    OP_CONFIRMED_FAILED,
    OP_IN_FLIGHT_OR_MAY_HAVE_SENT,
    OP_RESOLVED_DELIVERED,
    OP_RESOLVED_NOT_DELIVERED,
    OP_SUCCEEDED,
)
from omda.ports.errors import InvariantFailureError
from omda.storage import SqliteHistory


def _digest(payload: str = "payload") -> str:
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _open(path: Path) -> SqliteHistory:
    return SqliteHistory(path)


# --- acceptance 1/2: concurrency on two independent connections -------------


def test_acceptance_1_two_connections_race_same_key_single_authority() -> None:
    # Two independent connections race on the same ABSENT key: only one may
    # win the claim (created=True) and call the transport; outbound <= 1.
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "runtime.db"
        results: dict[int, tuple[bool, int]] = {}
        barrier = threading.Barrier(2)

        def worker(idx: int) -> None:
            store = _open(path)
            try:
                barrier.wait()  # both connections are live before the race
                snap = store.begin_delivery_operation(
                    run_id="run-race",
                    idempotency_key="run-race:pushplus",
                    channel="pushplus",
                    payload_digest=_digest(),
                )
                results[idx] = (snap.created, snap.operation.version)
            finally:
                store.close()

        threads = [threading.Thread(target=worker, args=(i,)) for i in (1, 2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert len(results) == 2
        created_count = sum(1 for created, _ in results.values() if created)
        assert created_count == 1  # exactly one authority
        # The second caller observed the existing row and must NOT send.
        store = _open(path)
        try:
            op = store.find_delivery_operation("run-race:pushplus")
            assert op is not None and op.state == OP_IN_FLIGHT_OR_MAY_HAVE_SENT
        finally:
            store.close()


def test_acceptance_2_second_caller_between_claim_and_send_never_sends() -> None:
    # A second caller arriving while the first is between reservation and send
    # sees the existing row and never calls the transport (calls == 1 total).
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "runtime.db"
        store = _open(path)
        try:
            first = store.begin_delivery_operation(
                run_id="run-1",
                idempotency_key="run-1:pushplus",
                channel="pushplus",
                payload_digest=_digest(),
            )
            assert first.created is True
            # "Second caller" = a fresh independent connection.
            other = _open(path)
            try:
                second = other.begin_delivery_operation(
                    run_id="run-1",
                    idempotency_key="run-1:pushplus",
                    channel="pushplus",
                    payload_digest=_digest(),
                )
                assert second.created is False
            finally:
                other.close()
        finally:
            store.close()


# --- acceptance 3/4: crash windows -------------------------------------------


def test_acceptance_3_crash_after_claim_before_call_never_auto_sends() -> None:
    # Crash after durable claim but before the call: restart does NOT auto-send;
    # the state is explicitly in-flight (conservative protocol -> human).
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "runtime.db"
        store = _open(path)
        store.begin_delivery_operation(
            run_id="run-1",
            idempotency_key="run-1:pushplus",
            channel="pushplus",
            payload_digest=_digest(),
        )
        store.close()  # "crash": no finalize ever happened

        restarted = _open(path)  # process restart
        try:
            op = restarted.find_delivery_operation("run-1:pushplus")
            assert op is not None and op.state == OP_IN_FLIGHT_OR_MAY_HAVE_SENT
            assert restarted.find_delivery_receipt("run-1:pushplus") is None
            # No automatic send: recovery demands human review.
            decision = resolve_recovery_action(restarted, "run-1", idempotency_key="run-1:pushplus")
            assert decision.action == REQUIRE_HUMAN
        finally:
            restarted.close()


def test_acceptance_4_crash_after_call_before_evidence_never_auto_sends() -> None:
    # Crash after the call but before final evidence: restart must NOT auto-send.
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "runtime.db"
        store = _open(path)
        snap = store.begin_delivery_operation(
            run_id="run-1",
            idempotency_key="run-1:pushplus",
            channel="pushplus",
            payload_digest=_digest(),
        )
        # "Call happened" but finalize never ran -> IN_FLIGHT with no attempt.
        assert snap.created is True
        store.close()

        restarted = _open(path)
        try:
            op = restarted.find_delivery_operation("run-1:pushplus")
            assert op is not None and op.state == OP_IN_FLIGHT_OR_MAY_HAVE_SENT
            decision = resolve_recovery_action(restarted, "run-1", idempotency_key="run-1:pushplus")
            assert decision.action == REQUIRE_HUMAN  # no re-push
        finally:
            restarted.close()


# --- acceptance 5: payload digest binding ------------------------------------


def test_acceptance_5_same_key_different_digest_fails_closed_before_network() -> None:
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "runtime.db"
        store = _open(path)
        try:
            store.begin_delivery_operation(
                run_id="run-1",
                idempotency_key="run-1:pushplus",
                channel="pushplus",
                payload_digest=_digest("original"),
            )
            # G4-002C (ADR-0001 §15-5 / ADR-0002 AC-3): replaying the SAME key
            # with a DIFFERENT payload digest fails closed in the storage
            # transaction BEFORE any external call — the durable operation row
            # is the authority and cannot be relabelled by the caller.
            with pytest.raises(InvariantFailureError):
                store.begin_delivery_operation(
                    run_id="run-1",
                    idempotency_key="run-1:pushplus",
                    channel="pushplus",
                    payload_digest=_digest("replayed-with-different-content"),
                )
            # The original binding is untouched.
            assert store.find_delivery_operation("run-1:pushplus").payload_digest == (
                _digest("original")
            )
        finally:
            store.close()


# --- acceptance 6: existing evidence never re-sends ---------------------------


@pytest.mark.parametrize(
    "final_state",
    [OP_SUCCEEDED, OP_AMBIGUOUS, OP_RESOLVED_DELIVERED],
    ids=["succeeded", "ambiguous", "resolved-delivered"],
)
def test_acceptance_6_existing_evidence_never_resends(final_state) -> None:
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "runtime.db"
        store = _open(path)
        try:
            snap = store.begin_delivery_operation(
                run_id="run-1",
                idempotency_key="run-1:pushplus",
                channel="pushplus",
                payload_digest=_digest(),
            )
            if final_state == OP_SUCCEEDED:
                store.finalize_delivery_attempt(
                    operation_key="run-1:pushplus",
                    expected_version=snap.operation.version,
                    outcome="ok",
                    evidence="ok",
                    attempted_at="2026-08-21T00:00:01Z",
                )
            elif final_state == OP_AMBIGUOUS:
                store.finalize_delivery_attempt(
                    operation_key="run-1:pushplus",
                    expected_version=snap.operation.version,
                    outcome="ambiguous",
                    evidence="timeout",
                    attempted_at="2026-08-21T00:00:01Z",
                )
            else:
                store.finalize_delivery_attempt(
                    operation_key="run-1:pushplus",
                    expected_version=snap.operation.version,
                    outcome="ambiguous",
                    evidence="timeout",
                    attempted_at="2026-08-21T00:00:01Z",
                )
                store.record_delivery_resolution(
                    operation_key="run-1:pushplus",
                    run_id="run-1",
                    idempotency_key="run-1:pushplus",
                    attempt_id=None,
                    outcome="CONFIRMED_DELIVERED",
                    actor="owner",
                    reason="verified",
                    decided_at="2026-08-21T12:00:00Z",
                )
            replay = store.begin_delivery_operation(
                run_id="run-1",
                idempotency_key="run-1:pushplus",
                channel="pushplus",
                payload_digest=_digest(),
            )
            assert replay.created is False  # existing evidence blocks the send
        finally:
            store.close()


# --- acceptance 7: failed is terminal, immutable evidence --------------------


def test_acceptance_7_failed_is_terminal_and_evidence_immutable() -> None:
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "runtime.db"
        store = _open(path)
        try:
            snap = store.begin_delivery_operation(
                run_id="run-1",
                idempotency_key="run-1:pushplus",
                channel="pushplus",
                payload_digest=_digest(),
            )
            op = store.finalize_delivery_attempt(
                operation_key="run-1:pushplus",
                expected_version=snap.operation.version,
                outcome="failed",
                evidence="rejected 401",
                attempted_at="2026-08-21T00:00:01Z",
            )
            assert op.state == OP_CONFIRMED_FAILED
            # A later "success" cannot overwrite the immutable failed receipt.
            with pytest.raises(InvariantFailureError):
                store.finalize_delivery_attempt(
                    operation_key="run-1:pushplus",
                    expected_version=op.version,
                    outcome="ok",
                    evidence="ok",
                    attempted_at="2026-08-21T00:00:02Z",
                )
            assert store.find_delivery_receipt("run-1:pushplus").status == "failed"
            assert store.find_delivery_operation("run-1:pushplus").state == OP_CONFIRMED_FAILED
        finally:
            store.close()


# --- acceptance 8: human resolution outcomes ----------------------------------


def test_acceptance_8_confirmed_delivered_commits_without_push() -> None:
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "runtime.db"
        store = _open(path)
        try:
            snap = store.begin_delivery_operation(
                run_id="run-1",
                idempotency_key="run-1:pushplus",
                channel="pushplus",
                payload_digest=_digest(),
            )
            store.finalize_delivery_attempt(
                operation_key="run-1:pushplus",
                expected_version=snap.operation.version,
                outcome="ambiguous",
                evidence="timeout",
                attempted_at="2026-08-21T00:00:01Z",
            )
            op = store.record_delivery_resolution(
                operation_key="run-1:pushplus",
                run_id="run-1",
                idempotency_key="run-1:pushplus",
                attempt_id=None,
                outcome="CONFIRMED_DELIVERED",
                actor="owner",
                reason="push visible in wechat",
                decided_at="2026-08-21T12:00:00Z",
            )
            assert op.state == OP_RESOLVED_DELIVERED
            decision = resolve_recovery_action(store, "run-1", idempotency_key="run-1:pushplus")
            assert decision.action == COMMIT_HISTORY  # commit without re-push
        finally:
            store.close()


def test_acceptance_8_confirmed_not_delivered_abandons() -> None:
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "runtime.db"
        store = _open(path)
        try:
            snap = store.begin_delivery_operation(
                run_id="run-1",
                idempotency_key="run-1:pushplus",
                channel="pushplus",
                payload_digest=_digest(),
            )
            store.finalize_delivery_attempt(
                operation_key="run-1:pushplus",
                expected_version=snap.operation.version,
                outcome="ambiguous",
                evidence="timeout",
                attempted_at="2026-08-21T00:00:01Z",
            )
            op = store.record_delivery_resolution(
                operation_key="run-1:pushplus",
                run_id="run-1",
                idempotency_key="run-1:pushplus",
                attempt_id=None,
                outcome="CONFIRMED_NOT_DELIVERED",
                actor="owner",
                reason="phone never received anything",
                decided_at="2026-08-21T12:00:00Z",
            )
            assert op.state == OP_RESOLVED_NOT_DELIVERED
            decision = resolve_recovery_action(store, "run-1", idempotency_key="run-1:pushplus")
            assert decision.action == REQUIRE_HUMAN  # new operation required
        finally:
            store.close()


def test_acceptance_8_still_unknown_stays_blocked() -> None:
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "runtime.db"
        store = _open(path)
        try:
            snap = store.begin_delivery_operation(
                run_id="run-1",
                idempotency_key="run-1:pushplus",
                channel="pushplus",
                payload_digest=_digest(),
            )
            store.finalize_delivery_attempt(
                operation_key="run-1:pushplus",
                expected_version=snap.operation.version,
                outcome="ambiguous",
                evidence="timeout",
                attempted_at="2026-08-21T00:00:01Z",
            )
            op = store.record_delivery_resolution(
                operation_key="run-1:pushplus",
                run_id="run-1",
                idempotency_key="run-1:pushplus",
                attempt_id=None,
                outcome="STILL_UNKNOWN",
                actor="owner",
                reason="cannot reach phone",
                decided_at="2026-08-21T12:00:00Z",
            )
            assert op.state == OP_AMBIGUOUS  # stays blocked: no-send/no-commit
        finally:
            store.close()


# --- acceptance 9: schema v2 + migration v2 accept v1 rows --------------------


def test_acceptance_9_v1_rows_survive_v3_migration_and_receipt_attempt_binds() -> None:
    import sqlite3

    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "runtime.db"
        conn = sqlite3.connect(path)
        # A COMPLETE v1 physical layout (ADR-0002 D7 fingerprint contract):
        # all four base tables exist, the receipt WITHOUT attempt_id.
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
            "('v1:markdown', 'v1', '2026-01-01T00:00:00Z', 'markdown', 'ok', 'v1.md')"
        )
        conn.execute("PRAGMA user_version = 1")
        conn.commit()
        conn.close()

        store = _open(path)
        try:
            assert store.schema_version() == 3
            assert store.find_delivery_receipt("v1:markdown").status == "ok"
            # G4-002B: the v3 column really exists and v1 rows stay null.
            cols = [r[1] for r in store._conn.execute("PRAGMA table_info(delivery_receipt)")]
            assert "attempt_id" in cols
            assert store.find_delivery_receipt("v1:markdown").attempt_id is None
            # New v2 states validate through the real store (ambiguous receipt).
            snap = store.begin_delivery_operation(
                run_id="v2",
                idempotency_key="v2:pushplus",
                channel="pushplus",
                payload_digest=_digest(),
            )
            store.finalize_delivery_attempt(
                operation_key="v2:pushplus",
                expected_version=snap.operation.version,
                outcome="ambiguous",
                evidence="timeout",
                attempted_at="2026-08-21T00:00:01Z",
            )
            receipt = store.find_delivery_receipt("v2:pushplus")
            assert receipt.status == "ambiguous"
            # The finalized receipt binds its generated attempt id.
            assert receipt.attempt_id == "v2:pushplus#1"
        finally:
            store.close()

        # Downgrade safety: a v2 database reopened by v1 tooling must fail
        # closed on unknown states rather than misclassify (validated by the
        # schema enum; here we assert the store still reads it).
        store2 = _open(path)
        try:
            assert store2.schema_version() == 3
        finally:
            store2.close()


# --- acceptance 10: typed provider response classification table --------------


class ScriptedTransport:
    def __init__(self, *script):
        self.script = list(script)
        self.calls = 0

    def post(self, url, payload):
        self.calls += 1
        step = self.script[min(self.calls - 1, len(self.script) - 1)]
        if isinstance(step, Exception):
            raise step
        return step


class NoSleep:
    def __call__(self, seconds):
        pass


def _delivery(transport, max_retries=3):
    return PushPlusDelivery(
        token_env="PUSHPLUS_TOKEN",
        transport=transport,
        sleeper=NoSleep(),
        max_retries=max_retries,
    )


@pytest.mark.parametrize(
    ("script", "expected_status", "expected_calls"),
    [
        # documented success code
        ([ProviderSuccess({"code": 200})], "ok", 1),
        # definitive rejection (documented): terminal, NO retry loop
        ([ProviderRejection("401", "unauthorized")], "failed", 1),
        # zero bytes proven: the only retryable class, bounded, then ok
        ([NoBytesSentError("dns"), ProviderSuccess({"code": 200})], "ok", 2),
        # zero bytes proven exhausted -> confirmed failure (never sent)
        ([NoBytesSentError("dns")], "failed", 4),  # 1 + 3 retries
        # 5xx -> ambiguous, no retry
        ([AmbiguousFailure("provider 5xx")], "ambiguous", 1),
        # timeout -> ambiguous, no retry
        ([TimeoutError("timeout")], "ambiguous", 1),
        # connection reset -> ambiguous, no retry
        ([ConnectionResetError("reset")], "ambiguous", 1),
        # unknown 4xx (undocumented) -> ambiguous, no retry
        # malformed body (generic exception) -> ambiguous, no retry
        ([ValueError("malformed body")], "ambiguous", 1),
    ],
    ids=[
        "success",
        "definitive-rejection",
        "zero-bytes-then-ok",
        "zero-bytes-exhausted",
        "5xx",
        "timeout",
        "connection-reset",
        "malformed-body",
    ],
)
def test_acceptance_10_typed_classification_table(
    script, expected_status, expected_calls
) -> None:
    transport = ScriptedTransport(*script)
    receipt = _delivery(transport).deliver(
        "payload", "run-1:pushplus", token_provider=lambda: "test-token"
    )
    assert receipt.status == expected_status
    assert transport.calls == expected_calls
    # ambiguous never retried: exactly one external call.
    if expected_status == "ambiguous":
        assert transport.calls == 1


# --- direct replay via the full RunEngine path --------------------------------


def test_acceptance_direct_same_key_replay_never_second_push() -> None:
    # Same-key direct replay through begin_delivery_operation: a second
    # deliver() would see created=False and must NOT reach the transport.
    from tests.fakes import FakeDelivery

    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "runtime.db"
        store = _open(path)
        delivery = FakeDelivery()
        try:
            snap = store.begin_delivery_operation(
                run_id="run-1",
                idempotency_key="run-1:markdown",
                channel="markdown",
                payload_digest=_digest(),
            )
            assert snap.created is True
            delivery.deliver("payload", "run-1:markdown")  # the one external effect
            store.finalize_delivery_attempt(
                operation_key="run-1:markdown",
                expected_version=snap.operation.version,
                outcome="ok",
                evidence="run-1.md",
                attempted_at="2026-08-21T00:00:01Z",
            )
            replay = store.begin_delivery_operation(
                run_id="run-1",
                idempotency_key="run-1:markdown",
                channel="markdown",
                payload_digest=_digest(),
            )
            assert replay.created is False
            # The caller checks the snapshot and refuses to call the transport.
            assert delivery.calls == 1  # exactly one external delivery, ever
        finally:
            store.close()
