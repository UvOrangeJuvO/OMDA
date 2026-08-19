"""CriticRatingSource Port — source-specific rating rows (SPEC §2.6)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from omda.ports.domain import AlbumCandidate


@dataclass(frozen=True)
class CriticRatingRow:
    source_id: str
    album_id: str
    rating: float
    rating_max: float | None = None
    review_url: str | None = None


class CriticRatingSource(Protocol):
    """A critic source's ratings. Dimensions stay source-specific; weights and
    missing-value policy are configuration, never Core constants (SPEC §2.6)."""

    def ratings_for(self, album: AlbumCandidate) -> list[CriticRatingRow]:
        """Return all rating rows this source holds for the album (possibly empty)."""
        ...
