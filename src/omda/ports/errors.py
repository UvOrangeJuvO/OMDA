"""Domain error taxonomy (SPEC §8, T1.4).

Adapters must translate provider-specific failures into these domain errors; the
Recommendation Core and Orchestrator only ever see this taxonomy. No provider
details may leak through.
"""

from __future__ import annotations

from typing import Any


class DomainError(Exception):
    """Base class for all domain-level errors."""

    def __init__(self, message: str, *, detail: Any = None) -> None:
        super().__init__(message)
        self.message = message
        self.detail = detail


class InvalidInputError(DomainError):
    """Input data is malformed or violates a schema/constraint."""


class SourceUnavailableError(DomainError):
    """An external or local source is unavailable (network, session, storage)."""


class InsufficientCandidatesError(DomainError):
    """Not enough eligible candidates to satisfy the constraints."""


class InvariantFailureError(DomainError):
    """A product invariant was violated; the system must fail closed."""


class GenerationFailureError(DomainError):
    """Narrative generation (LLM) failed or produced unusable output."""


class ValidationFailureError(DomainError):
    """Generated output failed validation (structure/length/facts)."""


class DeliveryFailureError(DomainError):
    """Delivery to the output channel failed."""


class StateCommitFailureError(DomainError):
    """Writing official history/journal to local state failed."""


__all__ = [
    "DeliveryFailureError",
    "DomainError",
    "GenerationFailureError",
    "InsufficientCandidatesError",
    "InvalidInputError",
    "InvariantFailureError",
    "SourceUnavailableError",
    "StateCommitFailureError",
    "ValidationFailureError",
]
