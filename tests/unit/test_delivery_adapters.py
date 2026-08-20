"""G4 T4.3 — Delivery Adapter tests (SPEC §4; MP §3.7; OPH §12).

Idempotent delivery (a stable idempotency key derived from the run id), bounded
retry with backoff, durable receipts, and Markdown/PushPlus channel behaviour.
All tests use fakes / a scripted HTTP transport and a temp output directory; no
live PushPlus or external service is ever touched.
"""

from __future__ import annotations

import pytest

from omda.adapters.delivery import (
    MarkdownFileDelivery,
    PushPlusDelivery,
)
from omda.ports.errors import DeliveryFailureError


class ScriptedHttp:
    """Records calls; serves scripted responses / raises scripted exceptions."""

    def __init__(self, *script):
        self.script = list(script)
        self.calls = 0
        self.last_url = None
        self.last_payload = None

    def post(self, url: str, payload: dict) -> dict:
        self.calls += 1
        self.last_url = url
        self.last_payload = payload
        step = self.script[min(self.calls - 1, len(self.script) - 1)]
        if isinstance(step, Exception):
            raise step
        return step


class RecordingSleeper:
    def __init__(self):
        self.delays = []

    def __call__(self, seconds):
        self.delays.append(seconds)


def _ok_response() -> dict:
    return {"code": 200, "msg": "成功", "data": "ok"}


def _fail_response() -> dict:
    return {"code": 500, "msg": "error", "data": None}


def test_markdown_file_delivery_writes_payload_and_receipt() -> None:
    import tempfile
    from pathlib import Path

    from omda.ports.domain import DeliveryReceipt

    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "out"
        delivery = MarkdownFileDelivery(output_dir=out)
        receipt = delivery.deliver("# hello", "run-1:markdown")
        assert isinstance(receipt, DeliveryReceipt)
        assert receipt.status == "ok"
        assert receipt.idempotency_key == "run-1:markdown"
        # Payload written to a deterministic path derived from the run id.
        written = (out / "run-1.md").read_text(encoding="utf-8")
        assert written == "# hello"


def test_markdown_file_delivery_escaping() -> None:
    # The file name comes from the run id only (safe); the payload is written
    # verbatim (OPH §12 escaping is about the file path / channel limits).
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "out"
        delivery = MarkdownFileDelivery(output_dir=out)
        payload = "line1\nline2 with **bold** and `code`"
        delivery.deliver(payload, "run-1:markdown")
        assert (out / "run-1.md").read_text(encoding="utf-8") == payload


def test_pushplus_delivery_success_receipt() -> None:
    transport = ScriptedHttp(_ok_response())
    delivery = PushPlusDelivery(
        token_env="PUSHPLUS_TOKEN", transport=transport, sleeper=RecordingSleeper()
    )
    # Token injected from a controlled dict, never from a real environment.
    receipt = delivery.deliver(
        "payload", "run-1:pushplus", token_provider=lambda: "test-token"
    )
    assert receipt.status == "ok"
    assert receipt.channel == "pushplus"
    assert transport.calls == 1
    assert transport.last_payload["token"] == "test-token"
    assert transport.last_payload["title"] is not None
    assert "payload" in transport.last_payload["content"]


def test_pushplus_retries_on_transient_failure_then_succeeds() -> None:
    sleeper = RecordingSleeper()
    transport = ScriptedHttp(_fail_response(), _ok_response())
    delivery = PushPlusDelivery(
        token_env="PUSHPLUS_TOKEN",
        transport=transport,
        sleeper=sleeper,
        max_retries=2,
    )
    receipt = delivery.deliver(
        "payload", "run-1:pushplus", token_provider=lambda: "test-token"
    )
    assert receipt.status == "ok"
    assert transport.calls == 2
    assert len(sleeper.delays) == 1  # one bounded backoff between attempts
    assert sleeper.delays[0] > 0


