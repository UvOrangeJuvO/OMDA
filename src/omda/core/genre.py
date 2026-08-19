"""Genre equal-opportunity selection (T2.1) and the daily Genre planner.

Equal opportunity (SPEC §2.1): every valid, eligible Genre outside cooldown has
equal base selection opportunity. No popularity, follower/rating count,
accessibility, LLM judgment or tier probability ever enters this module — the
only inputs are eligibility, cooldown history, family limits, the requested
count and an injectable randomness source.

Determinism (SPEC §6): candidates are stable-sorted by genre_id before
sampling, and the same input + configuration + seed reproduces the same result.
"""

from __future__ import annotations

import random
from collections.abc import Mapping, Sequence

from omda.core.cooldown import DEFAULT_COOLDOWN_PICKS, filter_available
from omda.core.diversity import DEFAULT_FAMILY_LIMITS, family_ok
from omda.ports.domain import GenreRef
from omda.ports.errors import InsufficientCandidatesError

MAX_SAMPLING_ATTEMPTS = 200


def sort_genres(genres: Sequence[GenreRef]) -> list[GenreRef]:
    """Stable canonical ordering by genre_id (iteration-order independent)."""
    return sorted(genres, key=lambda genre: genre.genre_id)


def sample_genres(
    available: Sequence[GenreRef],
    count: int,
    rng: random.Random,
) -> list[GenreRef]:
    """Equal-weight, without-replacement sample of ``count`` genres.

    Raises ``InsufficientCandidatesError`` when the pool is smaller than
    ``count`` (bounded, explicit outcome).
    """
    pool = list(available)
    if len(pool) < count:
        raise InsufficientCandidatesError(
            f"need {count} eligible genres, only {len(pool)} available"
        )
    return list(rng.sample(pool, count))


def next_pick_index(pick_history: Mapping[str, Sequence[int]]) -> int:
    """The global pick index the next committed pick would receive (1-based)."""
    return max((max(indices) for indices in pick_history.values() if indices), default=0) + 1


def select_daily_genres(
    eligible: Sequence[GenreRef],
    count: int,
    rng: random.Random,
    pick_history: Mapping[str, Sequence[int]] | None = None,
    cooldown_picks: int = DEFAULT_COOLDOWN_PICKS,
    family_limits: Mapping[str, int] | None = None,
    max_attempts: int = MAX_SAMPLING_ATTEMPTS,
) -> list[GenreRef]:
    """Select ``count`` genres with equal opportunity under cooldown + family
    diversity constraints.

    - Candidates are stable-sorted (deterministic order);
    - genres in cooldown are filtered out;
    - equal-weight sampling respects family limits with bounded retries;
    - unsatisfiable constraints terminate with ``InsufficientCandidatesError``
      (never an unbounded loop);
    - the input ``eligible`` sequence is never mutated.
    """
    pick_history = {} if pick_history is None else pick_history
    family_limits = DEFAULT_FAMILY_LIMITS if family_limits is None else family_limits
    nxt = next_pick_index(pick_history)

    available = filter_available(
        sort_genres(eligible),
        pick_history,
        nxt,
        cooldown_picks,
    )
    if len(available) < count:
        raise InsufficientCandidatesError(
            f"need {count} eligible genres outside cooldown, only {len(available)} available"
        )

    for _ in range(max_attempts):
        chosen = sample_genres(available, count, rng)
        if family_ok(chosen, family_limits):
            return chosen
    raise InsufficientCandidatesError(
        "cannot satisfy family diversity constraints within bounded attempts"
    )


__all__ = [
    "MAX_SAMPLING_ATTEMPTS",
    "next_pick_index",
    "sample_genres",
    "select_daily_genres",
    "sort_genres",
]
