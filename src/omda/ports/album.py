"""AlbumSource / Enricher Ports — candidate retrieval and on-demand enrichment."""

from __future__ import annotations

from typing import Protocol

from omda.ports.domain import AlbumCandidate, GenreRef


class AlbumSource(Protocol):
    """Source of candidate albums for a genre."""

    def candidates_for_genre(
        self, genre: GenreRef, limit: int | None = None
    ) -> list[AlbumCandidate]:
        """Return candidate albums for a genre; bounded, cacheable, never unbounded."""
        ...


class AlbumEnricher(Protocol):
    """On-demand enrichment of album facts (e.g. canonical identity)."""

    def enrich(self, candidate: AlbumCandidate) -> AlbumCandidate:
        """Return an enriched copy of the candidate (canonical identity, year, ...)."""
        ...
