"""HistoryPort — runtime state for journal, official history and delivery receipts.

Decision (G0-007 follow-up, recorded in the G1 Executor Report): run-journal
operations are part of this single Port rather than a separate `RunJournalPort`.
Journal and official history share one SQLite runtime store and transaction
boundary (T1.5); crash-recovery contract tests need to verify journal state and
history writes atomically within one abstraction. A separate Port would add
surface area with no independent consumer yet.

Official Genre/Album history is written ONLY after validated delivery succeeds
(SPEC §4). These records are protected user state — never disposable.
"""

from __future__ import annotations

from typing import Protocol

from omda.ports.domain import AlbumIdentity, DeliveryReceipt, JournalEntry


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

    # --- official genre pick history (cooldown source) ---
    def latest_pick_index(self) -> int:
        """Highest committed global pick index (0 when no history exists)."""
        ...

    def record_genre_pick(
        self, run_id: str, genre_id: str, pick_index: int, committed_at: str
    ) -> None:
        """Commit one genre pick at the given global index (cooldown advances)."""
        ...

    def cooldown_pick_indices(self, genre_id: str) -> list[int]:
        """All committed pick indices for a genre (for cooldown computation)."""
        ...

    # --- official album history (permanent exclusion) ---
    def record_album(self, run_id: str, identity: AlbumIdentity, recommended_at: str) -> None:
        """Permanently exclude an album from future selection (SPEC §2.4)."""
        ...

    def excluded_album_identities(self) -> set[AlbumIdentity]:
        """All permanently excluded album identities (immutable input to Core)."""
        ...

    # --- delivery receipts (idempotency) ---
    def save_delivery_receipt(self, receipt: DeliveryReceipt) -> None:
        """Persist a delivery receipt keyed by idempotency_key."""
        ...

    def find_delivery_receipt(self, idempotency_key: str) -> DeliveryReceipt | None:
        """Return the stored receipt for an idempotency key, if any."""
        ...
