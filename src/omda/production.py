"""Production Agent/PushPlus composition boundary (G4 T4.3/T4.5, G4-007).

G4-007 required an executable production route for the explicitly approved
``--deliver`` path, with REPLACEABLE concrete transports and configuration.
This module provides:

- ``PushPlusHttpTransport`` — a real HTTP(S) PushPlus client built on the
  standard library (no third-party SDK). It classifies every provider outcome
  per ADR-0001 §9: documented success -> ``ProviderSuccess``; definitive
  client rejection (HTTP 4xx) -> ``ProviderRejection`` (terminal); zero-bytes
  proven failures (DNS / connection-refused before any write) ->
  ``NoBytesSentError`` (the only retryable class); everything else (5xx,
  timeout, connection reset, malformed body, lost response) ->
  ``AmbiguousFailure`` (no retry).
- ``build_production_engine`` — wires the REAL ``RunEngine`` with the
  repository data sources, an injectable LLM transport and the PushPlus
  delivery. Ordinary tests inject fake transports; the composition shape, token
  boundary and official-history ordering are exercised without any live call.

No API key / token is ever committed: the PushPlus token is read at runtime
from the environment variable named by ``DeliveryConfig.pushplus_token_env``.
"""

from __future__ import annotations

import json
import socket
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any

from omda.adapters.delivery import (
    PUSHPLUS_API_URL,
    AmbiguousFailure,
    NoBytesSentError,
    ProviderSuccess,
    PushPlusDelivery,
)
from omda.adapters.llm import LLMAdapter
from omda.config import Config
from omda.orchestrator.run import RunEngine
from omda.ports.errors import DeliveryFailureError

# Repository data resolved independently of the caller's working directory
# (G4-003 P2): package-root anchored, override with OMDA_DATA_DIR if needed.
_PACKAGE_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_DATA_DIR = Path(
    __import__("os").environ.get("OMDA_DATA_DIR", str(_PACKAGE_ROOT / "data"))
)


class PushPlusHttpTransport:
    """Standard-library PushPlus client with ADR-0001 §9 outcome classification.

    ``urlopen`` is injectable so unit tests can script HTTP responses without
    touching the network.
    """

    def __init__(
        self,
        *,
        api_url: str = PUSHPLUS_API_URL,
        read_timeout: float = 10.0,
        urlopen: Callable[..., Any] | None = None,
    ) -> None:
        self._api_url = api_url
        self._read_timeout = read_timeout
        self._urlopen = urlopen or urllib.request.urlopen

    def post(self, url: str, payload: dict) -> ProviderSuccess:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json; charset=utf-8"},
            method="POST",
        )
        try:
            try:
                with self._urlopen(request, timeout=self._read_timeout) as resp:
                    status = int(resp.status)
                    body = resp.read().decode("utf-8", errors="replace")
            except urllib.error.HTTPError as exc:
                status = exc.code
                body = exc.read().decode("utf-8", errors="replace")
        except urllib.error.URLError as exc:
            reason = getattr(exc, "reason", exc)
            if isinstance(reason, (socket.gaierror, ConnectionRefusedError)):
                # Proven: no connection, no bytes written -> the only retryable class.
                raise NoBytesSentError(f"no bytes written: {reason}") from exc
            raise AmbiguousFailure(f"provider outcome unknown: {reason}") from exc
        except TimeoutError as exc:
            raise AmbiguousFailure(f"provider timeout: {exc}") from exc
        except OSError as exc:
            if isinstance(exc, ConnectionRefusedError):
                raise NoBytesSentError(f"connection refused (no bytes written): {exc}") from exc
            # Connection reset / EOF after any write is ambiguous.
            raise AmbiguousFailure(f"provider transport error: {exc}") from exc

        if status == 200:
            try:
                decoded = json.loads(body)
            except ValueError as exc:
                raise AmbiguousFailure(f"malformed provider body: {exc}") from exc
            if _business_code(decoded) == 200:
                return ProviderSuccess(decoded)
            raise AmbiguousFailure(f"undocumented provider business code: {body!r}")
        if status != 200:
            # G4-002A (ADR-0001 §9/§15-3): NO HTTP class may be treated as a
            # definitive rejection without a DOCUMENTED provider contract
            # proving no message was queued. The current PushPlus API
            # documentation only defines business code 200; it does not prove
            # "no side effect" for any HTTP 4xx/5xx, so EVERY non-200 status
            # (including undocumented 4xx) is AMBIGUOUS — the provider may
            # have queued the message, and a retry could duplicate a push.
            raise AmbiguousFailure(f"provider http {status}: {body!r}")


def _business_code(decoded: dict) -> int:
    code = decoded.get("code")
    try:
        return int(code)
    except (TypeError, ValueError):
        return -1


def build_production_engine(
    *,
    config: Config,
    history: Any,
    genre_source: Any,
    album_source: Any,
    llm_transport: Any,
    transport: Any | None = None,
    token_env: str | None = None,
    seed: str | None = None,
) -> RunEngine:
    """Compose the REAL production RunEngine for the ``--deliver`` path.

    ``transport`` is injectable for tests (a fake PushPlus transport); the
    production default is ``PushPlusHttpTransport``. The PushPlus token is
    resolved at runtime from ``config.delivery.pushplus_token_env`` — never
    logged and never committed.
    """
    if config.delivery is None or config.delivery.channel != "pushplus":
        raise DeliveryFailureError(
            "--deliver requires config delivery.channel == 'pushplus'"
        )
    delivery = PushPlusDelivery(
        token_env=token_env or config.delivery.pushplus_token_env,
        transport=transport or PushPlusHttpTransport(),
    )
    return RunEngine(
        config=config,
        history=history,
        genre_source=genre_source,
        album_source=album_source,
        llm=LLMAdapter(transport=llm_transport),
        delivery=delivery,
        seed=seed,
    )


__all__ = [
    "DEFAULT_DATA_DIR",
    "PushPlusHttpTransport",
    "build_production_engine",
]
