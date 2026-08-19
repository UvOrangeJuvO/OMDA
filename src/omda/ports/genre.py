"""GenreSource Port — provides eligible genres as domain values."""

from __future__ import annotations

from typing import Protocol

from omda.ports.domain import GenreRef


class GenreSource(Protocol):
    """Source of genre records (community text data, never a popularity ranking)."""

    def list_eligible_genres(self) -> list[GenreRef]:
        """Return all valid, eligible genres. `eligible` reflects data validity
        (SPEC §2.1), never popularity or perceived quality."""
        ...
