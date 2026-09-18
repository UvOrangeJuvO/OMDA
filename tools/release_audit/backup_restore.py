#!/usr/bin/env python3
"""G5 T5.4 — strict backup/restore rehearsal (MP §4/§11, OPH §7.5, G5-007).

Rehearses the documented user-facing backup/restore procedure end to end:

  1. build a store with official history + journal + a bound receipt;
  2. STOP the writer (close the store) and take a consistent backup via the
     sqlite3 backup API from a fresh read connection;
  3. verify the backup itself opens and matches the logical state;
  4. corrupt the live store (truncate: simulated disk damage);
  5. detect the corruption — the corrupt store MUST be rejected. If both the
     domain open path AND an explicit integrity check accept it, the rehearsal
     FAILS (non-zero) because a corrupted store went undetected;
  6. PRESERVE the damaged copy (never overwrite evidence);
  7. atomically restore: write the backup to a temp file and rename over the
     live path (no partial-write window);
  8. verify logical integrity of the restored store (schema, picks, identities,
     bound receipt + SUCCEEDED operation, HISTORY_COMMITTED journal tail).

Exit 0 = rehearsal passed; non-zero = any step failed (including undetected
corruption). Run from the repository root.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import sqlite3
import tempfile
from pathlib import Path

from omda.ports.domain import AlbumIdentity, GenrePickRecord
from omda.ports.errors import SourceUnavailableError
from omda.storage import SqliteHistory


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


def _integrity_ok(path: Path) -> bool:
    """Explicit sqlite integrity check (catches truncation that a connect-only
    open may accept)."""
    try:
        conn = sqlite3.connect(path)
        try:
            row = conn.execute("PRAGMA integrity_check").fetchone()
            return bool(row) and row[0] == "ok"
        finally:
            conn.close()
    except sqlite3.Error:
        return False


def _verify_restored(path: Path) -> None:
    restored = SqliteHistory(path)
    try:
        assert restored.schema_version() == 3
        assert restored.latest_pick_index() == 3
        assert len(restored.excluded_album_identities()) == 9
        receipt = restored.find_delivery_receipt("backup-run:markdown")
        assert receipt is not None and receipt.status == "ok"
        assert receipt.attempt_id == "backup-run:markdown#1"
        op = restored.find_delivery_operation("backup-run:markdown")
        assert op is not None and op.state == "SUCCEEDED"
        tails = [e.transition for e in restored.journal_after("backup-run", 0)]
        assert "HISTORY_COMMITTED" in tails
    finally:
        restored.close()


def main() -> int:
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        live = d / "omda.sqlite3"
        backup = d / "omda.backup.sqlite3"
        damaged = d / "omda.corrupt.sqlite3"

        # 1) Build + STOP the writer (consistent backup requires no active
        #    writer on the live file).
        store = _build_store(live)
        store.close()
        print("[T5.4] writer stopped; store closed")

        # 2) Consistent backup from a fresh read connection.
        src = sqlite3.connect(live)
        dst = sqlite3.connect(backup)
        src.backup(dst)
        dst.close()
        src.close()
        print(f"[T5.4] consistent backup written: {backup} ({backup.stat().st_size} bytes)")

        # 3) The backup itself must open and verify.
        _verify_restored(backup)
        print("[T5.4] backup verified (schema v3, 3 picks, 9 identities, bound receipt)")

        # 4) Corrupt the live store (truncate: simulated disk damage).
        data = live.read_bytes()
        live.write_bytes(data[: len(data) // 2])
        print("[T5.4] live store corrupted (truncated)")

        # 5) The corrupt store MUST be rejected. Undetected corruption = FAIL.
        domain_rejected = False
        try:
            SqliteHistory(live)
        except SourceUnavailableError:
            domain_rejected = True
        integrity_rejected = not _integrity_ok(live)
        if not (domain_rejected or integrity_rejected):
            print("[T5.4] FAIL: corrupted store was NOT rejected "
                  "(domain open succeeded AND integrity_check returned ok)")
            return 1
        print(f"[T5.4] corruption detected (domain_open_rejected={domain_rejected}, "
              f"integrity_rejected={integrity_rejected})")

        # 6) PRESERVE the damaged copy (evidence is never overwritten).
        shutil.copy2(live, damaged)
        print(f"[T5.4] damaged copy preserved: {damaged}")

        # 7) Atomic restore: temp file + rename (no partial-write window).
        tmp = d / "omda.restore.tmp"
        tmp.write_bytes(backup.read_bytes())
        os.replace(tmp, live)  # atomic on POSIX
        print("[T5.4] restored atomically (temp + rename)")

        # 8) Logical integrity verification.
        _verify_restored(live)
        print("[T5.4] restored store verified: schema v3, 3 picks, 9 identities, "
              "bound ok receipt + SUCCEEDED operation, HISTORY_COMMITTED journal")

    print("[T5.4] PASS: backup -> stop-writer -> corrupt -> reject -> preserve -> "
          "atomic restore -> verify")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
