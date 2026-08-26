"""Delivery Adapters — Markdown file and PushPlus (G4 T4.3; ADR-0001 v2).

Implements the EXISTING ``Delivery`` Port with a stable idempotency key derived
from the run id, bounded retry/backoff, and durable receipts (SPEC §4; MP §3.7).
The Orchestrator drives the ADR-0001 protocol around the adapter: an atomic
``begin_delivery_operation`` claim is persisted BEFORE the transport is called,
so a replay/concurrent caller can never produce a second external push.

PushPlus specifics (ADR-0001 §9): the transport returns a TYPED result so the
adapter can distinguish definitive provider rejection from delivery ambiguity:

- ``ProviderSuccess`` -> ok;
- ``ProviderRejection`` (definitive, documented: the request was NOT accepted)
  -> confirmed failure, TERMINAL for this operation (no retry loop);
- ``NoBytesSentError`` (proven zero request bytes were written) -> the ONLY
  class allowed a bounded automatic retry; exhaustion is a confirmed failure;
- anything else (5xx, parse failure, timeout, connection reset, lost response,
  unknown business codes) -> ``AmbiguousFailure`` / generic exception ->
  ``ambiguous`` receipt with NO retry.

The token is injected via an explicit ``token_provider`` callable (or the named
environment variable), never hard-coded or logged; payload length is bounded
BEFORE any external call.
"""

from __future__ import annotations

import time as _time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
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


@dataclass(frozen=True)
class ProviderSuccess:
    """A definitively successful provider response (payload parsed)."""

    body: Mapping


class ProviderRejection(Exception):
    """DEFINITIVE rejection: the provider did NOT accept/queue the request.

    Only documented categories (e.g. authentication / parameter rejection that
    provably produced no side effect) may raise this — it is terminal for the
    operation, never an automatic retry loop (ADR-0001 §9).
    """

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"provider definitive rejection {code}: {message}")
        self.code = code
        self.message = message


class NoBytesSentError(Exception):
    """Proven: ZERO request bytes were written to the wire.

    Raised only when the concrete transport can prove no bytes left the
    process (e.g. DNS failure or connection-establishment failure before the
    first write). This is the ONLY class that may be automatically retried,
    with a bounded count (ADR-0001 §15-3).
    """


class AmbiguousFailure(Exception):
    """The provider outcome is UNKNOWN (5xx, parse failure, timeout, reset,
    lost response, undocumented business code). NEVER automatically retried;
    the outcome may already have produced a push (ADR-0001 §9)."""


class HttpTransport(Protocol):
    """Injectable typed HTTP boundary for PushPlus (no socket/HTTP imports here).

    ``post`` returns ``ProviderSuccess`` or raises one of:
    ``ProviderRejection`` (definitive), ``NoBytesSentError`` (zero bytes,
    retryable) or ``AmbiguousFailure``/other exceptions (ambiguous).
    """

    def post(self, url: str, payload: dict) -> ProviderSuccess:
        """POST a JSON payload; provider outcomes are classified by the caller."""
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
        # ADR-0001 §9: ONLY NoBytesSentError (proven zero bytes written) may be
        # retried, with a bounded count. Everything else is either terminal
        # (ProviderRejection) or ambiguous (no retry) — a lost/unknown response
        # may already have produced a push.
        for attempt in range(self._max_retries + 1):
            try:
                result = self._transport.post(self._api_url, body)
            except NoBytesSentError:
                # Proven: no request bytes left this process. Safe to retry; a
                # bounded exhaustion is a CONFIRMED failure (never sent).
                if attempt < self._max_retries:
                    self._backoff(attempt)
                    continue
                return DeliveryReceipt(
                    run_id=run_id,
                    idempotency_key=idempotency_key,
                    delivered_at=self._clock(),
                    channel=channel,
                    status="failed",
                    target=self._api_url,
                )
            except ProviderRejection as exc:
                # Definitive rejection (documented): NOT accepted -> terminal,
                # never an automatic retry loop (ADR-0001 §9 / §15-3).
                return DeliveryReceipt(
                    run_id=run_id,
                    idempotency_key=idempotency_key,
                    delivered_at=self._clock(),
                    channel=channel,
                    status="failed",
                    target=f"{self._api_url} [{exc.code}] {exc.message}",
                )
            except AmbiguousFailure as exc:
                # 5xx / parse failure / timeout / reset / lost response /
                # undocumented business code: the outcome is UNKNOWN and the
                # provider MAY have queued the push -> ambiguous, no retry.
                return DeliveryReceipt(
                    run_id=run_id,
                    idempotency_key=idempotency_key,
                    delivered_at=self._clock(),
                    channel=channel,
                    status="ambiguous",
                    target=str(exc),
                )
            except Exception as exc:
                # Any unclassified transport exception is treated as ambiguous
                # (no proof the request was not accepted), never blindly retried.
                return DeliveryReceipt(
                    run_id=run_id,
                    idempotency_key=idempotency_key,
                    delivered_at=self._clock(),
                    channel=channel,
                    status="ambiguous",
                    target=str(exc),
                )
            if not isinstance(result, ProviderSuccess):
                # An unclassified (e.g. raw dict) response is NOT proof of
                # success -> ambiguous, no retry (ADR-0001 §9).
                return DeliveryReceipt(
                    run_id=run_id,
                    idempotency_key=idempotency_key,
                    delivered_at=self._clock(),
                    channel=channel,
                    status="ambiguous",
                    target=repr(result),
                )
            return DeliveryReceipt(
                run_id=run_id,
                idempotency_key=idempotency_key,
                delivered_at=self._clock(),
                channel=channel,
                status="ok",
                target=self._api_url,
            )
        # Unreachable: the NoBytesSent exhaustion branch returns inside the loop.
        raise DeliveryFailureError("unreachable pushplus delivery state")

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


__all__ = [
    "AmbiguousFailure",
    "DEFAULT_MAX_RETRIES",
    "DEFAULT_MAX_BACKOFF",
    "DEFAULT_BASE_DELAY",
    "MarkdownFileDelivery",
    "MAX_PUSHPLUS_CONTENT",
    "NoBytesSentError",
    "PUSHPLUS_API_URL",
    "ProviderRejection",
    "ProviderSuccess",
    "PushPlusDelivery",
]