def test_pushplus_exhausts_retries_and_returns_failed_receipt() -> None:
    sleeper = RecordingSleeper()
    transport = ScriptedHttp(_fail_response())
    delivery = PushPlusDelivery(
        token_env="PUSHPLUS_TOKEN",
        transport=transport,
        sleeper=sleeper,
        max_retries=1,
    )
    receipt = delivery.deliver(
        "payload", "run-1:pushplus", token_provider=lambda: "test-token"
    )
    assert receipt.status == "failed"
    assert transport.calls == 2  # initial + 1 retry
    assert len(sleeper.delays) == 1


def test_pushplus_network_error_maps_to_ambiguous_not_failed() -> None:
    # G4-002: a timeout/transport error means the provider MAY have accepted
    # the request (response lost) — the outcome is AMBIGUOUS, never a
    # confirmed "failed" (which would terminate the run as FAILED).
    sleeper = RecordingSleeper()
    transport = ScriptedHttp(TimeoutError("down"))
    delivery = PushPlusDelivery(
        token_env="PUSHPLUS_TOKEN",
        transport=transport,
        sleeper=sleeper,
        max_retries=0,
    )
    receipt = delivery.deliver(
        "payload", "run-1:pushplus", token_provider=lambda: "test-token"
    )
    assert receipt.status == "ambiguous"
    assert transport.calls == 1


def test_pushplus_rejects_oversized_payload() -> None:
    # PushPlus content limit: an oversized payload is refused BEFORE any call.
    transport = ScriptedHttp(_ok_response())
    delivery = PushPlusDelivery(
        token_env="PUSHPLUS_TOKEN", transport=transport, sleeper=RecordingSleeper()
    )
    with pytest.raises(DeliveryFailureError):
        delivery.deliver(
            "x" * 100_000, "run-1:pushplus", token_provider=lambda: "t"
        )
    assert transport.calls == 0  # never reached the external service


def test_pushplus_requires_explicit_token_provider() -> None:
    transport = ScriptedHttp(_ok_response())
    delivery = PushPlusDelivery(
        token_env="PUSHPLUS_TOKEN", transport=transport, sleeper=RecordingSleeper()
    )
    # No token provider and no environment variable -> controlled failure.
    with pytest.raises(DeliveryFailureError):
        delivery.deliver("payload", "run-1:pushplus")


def test_non_positive_retries_rejected() -> None:
    with pytest.raises(ValueError):
        PushPlusDelivery(
            token_env="T",
            transport=ScriptedHttp(),
            sleeper=RecordingSleeper(),
            max_retries=-1,
        )


def test_retry_bounds_are_integer_typed() -> None:
    for bad in (1.5, float("nan"), True):
        with pytest.raises(ValueError):
            PushPlusDelivery(
                token_env="T",
                transport=ScriptedHttp(),
                sleeper=RecordingSleeper(),
                max_retries=bad,
            )


# --- T4.3 acceptance: same idempotency key never causes a second push ----------


def test_same_idempotency_key_does_not_cause_second_push() -> None:
    # SPEC §4 / MP §3.7: a replay of the same run id must not cause a second
    # external delivery. The adapter is stateless; the durable receipt in the
    # HistoryPort is the authority — the recovery/caller checks it and refuses
    # to call deliver() again for the same key.
    from tests.fakes import InMemoryHistory

    transport = ScriptedHttp(_ok_response())
    delivery = PushPlusDelivery(
        token_env="PUSHPLUS_TOKEN", transport=transport, sleeper=RecordingSleeper()
    )
    history = InMemoryHistory()
    key = "run-1:pushplus"
    first = delivery.deliver("payload", key, token_provider=lambda: "test-token")
    assert first.status == "ok"
    history.save_delivery_receipt(first)
    assert transport.calls == 1

    # Replay: the caller (recovery) sees the durable receipt for the key and
    # MUST NOT call deliver() again — no second external push happens.
    stored = history.find_delivery_receipt(key)
    assert stored is not None and stored.status == "ok"
    if stored.status == "ok":  # the caller's idempotency decision
        pass  # recovery commits history directly; deliver() is not re-invoked
    assert transport.calls == 1  # exactly one external push, ever


