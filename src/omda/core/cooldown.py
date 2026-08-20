"""Pick-index cooldown engine (T2.2).

Cooldown is measured in successfully committed Genre picks, never in days or
run counts (SPEC §2.2). A Genre committed at global pick index ``p`` is
ineligible for indices ``p+1..p+30`` and MAY become eligible at ``p+31``.
Failed or abandoned runs never consume official pick indices — this engine only
ever sees the committed history passed in by the Orchestrator.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from omda.ports.domain import GenreRef

DEFAULT_COOLDOWN_PICKS = 30


def is_available(
    genre_pick_indices: Sequence[int],
    next_pick_index: int,
    cooldown_picks: int = DEFAULT_COOLDOWN_PICKS,
) -> bool:
    """Whether a Genre with the given committed pick indices may be picked at
    ``next_pick_index``.

    ``next_pick_index`` is the global index the next pick would receive.
    ``p + cooldown_picks < next_pick_index`` (i.e. p+31 for cooldown 30) restores
    eligibility.
    """
    if not genre_pick_indices:
        return True
    latest = max(genre_pick_indices)
    return (next_pick_index - latest) > cooldown_picks


def filter_available(
    genres: Sequence[GenreRef],
    pick_history: Mapping[str, Sequence[int]],
    next_pick_index: int,
    cooldown_picks: int = DEFAULT_COOLDOWN_PICKS,
) -> list[GenreRef]:
    """Return genres not in cooldown at ``next_pick_index``.

    ``pick_history`` maps genre_id to its committed pick indices (immutable
    input; never mutated here).
    """
    return [
        genre
        for genre in genres
        if is_available(pick_history.get(genre.genre_id, ()), next_pick_index, cooldown_picks)
    ]


__all__ = ["DEFAULT_COOLDOWN_PICKS", "filter_available", "is_available"]
