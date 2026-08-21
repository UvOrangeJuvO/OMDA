"""G4-007 — production Agent/PushPlus composition tests.

The production composition shape (RunEngine wired to real sources, PushPlus
delivery with a replaceable transport, token boundary, controlled failures and
official-history ordering) is exercised with fake transports — no live HTTP,
no live LLM, no PushPlus token in the repository.
"""

from __future__ import annotations

import io
import os
import urllib.error
from dataclasses import replace

import pytest
from tests.fakes import FakeAlbumSource, FakeGenreSource, InMemoryHistory

from omda.adapters.delivery import (
    AmbiguousFailure,
    NoBytesSentError,
    ProviderRejection,
    ProviderSuccess,
)
from omda.config import Config, DeliveryConfig, load_config
from omda.orchestrator.run import COMPLETE, RECOVERING, RunEngine
from omda.ports.domain import AlbumCandidate, GenreRef
from omda.production import PushPlusHttpTransport, build_production_engine


class FakeLLMTransport:
    def complete(self, system: str, user: str) -> str:
        return "A concise explanation."


class ScriptedPushPlusTransport:
    def __init__(self, *script):
        self.script = list(script)
        self.calls = 0
        self.last_payload = None

    def post(self, url: str, payload: dict) -> ProviderSuccess:
        self.calls += 1
        self.last_payload = payload
        step = self.script[min(self.calls - 1, len(self.script) - 1)]
        if isinstance(step, Exception):
            raise step
        return step


class NoSleep:
    def __call__(self, seconds):
        pass


@pytest.fixture(autouse=True)
def _pushplus_token_env():
    os.environ["PUSHPLUS_TOKEN"] = "test-token"
    yield
    os.environ.pop("PUSHPLUS_TOKEN", None)


def _genres() -> list[GenreRef]:
    return [
        GenreRef("ambient", "Ambient", "Electronic"),
        GenreRef("bebop", "Bebop", "Jazz"),
        GenreRef("krautrock", "Krautrock", "Rock"),
        GenreRef("tuareg", "Tuareg Music", "Regional"),
        GenreRef("idm", "IDM", "Electronic"),
    ]


def _albums(gid: str) -> list[AlbumCandidate]:
    return [
        AlbumCandidate(f"{gid}-1", f"{gid} Album 1", "Artist", 2015),
        AlbumCandidate(f"{gid}-2", f"{gid} Album 2", "Artist", 2000),
        AlbumCandidate(f"{gid}-3", f"{gid} Album 3", "Artist", 1990),
        AlbumCandidate(f"{gid}-4", f"{gid} Album 4", "Artist", 2020),
    ]


def _config(channel: str = "pushplus") -> Config:
    return replace(
        load_config(),
        delivery=DeliveryConfig(channel=channel, pushplus_token_env="PUSHPLUS_TOKEN"),
    )


def _engine(transport, history=None, channel="pushplus"):
    return build_production_engine(
        config=_config(channel),
        history=history or InMemoryHistory(),
        genre_source=FakeGenreSource(_genres()),
        album_source=FakeAlbumSource({g.genre_id: _albums(g.genre_id) for g in _genres()}),
        llm_transport=FakeLLMTransport(),
        transport=transport,
        seed="production",
    )


def test_build_production_engine_returns_real_runengine_with_pushplus_delivery() -> None:
    engine = _engine(ScriptedPushPlusTransport(ProviderSuccess({"code": 200})))
    assert isinstance(engine, RunEngine)
    assert engine._config.delivery.channel == "pushplus"
    assert engine._delivery is not None


def test_build_production_engine_rejects_non_pushplus_channel() -> None:
    from omda.ports.errors import DeliveryFailureError

    with pytest.raises(DeliveryFailureError):
        _engine(ScriptedPushPlusTransport(ProviderSuccess({"code": 200})), channel="markdown")


def test_production_run_success_commits_history_in_order() -> None:
    # Official-history ordering: the external push (one call, ok) happens
    # BEFORE the local history commit; the run completes.
    history = InMemoryHistory()
    transport = ScriptedPushPlusTransport(ProviderSuccess({"code": 200}))
    outcome = _engine(transport, history).run("run-pp")
    assert outcome.state == COMPLETE
    assert transport.calls == 1
    assert transport.last_payload["token"] == "test-token"
    assert history.latest_pick_index() == 3


def test_production_ambiguous_outcome_enters_recovery_no_history() -> None:
    history = InMemoryHistory()
    transport = ScriptedPushPlusTransport(AmbiguousFailure("timeout"))
    outcome = _engine(transport, history).run("run-amb")
    assert outcome.state == RECOVERING
    assert transport.calls == 1  # never blindly retried
    assert history.latest_pick_index() == 0


