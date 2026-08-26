"""AlbumSource / Enricher Ports — candidate retrieval and on-demand enrichment."""

from __future__ import annotations

from typing import Protocol

from omda.ports.domain import AlbumCandidate, GenreRef
from omda.ports.source import CandidateBatch


class AlbumSource(Protocol):
    """Source of candidate albums for a genre.

    ``candidates_for_genre`` returns domain candidate values for selection.
    ``source_batch`` is the provider-neutral SOURCE-ENVELOPE contract
    (ADR-0002 §8.4, G3-007-004): it returns the versioned, digest-bound
    :class:`CandidateBatch` for a Genre so the trusted application boundary can
    assemble and validate a :class:`ValidatedSourceSet` AFTER FETCH and BEFORE
    selection/delivery claim, without importing any concrete adapter.
    """

    def candidates_for_genre(
        self, genre: GenreRef, limit: int | None = None
    ) -> list[AlbumCandidate]:
        """Return candidate albums for a genre; bounded, cacheable, never unbounded."""
        ...

    def source_batch(self, genre: GenreRef) -> CandidateBatch:
        """Return the versioned, digest-bound batch envelope for a Genre."""
        ...


class AlbumEnricher(Protocol):
    """On-demand enrichment of album facts (e.g. canonical identity)."""

    def enrich(self, candidate: AlbumCandidate) -> AlbumCandidate:
        """Return an enriched copy of the candidate (canonical identity, year, ...)."""
        ...
