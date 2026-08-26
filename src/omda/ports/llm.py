"""LLM Port — bounded narrative generation from a validated fact packet.

The LLM MUST NOT decide the official Genre or Album set (SPEC §3.5); it only
explains. All vendor SDKs live behind this Port's implementations (G4).
"""

from __future__ import annotations

from typing import Any, Protocol


class LLM(Protocol):
    def generate_narrative(
        self,
        fact_packet: dict[str, Any],
        *,
        expected_genres: int | None = None,
        expected_albums: int | None = None,
    ) -> str:
        """Return narrative text for a bounded, validated fact packet.

        External/web content embedded in the packet is untrusted data; it must
        never act as an instruction override (SPEC §3.5). The optional
        expected cardinality pins the real plan shape (G4-006).
        """
        ...
