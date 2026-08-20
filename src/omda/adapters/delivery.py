"""Delivery Adapters — Markdown file and PushPlus (G4 T4.3).

Implements the EXISTING ``Delivery`` Port with a stable idempotency key derived
from the run id, bounded retry/backoff, and durable receipts (SPEC §4; MP §3.7).
Idempotency: an adapter that delivers a payload for a key that was already
delivered MUST NOT cause a second external side effect — the caller (Orchestrator
/ recovery) holds the durable receipt and decides; these adapters additionally
never silently re-send on ambiguous evidence.

PushPlus specifics (OPH §12): the token is injected via an explicit
``token_provider`` callable (or the named environment variable), never
hard-coded or logged; payload length is bounded BEFORE any external call;
transient failures are retried with bounded exponential backoff; exhaustion
returns a ``failed`` receipt instead of raising (so the Orchestrator can journal
it), while payload/config errors raise ``DeliveryFailureError``.
"""

from __future__ import annotations

import time as _time
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from omda.ports.domain import DeliveryReceipt
from omda.ports.errors import DeliveryFailureError

PUSHPLUS_API_URL = "https://www.pushplus.plus/send"
DEFAULT_MAX_RETRIES = 3
DEFAULT_BASE_DELAY = 1.0
DEFAULT_MAX_BACKOFF = 30.0
MAX_PUSHPLUS_CONTENT = 5000  # OPH §12: PushPlus content length bound


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


class HttpTransport(Protocol):
    """Injectable HTTP boundary for PushPlus (no socket/HTTP imports here)."""

    def post(self, url: str, payload: dict) -> dict:
        """POST a JSON payload; provider exceptions are classified by callers."""
        ...


class MarkdownFileDelivery:
    """``Delivery`` that writes the payload to a local Markdown file.

    The file name is derived ONLY from the run id (``<run_id>.md``) so a hostile
    payload can never escape the output directory; the payload itself is written
    verbatim. Safe for the default dry-run channel: local disk, no network.
    """

    def __init__(self, *, output_dir: Path | str, clock: Callable[[], str] = _utc_now) -> None:
        self._output_dir = Path(output_dir)
        self._clock = clock

    def deliver(
        self,
        payload: str,
        idempotency_key: str,
        target: str | None = None,
    ) -> DeliveryReceipt:
        run_id, _, channel = idempotency_key.partition(":")
        channel = channel or "markdown"
        # The run id is the only file-name input; sanitize to a plain token.
        safe_run = "".join(c for c in run_id if c.isalnum() or c in "-_")
        if not safe_run:
            raise DeliveryFailureError("cannot derive a safe file name from the idempotency key")
        path = self._output_dir / f"{safe_run}.md"
        try:
            self._output_dir.mkdir(parents=True, exist_ok=True)
            path.write_text(payload, encoding="utf-8")
        except OSError as exc:
            raise DeliveryFailureError(f"markdown write failed: {exc}") from exc
        return DeliveryReceipt(
            run_id=run_id,
            idempotency_key=idempotency_key,
            delivered_at=self._clock(),
            channel=channel,
            status="ok",
            target=str(path),
        )


class PushPlusDelivery:
    """``Delivery`` over the PushPlus send API with bounded retry/backoff.

    The token is resolved per call from ``token_provider`` (a callable) or the
    environment variable named by ``token_env``; it is never logged. Retries are
    bounded and respect idempotency: a confirmed failure returns a ``failed``
    receipt (never a blind second send by the caller), and an oversized payload
    is rejected before any external call.
    """

    def __init__(
        self,
        *,
        token_env: str,
        transport: HttpTransport,
        sleeper: Callable[[float], None] = _time.sleep,
        max_retries: int = DEFAULT_MAX_RETRIES,
        base_delay: float = DEFAULT_BASE_DELAY,
        max_backoff: float = DEFAULT_MAX_BACKOFF,
        api_url: str = PUSHPLUS_API_URL,
        title_prefix: str = "OMDA 每日音乐发现",
        clock: Callable[[], str] = _utc_now,
    ) -> None:
        if (
            not isinstance(max_retries, int)
            or isinstance(max_retries, bool)
            or max_retries < 0
        ):
            raise ValueError(
                f"max_retries must be a non-negative integer, got {max_retries!r}"
            )
        for name, value in (("base_delay", base_delay), ("max_backoff", max_backoff)):
            if not isinstance(value, (int, float)) or isinstance(value, bool) or value <= 0:
                raise ValueError(f"{name} must be a positive number, got {value!r}")
        self._token_env = token_env
        self._transport = transport
        self._sleeper = sleeper
        self._max_retries = max_retries
        self._base_delay = base_delay
        self._max_backoff = max_backoff
        self._api_url = api_url
        self._title_prefix = title_prefix
        self._clock = clock

    def deliver(
        self,
        payload: str,
        idempotency_key: str,
        target: str | None = None,
        *,
        token_provider: Callable[[], str] | None = None,
    ) -> DeliveryReceipt:
        run_id, _, channel = idempotency_key.partition(":")
        channel = channel or "pushplus"
        if not isinstance(payload, str) or not payload.strip():
            raise DeliveryFailureError("pushplus payload is empty")
        if len(payload) > MAX_PUSHPLUS_CONTENT:
            raise DeliveryFailureError(
                f"pushplus payload exceeds {MAX_PUSHPLUS_CONTENT} characters"
            )
        token = self._resolve_token(token_provider)
        title = f"{self._title_prefix} · {run_id}"
        body = {"token": token, "title": title, "content": payload, "template": "markdown"}
        for attempt in range(self._max_retries + 1):
            try:
                response = self._transport.post(self._api_url, body)
            except Exception:  # network / transport-level failure -> backoff/retry
                if attempt < self._max_retries:
                    self._backoff(attempt)
                continue
            if _is_success_response(response):
                return DeliveryReceipt(
                    run_id=run_id,
                    idempotency_key=idempotency_key,
                    delivered_at=self._clock(),
                    channel=channel,
                    status="ok",
                    target=self._api_url,
                )
            if attempt < self._max_retries:
                self._backoff(attempt)
        # Exhausted: confirmed failure -> failed receipt (no raise; journaled).
        return DeliveryReceipt(
            run_id=run_id,
            idempotency_key=idempotency_key,
            delivered_at=self._clock(),
            channel=channel,
            status="failed",
            target=self._api_url,
        )

    def _resolve_token(self, token_provider: Callable[[], str] | None) -> str:
        if token_provider is not None:
            token = token_provider()
        else:
            import os

            token = os.environ.get(self._token_env, "")
        if not isinstance(token, str) or not token.strip():
            raise DeliveryFailureError(
                f"pushplus token missing: set {self._token_env} or provide a token_provider"
            )
        return token

    def _backoff(self, attempt: int) -> None:
        delay = min(self._base_delay * (2**attempt), self._max_backoff)
        self._sleeper(delay)


def _is_success_response(response: Mapping) -> bool:
    """PushPlus returns ``code == 200`` on success (string or int)."""
    try:
        code = response.get("code")
    except AttributeError:
        return False
    if isinstance(code, str):
        return code.strip() == "200"
    return code == 200


__all__ = [
    "DEFAULT_MAX_RETRIES",
    "DEFAULT_MAX_BACKOFF",
    "DEFAULT_BASE_DELAY",
    "MarkdownFileDelivery",
    "MAX_PUSHPLUS_CONTENT",
    "PUSHPLUS_API_URL",
    "PushPlusDelivery",
]
