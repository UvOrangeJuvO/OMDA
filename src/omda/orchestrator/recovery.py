"""delivered-but-not-committed recovery decision layer (G4 T4.4).

SPEC §4 / MP §6: after an external push succeeds but the local history commit
fails, the run enters RECOVERING. Recovery MUST resolve from DURABLE evidence —
the run journal and the immutable delivery receipt keyed by the run's stable
idempotency key — NEVER from conversation memory, and MUST NOT blind re-deliver
(a second external push for the same key is forbidden).

Compensating / idempotency protocol (no cross-system absolute atomicity):
- the external push and local SQLite commit are separate systems; OMDA never
  claims atomicity across them (SPEC §4). The protocol is: push first with a
  stable idempotency key, persist the receipt, then commit local history;
- if the receipt is persisted with status "ok" but history is uncommitted, the
  run is delivered-but-not-committed and the ONLY safe action is to commit the
  local history (no re-push);
- if evidence is missing, failed or does not bind to this run/key/channel, the
  outcome is ambiguous: require human review, never guess, never re-push.

This module is a pure decision layer over the existing HistoryPort — it does not
modify the accepted run state machine.
"""

from __future__ import annotations

from dataclasses import dataclass

from omda.ports.domain import DeliveryReceipt
from omda.ports.history import HistoryPort

# Recovery actions (decisions, not new transitions).
COMMIT_HISTORY = "COMMIT_HISTORY"
COMPLETE_ALREADY = "COMPLETE_ALREADY"
REQUIRE_HUMAN = "REQUIRE_HUMAN"

_AFTER_DELIVER_TRANSITIONS = frozenset({"DELIVERING", "DELIVERED", "RECOVERING"})


@dataclass(frozen=True)
class RecoveryDecision:
    """One recovery decision derived from durable evidence."""

    action: str
    reason: str
    receipt: DeliveryReceipt | None = None
    journal_tail: str | None = None


def resolve_recovery_action(
    history: HistoryPort, run_id: str, *, idempotency_key: str | None = None
) -> RecoveryDecision:
    """Decide the recovery action for ``run_id`` from durable evidence only.

    Order of checks:
    1. terminal tail (COMPLETE / HISTORY_COMMITTED) -> already complete;
    2. a bound, "ok" receipt for the run's idempotency key -> delivered; commit
       local history (delivered-but-not-committed) and NEVER re-deliver;
    3. anything else (missing/failed/unbound evidence, or a tail before
       delivery) -> REQUIRE_HUMAN; no guess, no re-push.
    """
    entries = history.journal_after(run_id, 0)
    tail = entries[-1].transition if entries else None

    if tail in ("COMPLETE", "HISTORY_COMMITTED"):
        return RecoveryDecision(
            action=COMPLETE_ALREADY, reason="run already completed", journal_tail=tail
        )

    key = idempotency_key or f"{run_id}:markdown"
    receipt = history.find_delivery_receipt(key)
    if receipt is not None and receipt.status == "ok" and receipt.run_id == run_id:
        return RecoveryDecision(
            action=COMMIT_HISTORY,
            reason="delivered-but-not-committed",
            receipt=receipt,
            journal_tail=tail,
        )
    return RecoveryDecision(
        action=REQUIRE_HUMAN,
        reason="delivery evidence missing or mismatched; no blind re-delivery",
        receipt=receipt,
        journal_tail=tail,
    )


__all__ = [
    "COMMIT_HISTORY",
    "COMPLETE_ALREADY",
    "REQUIRE_HUMAN",
    "RecoveryDecision",
    "resolve_recovery_action",
]
