"""Application Port contracts (interfaces only, no implementations).

Dependency direction (G0-006): Orchestrator depends on both the pure Core and
these Port contracts; Adapters implement these Ports; Core never calls them.
"""

from omda.ports.album import AlbumEnricher, AlbumSource
from omda.ports.critic import CriticRatingRow, CriticRatingSource
from omda.ports.delivery import Delivery
from omda.ports.domain import (
    AlbumCandidate,
    AlbumIdentity,
    DeliveryReceipt,
    GenreRef,
    JournalEntry,
)
from omda.ports.errors import (
    DeliveryFailureError,
    DomainError,
    GenerationFailureError,
    InsufficientCandidatesError,
    InvalidInputError,
    InvariantFailureError,
    SourceUnavailableError,
    StateCommitFailureError,
    ValidationFailureError,
)
from omda.ports.genre import GenreSource
from omda.ports.history import HistoryPort
from omda.ports.llm import LLM

__all__ = [
    "AlbumCandidate",
    "AlbumEnricher",
    "AlbumIdentity",
    "AlbumSource",
    "CriticRatingRow",
    "CriticRatingSource",
    "Delivery",
    "DeliveryFailureError",
    "DeliveryReceipt",
    "DomainError",
    "GenerationFailureError",
    "GenreRef",
    "GenreSource",
    "HistoryPort",
    "InsufficientCandidatesError",
    "InvalidInputError",
    "InvariantFailureError",
    "JournalEntry",
    "LLM",
    "SourceUnavailableError",
    "StateCommitFailureError",
    "ValidationFailureError",
]
