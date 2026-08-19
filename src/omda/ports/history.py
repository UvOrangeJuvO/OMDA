"""HistoryPort — runtime state for journal, official history and delivery receipts.

Decision (G0-007 follow-up, recorded in the G1 Executor Report): run-journal
operations are part of this single Port rather than a separate `RunJournalPort`.
Journal and official history share one SQLite runtime store and transaction
boundary (T1.5); crash-recovery contract tests need to verify journal state and
history writes atomically within one abstraction.

Official Genre/Album history is written ONLY through ``commit_history`` — a single
all-or-nothing unit of work (G1-001). A failed run must leave official pick
history, album exclusions and the journal exactly unchanged. These records are
protected user state — never disposable.

Delivery receipts are immutable per idempotency key (G1-002): an exact replay is
a no-op returning the original record; a conflicting write fails closed and must
never alter the original success evidence.
"""

from __future__ import annotations

from typing import Protocol

from omda.ports.domain import (
    AlbumIdentity,
    DeliveryReceipt,
    GenrePickRecord,
    JournalEntry,
)


class HistoryPort(Protocol):
    """Persistent runtime state: journal, official history, delivery receipts."""

    # --- run journal (append-friendly) ---
    def append_journal(
        self,
        run_id: str,
        transition: str,
        at: str,
        detail: dict | None = None,
    ) -> JournalEntry:
        """Append one transition and return the stored entry with its journal_id."""
        ...

    def journal_after(self, run_id: str, after_journal_id: int) -> list[JournalEntry]:
        """Return journal entries for a run with journal_id > after_journal_id."""
        ...

    # --- official history reads (cooldown / exclusion inputs to Core) ---
    def latest_pick_index(self) -> int:
        """Highest committed global pick index (0 when no history exists)."""
        ...

    def cooldown_pick_indices(self, genre_id: str) -> list[int]:
        """All committed pick indices for a genre (for cooldown computation)."""
        ...

    def excluded_album_identities(self) -> frozenset[AlbumIdentity]:
        """All permanently excluded album identities (immutable input to Core)."""
        ...

    # --- ATOMIC official history commit (G1-001: the ONLY write path) ---
    def commit_history(
        self,
        run_id: str,
        genre_picks: list[GenrePickRecord],
        album_identities: list[AlbumIdentity],
        committed_at: str,
    ) -> None:
        """Commit the complete official 3x3 history in one local transaction.

        Writes ALL genre picks, ALL album histories and a ``HISTORY_COMMITTED``
        journal entry atomically. Any failure leaves all three areas unchanged.
        Individual per-row writes are NOT a normal commit path (G1-001).
        """
        ...

    # --- delivery receipts (immutable idempotency evidence, G1-002) ---
    def save_delivery_receipt(self, receipt: DeliveryReceipt) -> DeliveryReceipt:
        """Store a receipt; returns the authoritative record.

        - absent key: store and return the new record;
        - exact replay (identical fields): no-op, return the stored record;
        - conflicting write for an existing key: fail closed, original unchanged.
        """
        ...

    def find_delivery_receipt(self, idempotency_key: str) -> DeliveryReceipt | None:
        """Return the stored receipt for an idempotency key, if any."""
        ...