def test_production_zero_bytes_then_success_retries_once() -> None:
    history = InMemoryHistory()
    transport = ScriptedPushPlusTransport(
        NoBytesSentError("dns"), ProviderSuccess({"code": 200})
    )
    outcome = _engine(transport, history).run("run-pp")
    assert outcome.state == COMPLETE
    assert transport.calls == 2


def test_production_definitive_rejection_is_terminal_no_retry_loop() -> None:
    history = InMemoryHistory()
    transport = ScriptedPushPlusTransport(ProviderRejection("401", "unauthorized"))
    outcome = _engine(transport, history).run("run-pp")
    from omda.orchestrator.run import FAILED

    assert outcome.state == FAILED
    assert transport.calls == 1  # terminal, never a retry loop
    assert history.latest_pick_index() == 0


# --- PushPlusHttpTransport classification (injected urlopen) -------------------


class FakeResponse:
    def __init__(self, status: int, body: bytes) -> None:
        self.status = status
        self._body = body

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _transport_with(urlopen):
    return PushPlusHttpTransport(urlopen=urlopen)


def _urlopen_returning(status: int, body: bytes):
    def urlopen(request, timeout):
        if status >= 400:
            raise urllib.error.HTTPError(
                request.full_url, status, "err", {}, io.BytesIO(body)
            )
        return FakeResponse(status, body)
    return urlopen


def test_http_transport_classifies_200_success() -> None:
    transport = _transport_with(
        _urlopen_returning(200, b'{"code":200,"msg":"ok"}')
    )
    result = transport.post("https://x/send", {"a": 1})
    assert isinstance(result, ProviderSuccess)


def test_http_transport_classifies_401_as_ambiguous() -> None:
    # G4-002A: no documented PushPlus contract proves a 401 produced no side
    # effect, so even authentication failures are AMBIGUOUS (no retry).
    transport = _transport_with(_urlopen_returning(401, b"unauthorized"))
    with pytest.raises(AmbiguousFailure):
        transport.post("https://x/send", {"a": 1})


def test_http_transport_classifies_500_ambiguous() -> None:

    transport = _transport_with(_urlopen_returning(500, b"boom"))
    with pytest.raises(AmbiguousFailure):
        transport.post("https://x/send", {"a": 1})


def test_http_transport_classifies_dns_failure_zero_bytes() -> None:
    import socket
    import urllib.error

    def urlopen(request, timeout):
        raise urllib.error.URLError(socket.gaierror("name resolution failed"))

    with pytest.raises(NoBytesSentError):
        _transport_with(urlopen).post("https://x/send", {"a": 1})


def test_http_transport_classifies_timeout_ambiguous() -> None:
    import urllib.error

    def urlopen(request, timeout):
        raise urllib.error.URLError(TimeoutError("timed out"))

    with pytest.raises(AmbiguousFailure):
        _transport_with(urlopen).post("https://x/send", {"a": 1})


def test_http_transport_classifies_malformed_body_ambiguous() -> None:
    transport = _transport_with(_urlopen_returning(200, b"not-json"))
    with pytest.raises(AmbiguousFailure):
        transport.post("https://x/send", {"a": 1})


def test_http_transport_classifies_undocumented_business_code_ambiguous() -> None:
    transport = _transport_with(_urlopen_returning(200, b'{"code":999,"msg":"?"}'))
    with pytest.raises(AmbiguousFailure):
        transport.post("https://x/send", {"a": 1})


# --- G4-002A re-review 3: unknown HTTP 4xx is AMBIGUOUS, not definitive ---------


def test_http_transport_unknown_418_is_ambiguous() -> None:
    # Reviewer reproduction: an undocumented HTTP 418 must be AMBIGUOUS (the
    # provider may have queued the message) — never a confirmed failure.
    transport = _transport_with(_urlopen_returning(418, b"teapot"))
    with pytest.raises(AmbiguousFailure):
        transport.post("https://x/send", {"a": 1})


def test_http_transport_unknown_499_is_ambiguous() -> None:
    transport = _transport_with(_urlopen_returning(499, b"client closed"))
    with pytest.raises(AmbiguousFailure):
        transport.post("https://x/send", {"a": 1})


def test_http_transport_no_definitive_4xx_category_without_documented_contract() -> None:
    # ADR-0001 §9/§15-3: without a documented provider contract proving no
    # side effect, NO 4xx category may be treated as definitive. The concrete
    # transport therefore produces NO ProviderRejection for the whole 4xx range.
    for status in (400, 401, 403, 404, 418, 422, 429, 499):
        transport = _transport_with(_urlopen_returning(status, b"err"))
        with pytest.raises(AmbiguousFailure):
            transport.post("https://x/send", {"a": 1})
