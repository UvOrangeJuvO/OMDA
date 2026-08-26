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


def freeze_json(value: Any) -> Any:
    """Recursively freeze JSON-like values (G1-004).

    dict/mapping -> read-only MappingProxyType (recursively); list/tuple ->
    immutable tuple (recursively); scalars and None pass through unchanged.
    The result cannot be mutated at any nesting level.
    """
    if isinstance(value, Mapping):
        return MappingProxyType({key: freeze_json(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(freeze_json(item) for item in value)
    return value


def thaw_json(value: Any) -> Any:
    """Recursively convert a frozen snapshot back to plain JSON-like types
    (dict/list), suitable for ``json.dumps`` or a writable defensive copy."""
    if isinstance(value, Mapping):
        return {key: thaw_json(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [thaw_json(item) for item in value]
    return value


@dataclass(frozen=True)
class GenreRef:
    """A genre as seen by the selection layer.

    ``parents`` carries the source taxonomy's parent memberships (G2-010) so the
    Orchestrator can enforce configured parent diversity as a set constraint —
    never a popularity signal.
    """

    genre_id: str
    name: str
    family: str
    eligible: bool = True
    parents: tuple[str, ...] = field(default_factory=tuple)


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

    ``detail`` is recursively frozen at construction time (G1-004): nested
    mappings become read-only ``MappingProxyType`` and nested lists become
    tuples, so neither the caller's original object nor later mutation through
    the exposed value can alter the durable snapshot. Use :meth:`snapshot_detail`
    for a writable deep copy with plain dict/list types.
    """

    journal_id: int
    run_id: str
    transition: str
    at: str
    detail: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        if self.detail is not None:
            object.__setattr__(self, "detail", freeze_json(self.detail))

    def snapshot_detail(self) -> dict[str, Any] | None:
        """Return a deep copy of the detail with plain dict/list types.

        Mutating the returned value never affects this entry's frozen snapshot.
        """
        if self.detail is None:
            return None
        return thaw_json(self.detail)


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
    status: str  # "ok" | "failed" | "ambiguous" (ADR-0001 v2)
    target: str | None = None
    attempt_id: str | None = None  # bound immutable attempt (G4-002B)


# Delivery operation states (ADR-0001 v2, §5).
OP_IN_FLIGHT_OR_MAY_HAVE_SENT = "IN_FLIGHT_OR_MAY_HAVE_SENT"
OP_SUCCEEDED = "SUCCEEDED"
OP_CONFIRMED_FAILED = "CONFIRMED_FAILED"
OP_AMBIGUOUS = "AMBIGUOUS"
OP_RESOLVED_DELIVERED = "RESOLVED_DELIVERED"
OP_RESOLVED_NOT_DELIVERED = "RESOLVED_NOT_DELIVERED"

OPERATION_STATES = frozenset(
    {
        OP_IN_FLIGHT_OR_MAY_HAVE_SENT,
        OP_SUCCEEDED,
        OP_CONFIRMED_FAILED,
        OP_AMBIGUOUS,
        OP_RESOLVED_DELIVERED,
        OP_RESOLVED_NOT_DELIVERED,
    }
)

# Human resolution outcomes (ADR-0001 v2, §6).
RESOLUTION_CONFIRMED_DELIVERED = "CONFIRMED_DELIVERED"
RESOLUTION_CONFIRMED_NOT_DELIVERED = "CONFIRMED_NOT_DELIVERED"
RESOLUTION_STILL_UNKNOWN = "STILL_UNKNOWN"

RESOLUTION_OUTCOMES = frozenset(
    {
        RESOLUTION_CONFIRMED_DELIVERED,
        RESOLUTION_CONFIRMED_NOT_DELIVERED,
        RESOLUTION_STILL_UNKNOWN,
    }
)


@dataclass(frozen=True)
class DeliveryOperation:
    """The durable per-key delivery intent (ADR-0001 v2).

    One row per stable idempotency key; created atomically BEFORE any network
    call with a conservative ``IN_FLIGHT_OR_MAY_HAVE_SENT`` state, so every
    existing row blocks every other automatic caller (at-most-one outbound
    request per operation). ``version`` is the compare-and-swap counter used by
    ``finalize_delivery_attempt`` / ``record_delivery_resolution``.
    """

    idempotency_key: str
    run_id: str
    channel: str
    payload_digest: str
    state: str
    version: int
    created_at: str


@dataclass(frozen=True)
class DeliveryOperationSnapshot:
    """Result of ``begin_delivery_operation``.

    ``created=True`` means this caller won the atomic claim and may proceed to
    the external call; ``created=False`` returns the authoritative existing
    operation (the caller must follow the state table and NOT call the
    transport again).
    """

    created: bool
    operation: DeliveryOperation


@dataclass(frozen=True)
class DeliveryAttempt:
    """Append-only, immutable record of ONE outbound attempt (ADR-0001 v2)."""

    attempt_id: str
    operation_key: str
    outcome: str  # "ok" | "failed" | "ambiguous"
    evidence: str
    attempted_at: str


@dataclass(frozen=True)
class DeliveryResolution:
    """Append-only human/operator decision bound to an operation (ADR-0001 v2).

    ``outcome`` is one of ``RESOLUTION_*``. A ``STILL_UNKNOWN`` entry does not
    change the operation state (remains blocked); the other two advance the
    operation only from IN_FLIGHT_OR_MAY_HAVE_SENT / AMBIGUOUS (§15-4).
    """

    operation_key: str
    run_id: str
    idempotency_key: str
    attempt_id: str | None
    outcome: str
    actor: str
    reason: str
    decided_at: str


__all__ = [
    "AlbumCandidate",
    "AlbumIdentity",
    "DeliveryAttempt",
    "DeliveryOperation",
    "DeliveryOperationSnapshot",
    "DeliveryReceipt",
    "DeliveryResolution",
    "GenrePickRecord",
    "GenreRef",
    "JournalEntry",
    "OP_AMBIGUOUS",
    "OP_CONFIRMED_FAILED",
    "OP_IN_FLIGHT_OR_MAY_HAVE_SENT",
    "OP_RESOLVED_DELIVERED",
    "OP_RESOLVED_NOT_DELIVERED",
    "OP_SUCCEEDED",
    "OPERATION_STATES",
    "RESOLUTION_CONFIRMED_DELIVERED",
    "RESOLUTION_CONFIRMED_NOT_DELIVERED",
    "RESOLUTION_OUTCOMES",
    "RESOLUTION_STILL_UNKNOWN",
    "freeze_json",
    "thaw_json",
]
