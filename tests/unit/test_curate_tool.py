"""G3-007-008: the MBID curation tool requires an owner-supplied, contactable,
non-placeholder User-Agent and supports an injectable transport (no network)."""

from __future__ import annotations

import json

import pytest
import tools.curate_mbids as tool


class _FakeResponse:
    def __init__(self, body: bytes) -> None:
        self._body = body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self) -> bytes:
        return self._body


class _FakeTransport:
    def __init__(self) -> None:
        self.headers: list[dict] = []

    def __call__(self, request, timeout):
        self.headers.append(dict(request.header_items()))
        body = json.dumps(
            {
                "release-groups": [
                    {
                        "id": "00000000-0000-0000-0000-000000000001",
                        "title": "Some Album",
                        "artist-credit": [{"name": "Some Artist"}],
                        "first-release-date": "2000",
                        "primary-type": "Album",
                        "score": 100,
                    }
                ]
            }
        ).encode("utf-8")
        return _FakeResponse(body)


def test_user_agent_missing_or_placeholder_is_rejected() -> None:
    # G3-007-008: a missing value, a non-contactable shape and placeholder
    # markers (including .invalid) must all be rejected.
    with pytest.raises(ValueError):
        tool._validate_user_agent(None)
    with pytest.raises(ValueError):
        tool._validate_user_agent("")
    with pytest.raises(ValueError):
        tool._validate_user_agent("just-a-string")
    with pytest.raises(ValueError):
        tool._validate_user_agent("OMDA-curation/0.1 (mailto:omda-curation@example.invalid)")
    with pytest.raises(ValueError):
        tool._validate_user_agent("OMDA-curation/0.1 (mailto:owner@example.com)")
    with pytest.raises(ValueError):
        tool._validate_user_agent("OMDA-curation/0.1 (https://example.org/contact)")


def test_user_agent_owner_supplied_value_is_accepted() -> None:
    value = "OMDA-curation/0.1 (mailto:owner@example.invalid)"
    assert tool._validate_user_agent(value) == value


def test_fetch_uses_owner_user_agent_via_injected_transport() -> None:
    # No network: an injected transport records the exact User-Agent header and
    # returns a canned response.
    transport = _FakeTransport()
    data = tool._fetch(
        "Some Album", "Some Artist", "OMDA-curation/0.1 (mailto:owner@example.invalid)",
        transport=transport,
    )
    assert data["release-groups"][0]["id"] == "00000000-0000-0000-0000-000000000001"
    assert transport.headers  # one request was made
    ua = dict(transport.headers[0]).get("User-agent") or dict(transport.headers[0]).get(
        "User-Agent"
    )
    assert ua == "OMDA-curation/0.1 (mailto:owner@example.invalid)"
