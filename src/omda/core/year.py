"""Year constraints and per-genre album selection (T2.5).

- default 3 Albums per Genre;
- at least one Album with ``year >= modern_year`` when suitable candidates exist;
- at most two older Albums in the normal case;
- missing modern candidates or unknown years NEVER force an unrelated/invalid
  Album in; candidate shortage yields a bounded ``InsufficientCandidatesError``
  (the Orchestrator may observe/degrade);
- year selection is decoupled from rating composition: ``select_albums_for_genre``
  consumes an already-ranked candidate list.
"""

from __future__ import annotations

from collections.abc import Sequence

from omda.ports.domain import AlbumCandidate
from omda.ports.errors import InsufficientCandidatesError

DEFAULT_ALBUMS_PER_GENRE = 3
DEFAULT_MODERN_YEAR = 2010
DEFAULT_MAX_OLDER = 2


def is_modern(candidate: AlbumCandidate, modern_year: int = DEFAULT_MODERN_YEAR) -> bool:
    """year >= modern_year; unknown year is never considered modern."""
    return candidate.year is not None and candidate.year >= modern_year


def select_albums_for_genre(
    ranked: Sequence[AlbumCandidate],
    count: int = DEFAULT_ALBUMS_PER_GENRE,
    modern_year: int = DEFAULT_MODERN_YEAR,
    max_older: int = DEFAULT_MAX_OLDER,
) -> list[AlbumCandidate]:
    """Select ``count`` albums honouring the modern/older constraint.

    ``ranked`` is the score-ordered candidate list (deterministic; produced by
    the rating module or a stable order). Behaviour:
    - fewer candidates than ``count`` -> ``InsufficientCandidatesError``;
    - modern candidates exist -> at least one modern, at most ``max_older`` older;
    - no modern candidates -> bounded degradation: return the top ``count``
      (caller records the degradation; nothing unrelated is ever forced in).
    """
    if len(ranked) < count:
        raise InsufficientCandidatesError(
            f"need {count} album candidates, only {len(ranked)} available"
        )
    modern = [c for c in ranked if is_modern(c, modern_year)]
    if not modern:
        # No modern candidates: explicit degradation path (observable, tested).
        return list(ranked[:count])

    chosen: list[AlbumCandidate] = [modern[0]]
    older_picked = 0
    for candidate in ranked:
        if len(chosen) >= count:
            break
        if candidate.album_id == modern[0].album_id:
            continue
        if is_modern(candidate, modern_year):
            chosen.append(candidate)
        else:
            if older_picked >= max_older:
                continue
            older_picked += 1
            chosen.append(candidate)
    # Candidate shortage of suitable era: fill with remaining candidates only if
    # we still fall short (bounded; never unrelated, they come from this genre).
    for candidate in ranked:
        if len(chosen) >= count:
            break
        if candidate.album_id not in {c.album_id for c in chosen}:
            chosen.append(candidate)
    return chosen[:count]


__all__ = [
    "DEFAULT_ALBUMS_PER_GENRE",
    "DEFAULT_MAX_OLDER",
    "DEFAULT_MODERN_YEAR",
    "is_modern",
    "select_albums_for_genre",
]
