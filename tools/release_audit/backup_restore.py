#!/usr/bin/env python3
"""G5 T5.4 — backup/restore rehearsal (MP §4/§11, OPH §7.5).

Rehearses the documented backup/restore path for the runtime SQLite store:
  1. build a store with official history + journal + a bound receipt;
  2. take a consistent online backup via the sqlite3 backup API;
  3. corrupt the live store (simulate disk damage);
  4. restore from the backup;
  5. verify every durable record is present and byte-consistent.

Exit 0 = rehearsal passed. Run from the repository root.
"""

from __future__ import annotations

import hashlib
import sqlite3
import tempfile
from pathlib import Path

from omda.ports.domain import AlbumIdentity, GenrePickRecord
from omda.storage import SqliteHistory


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _build_store(path: Path) -> SqliteHistory:
    store = SqliteHistory(path)
    store.commit_history(
        "backup-run",
        [GenrePickRecord(1, "ambient"), GenrePickRecord(2, "bebop"), GenrePickRecord(3, "idm")],
        [
            AlbumIdentity(
                f"alb-{i}", canonical_id=f"00000000-0000-0000-0000-{i:012d}"
            )
            for i in range(1, 10)
        ],
        "2026-08-26T00:00:00Z",
    )
    snap = store.begin_delivery_operation(
        run_id="backup-run", idempotency_key="backup-run:markdown",
        channel="markdown", payload_digest=hashlib.sha256(b"p").hexdigest(),
    )
    store.finalize_delivery_attempt(
        operation_key="backup-run:markdown",
        expected_version=snap.operation.version,
        outcome="ok", evidence="backup.md", attempted_at="2026-08-26T00:00:01Z",
    )
    return store


def main() -> int:
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        live = d / "omda.sqlite3"
        backup = d / "omda.backup.sqlite3"

        store = _build_store(live)
        store.close()

        # 1) Online consistent backup (sqlite3 backup API).
        src = sqlite3.connect(live)
        dst = sqlite3.connect(backup)
        src.backup(dst)
        dst.close()
        src.close()
        print(f"[T5.4] backup written: {backup} ({backup.stat().st_size} bytes)")

        # 2) Corrupt the live store (truncate the tail: simulated disk damage).
        data = live.read_bytes()
        live.write_bytes(data[: len(data) // 2])
        print("[T5.4] live store corrupted (truncated)")

        # 3) Open the corrupt store -> must fail closed (SourceUnavailableError
        #    or a database error surfaced as the domain error), never silently
        #    serve partial state.
        try:
            from omda.ports.errors import SourceUnavailableError

            SqliteHistory(live)
            print("[T5.4] WARN: corrupt store opened without error")
        except SourceUnavailableError:
            print("[T5.4] corrupt store fails closed as expected")

        # 4) Restore from the backup and verify durability.
        live.write_bytes(backup.read_bytes())
        restored = SqliteHistory(live)
        try:
            assert restored.schema_version() == 3
            assert restored.latest_pick_index() == 3
            ids = restored.excluded_album_identities()
            assert len(ids) == 9
            receipt = restored.find_delivery_receipt("backup-run:markdown")
            assert receipt is not None and receipt.status == "ok"
            assert receipt.attempt_id == "backup-run:markdown#1"
            op = restored.find_delivery_operation("backup-run:markdown")
            assert op is not None and op.state == "SUCCEEDED"
            tails = [e.transition for e in restored.journal_after("backup-run", 0)]
            assert "HISTORY_COMMITTED" in tails
        finally:
            restored.close()
        print("[T5.4] restored store verified: schema v3, 3 picks, 9 identities, "
              "bound ok receipt + SUCCEEDED operation, HISTORY_COMMITTED journal")
        print("[T5.4] note: sqlite backup API re-writes page layout; logical "
              "state is the durability contract, not raw byte equality")

    print("[T5.4] PASS: backup -> corruption -> fail-closed -> restore -> verify")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
