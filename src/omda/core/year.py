"""Year constraints and per-genre album selection (T2.5; repaired G2-004).

- default 3 Albums per Genre;
- at least one Album with ``year >= modern_year`` when suitable candidates exist;
- at most two older Albums in the normal case;
- missing modern candidates or unknown years NEVER force an unrelated/invalid
  Album in; candidate shortage yields a bounded ``InsufficientCandidatesError``;

G2-004 repairs:
- selection returns a structured ``AlbumSelectionResult`` carrying the selected
  Albums PLUS constraint/fallback status, reason and counts, so operators and
  the journal can distinguish a compliant plan from a degradation;
- the final fill never silently exceeds ``max_older``; an unsatisfiable cap for
  a configured count yields an explicit ``fallback_insufficient_era`` result
  (never a silent cap bypass).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from omda.ports.domain import AlbumCandidate
from omda.ports.errors import InsufficientCandidatesError

DEFAULT_ALBUMS_PER_GENRE = 3
DEFAULT_MODERN_YEAR = 2010
DEFAULT_MAX_OLDER = 2

STATUS_NORMAL = "normal"
STATUS_FALLBACK_NO_MODERN = "fallback_no_modern"
STATUS_FALLBACK_INSUFFICIENT_ERA = "fallback_insufficient_era"


@dataclass(frozen=True)
class AlbumSelectionResult:
    """Observable outcome of the year-constrained selection (G2-004)."""

    albums: tuple[AlbumCandidate, ...]
    status: str
    reason: str
    modern_count: int
    older_count: int
    unknown_year_count: int
    candidates_considered: int


def is_modern(candidate: AlbumCandidate, modern_year: int = DEFAULT_MODERN_YEAR) -> bool:
    """year >= modern_year; unknown year is never considered modern."""
    return candidate.year is not None and candidate.year >= modern_year


def select_albums_for_genre(
    ranked: Sequence[AlbumCandidate],
    count: int = DEFAULT_ALBUMS_PER_GENRE,
    modern_year: int = DEFAULT_MODERN_YEAR,
    max_older: int = DEFAULT_MAX_OLDER,
) -> AlbumSelectionResult:
    """Select ``count`` albums honouring the modern/older constraint.

    ``ranked`` is the score-ordered candidate list (deterministic). Outcomes:
    - fewer candidates than ``count`` -> ``InsufficientCandidatesError``;
    - modern candidates exist and constraints fit -> ``status="normal"``;
    - no modern candidates -> ``status="fallback_no_modern"`` (top ``count``,
      observable degradation, nothing unrelated forced in);
    - the older cap cannot fill ``count`` even though enough candidates exist
      -> ``status="fallback_insufficient_era"`` with the cap-respecting subset
      (never a silent cap bypass; reason records the shortfall).
    """
    ranked_list = list(ranked)
    if len(ranked_list) < count:
        raise InsufficientCandidatesError(
            f"need {count} album candidates, only {len(ranked_list)} available"
        )
    modern = [c for c in ranked_list if is_modern(c, modern_year)]
    older = [c for c in ranked_list if not is_modern(c, modern_year)]
    unknown = [c for c in ranked_list if c.year is None]
    considered = len(ranked_list)

    if not modern:
        # Explicit degradation: no modern candidates.
        return AlbumSelectionResult(
            albums=tuple(ranked_list[:count]),
            status=STATUS_FALLBACK_NO_MODERN,
            reason="no album with year >= modern_year available",
            modern_count=0,
            older_count=len(older[:count]),
            unknown_year_count=len(unknown),
            candidates_considered=considered,
        )

    chosen: list[AlbumCandidate] = [modern[0]]
    older_picked = 0
    for candidate in ranked_list:
        if len(chosen) >= count:
            break
        if candidate.album_id == modern[0].album_id:
            continue
        if is_modern(candidate, modern_year):
            chosen.append(candidate)
        elif older_picked < max_older:
            older_picked += 1
            chosen.append(candidate)
        # else: older cap reached -> skip (never silently exceed)

    if len(chosen) < count:
        # The cap (or modern availability) cannot fill the configured count:
        # explicit observable degradation — never fill past the older cap.
        return AlbumSelectionResult(
            albums=tuple(chosen),
            status=STATUS_FALLBACK_INSUFFICIENT_ERA,
            reason=(
                f"only {len(chosen)} albums fit era constraints "
                f"(need {count}, max_older={max_older}, modern={len(modern)})"
            ),
            modern_count=sum(1 for c in chosen if is_modern(c, modern_year)),
            older_count=sum(1 for c in chosen if not is_modern(c, modern_year)),
            unknown_year_count=len(unknown),
            candidates_considered=considered,
        )

    return AlbumSelectionResult(
        albums=tuple(chosen[:count]),
        status=STATUS_NORMAL,
        reason="",
        modern_count=sum(1 for c in chosen if is_modern(c, modern_year)),
        older_count=sum(1 for c in chosen if not is_modern(c, modern_year)),
        unknown_year_count=len(unknown),
        candidates_considered=considered,
    )


__all__ = [
    "STATUS_FALLBACK_INSUFFICIENT_ERA",
    "STATUS_FALLBACK_NO_MODERN",
    "STATUS_NORMAL",
    "AlbumSelectionResult",
    "DEFAULT_ALBUMS_PER_GENRE",
    "DEFAULT_MAX_OLDER",
    "DEFAULT_MODERN_YEAR",
    "is_modern",
    "select_albums_for_genre",
]
