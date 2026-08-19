"""Minimal domain values shared by Port contracts (T1.4).

These are immutable, dependency-free value types that cross the Port boundary.
The Recommendation Core operates on domain values only (SPEC §3.1); G2 may extend
this module with richer domain logic, but the Port-facing shapes stay minimal.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any


@dataclass(frozen=True)
class GenreRef:
    """A genre as seen by the selection layer."""

    genre_id: str
    name: str
    family: str
    eligible: bool = True


@dataclass(frozen=True)
class AlbumIdentity:
    """Canonical identity of an album (SPEC §2.4)."""

    album_id: str
    canonical_id: str | None = None
    canonical_source: str | None = None  # e.g. "musicbrainz" | "none"
    identity_confidence: str = "exact"  # "exact" | "normalized" | "ambiguous"


@dataclass(frozen=True)
class AlbumCandidate:
    """A candidate album offered to the selection layer."""

    album_id: str
    title: str
    artist: str
    year: int | None = None
    genres: tuple[str, ...] = field(default_factory=tuple)
    identity: AlbumIdentity | None = None


@dataclass(frozen=True)
class GenrePickRecord:
    """One official genre pick inside an atomic history commit."""

    pick_index: int
    genre_id: str


@dataclass(frozen=True)
class JournalEntry:
    """One run-journal transition (SPEC §4).

    ``detail`` is exposed as an immutable read-only mapping so callers cannot
    mutate a durable journal snapshot (G1-004).
    """

    journal_id: int
    run_id: str
    transition: str
    at: str
    detail: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        if self.detail is not None and not isinstance(self.detail, MappingProxyType):
            object.__setattr__(self, "detail", MappingProxyType(dict(self.detail)))


@dataclass(frozen=True)
class DeliveryReceipt:
    """Immutable delivery evidence (SPEC §4, G1-002).

    Receipts are authoritative per idempotency key: an exact replay is a no-op and
    a conflicting write fails closed; a success receipt can never be overwritten.
    """

    run_id: str
    idempotency_key: str
    delivered_at: str
    channel: str
    status: str  # "ok" | "failed"
    target: str | None = None


__all__ = [
    "AlbumCandidate",
    "AlbumIdentity",
    "DeliveryReceipt",
    "GenrePickRecord",
    "GenreRef",
    "JournalEntry",
]
