"""Delivery Port — idempotent delivery of the final recommendation payload."""

from __future__ import annotations

from typing import Protocol

from omda.ports.domain import DeliveryReceipt


class Delivery(Protocol):
    """Output channel adapter (Markdown file, PushPlus, ...).

    ADR-0001 (Accepted): the Orchestrator drives the atomic pre-network claim
    protocol around this Port — ``begin_delivery_operation`` (HistoryPort) is
    persisted BEFORE ``deliver`` is called, so a replay/concurrent caller can
    never produce a second external push. This adapter is invoked at most once
    per operation and reports the outcome as a receipt.
    """

    def deliver(
        self,
        payload: str,
        idempotency_key: str,
        target: str | None = None,
    ) -> DeliveryReceipt:
        """Deliver a payload with a stable idempotency key derived from the run id.

        Returns a receipt whose ``status`` is one of the three ADR-0001 classes:
        ``"ok"`` (definitively delivered), ``"failed"`` (definitively rejected
        by a documented no-side-effect category) or ``"ambiguous"`` (outcome
        unknown — 5xx, timeout, lost response, undocumented codes; NEVER
        automatically retried).
        """
        ...