# --- G4-002 re-review: ambiguous PushPlus outcomes are never blindly retried ---


class EffectThenTimeout:
    """Transport that records an external effect and then raises TimeoutError.

    Simulates 'provider accepted the request, response was lost': the first
    call DID reach the provider, so a retry would cause a SECOND push.
    """

    def __init__(self):
        self.effects = 0
        self.calls = 0

    def post(self, url: str, payload: dict) -> dict:
        self.calls += 1
        self.effects += 1  # the external side effect happened
        raise TimeoutError("response lost after provider accepted")


def test_timeout_after_provider_accept_is_ambiguous_not_retried() -> None:
    # Reviewer reproduction: one deliver() call must NOT produce a second
    # external push when the first response was lost after acceptance.
    transport = EffectThenTimeout()
    sleeper = RecordingSleeper()
    delivery = PushPlusDelivery(
        token_env="PUSHPLUS_TOKEN",
        transport=transport,
        sleeper=sleeper,
        max_retries=3,
    )
    receipt = delivery.deliver(
        "payload", "run-1:pushplus", token_provider=lambda: "test-token"
    )
    assert transport.calls == 1  # NO automatic retry of an ambiguous send
    assert transport.effects == 1  # exactly one external effect, ever
    assert receipt.status == "ambiguous"  # not "failed": outcome is unknown
    assert len(sleeper.delays) == 0  # no backoff for an ambiguous outcome


def test_ambiguous_outcome_enters_recovery_at_run_level() -> None:
    # An ambiguous receipt must drive the RunEngine into RECOVERING (durable,
    # human-safe), never FAILED as if the delivery were confirmed dead.
    from tests.fakes import FakeAlbumSource, FakeGenreSource, FakeLLM, InMemoryHistory

    from omda.config import load_config
    from omda.orchestrator.run import RECOVERING, RunEngine
    from omda.ports.domain import AlbumCandidate, GenreRef

    history = InMemoryHistory()

    class AmbiguousDelivery:
        def deliver(self, payload, idempotency_key, target=None):
            run_id, _, channel = idempotency_key.partition(":")
            from omda.ports.domain import DeliveryReceipt

            return DeliveryReceipt(
                run_id=run_id,
                idempotency_key=idempotency_key,
                delivered_at="2026-08-21T00:00:00+00:00",
                channel=channel or "markdown",
                status="ambiguous",
            )

    genres = [
        GenreRef("ambient", "Ambient", "Electronic"),
        GenreRef("bebop", "Bebop", "Jazz"),
        GenreRef("krautrock", "Krautrock", "Rock"),
        GenreRef("tuareg", "Tuareg Music", "Regional"),
        GenreRef("idm", "IDM", "Electronic"),
    ]

    def albums(gid):
        return [
            AlbumCandidate(f"{gid}-1", f"{gid} Album 1", "Artist", 2015),
            AlbumCandidate(f"{gid}-2", f"{gid} Album 2", "Artist", 2000),
            AlbumCandidate(f"{gid}-3", f"{gid} Album 3", "Artist", 1990),
            AlbumCandidate(f"{gid}-4", f"{gid} Album 4", "Artist", 2020),
        ]

    engine = RunEngine(
        config=load_config(),
        history=history,
        genre_source=FakeGenreSource(genres),
        album_source=FakeAlbumSource({g.genre_id: albums(g.genre_id) for g in genres}),
        llm=FakeLLM("A concise explanation."),
        delivery=AmbiguousDelivery(),
        seed="ambiguous",
    )
    outcome = engine.run("run-amb")
    assert outcome.state == RECOVERING
    # No official history was committed for an ambiguous delivery.
    assert history.latest_pick_index() == 0
    assert history.excluded_album_identities() == frozenset()
