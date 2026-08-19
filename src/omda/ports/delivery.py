"""Delivery Port — idempotent delivery of the final recommendation payload."""

from __future__ import annotations

from typing import Protocol

from omda.ports.domain import DeliveryReceipt


class Delivery(Protocol):
    """Output channel adapter (Markdown file, PushPlus, ...)."""

    def deliver(
        self,
        payload: str,
        idempotency_key: str,
        target: str | None = None,
    ) -> DeliveryReceipt:
        """Deliver a payload with a stable idempotency key derived from the run id.

        Must not cause a second external push for a replay of the same key
        (SPEC §4). Returns a receipt with status "ok" or "failed".
        """
        ...
