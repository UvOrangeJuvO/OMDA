"""Multi-source rating composition with deterministic ranking (T2.5).

Rating dimensions stay source-specific; weights and the missing-value policy
are configuration/input, never hard-coded Core constants (SPEC §2.6). Adding a
critic source requires no Core modification. Ranking ties are resolved
deterministically (stable key, no set/dict iteration order).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from omda.ports.critic import CriticRatingRow
from omda.ports.domain import AlbumCandidate

# Missing-value policies: "skip" ignores sources without a rating; "zero" treats
# a missing source rating as 0.0 within its weight.
MISSING_SKIP = "skip"
MISSING_ZERO = "zero"


def _normalized(row: CriticRatingRow) -> float:
    if row.rating_max:
        return float(row.rating) / float(row.rating_max)
    return float(row.rating)


def compose_rating(
    rows: Sequence[CriticRatingRow],
    weights: Mapping[str, float],
    missing_policy: str = MISSING_SKIP,
) -> float | None:
    """Weighted mean of an album's ratings across critic sources.

    Returns ``None`` when no weighted rating is available (all weights zero or
    no rows under ``skip``).
    """
    if missing_policy not in (MISSING_SKIP, MISSING_ZERO):
        raise ValueError(f"unknown missing_policy {missing_policy!r}")
    by_source: dict[str, CriticRatingRow] = {}
    for row in rows:
        by_source.setdefault(row.source_id, row)

    total_weight = 0.0
    acc = 0.0
    for source_id, weight in weights.items():
        if weight <= 0:
            continue
        row = by_source.get(source_id)
        if row is None:
            if missing_policy == MISSING_ZERO:
                acc += weight * 0.0
                total_weight += weight
            continue
        acc += weight * _normalized(row)
        total_weight += weight
    if total_weight <= 0:
        return None
    return acc / total_weight


def rank_candidates(
    candidates: Sequence[AlbumCandidate],
    rating_rows: Mapping[str, Sequence[CriticRatingRow]],
    weights: Mapping[str, float],
    missing_policy: str = MISSING_SKIP,
) -> list[AlbumCandidate]:
    """Return candidates sorted by composed rating (desc), with deterministic
    tie-breaking by normalized title then album_id. Unrated albums sort last."""
    scored: list[tuple[float | None, AlbumCandidate]] = []
    for candidate in candidates:
        rows = rating_rows.get(candidate.album_id, ())
        score = compose_rating(rows, weights, missing_policy)
        scored.append((score, candidate))

    def sort_key(item: tuple[float | None, AlbumCandidate]) -> tuple:
        score, candidate = item
        return (
            -(score if score is not None else float("-inf")),
            candidate.title.lower(),
            candidate.album_id,
        )

    return [candidate for _, candidate in sorted(scored, key=sort_key)]


__all__ = ["MISSING_SKIP", "MISSING_ZERO", "compose_rating", "rank_candidates"]
