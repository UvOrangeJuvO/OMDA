"""Genre equal-opportunity selection (T2.1) and the daily Genre planner
(repaired G2-001/G2-002).

Equal opportunity (SPEC §2.1): every valid, eligible Genre outside cooldown has
equal base selection opportunity. No popularity, follower/rating count,
accessibility, LLM judgment or tier probability ever enters this module.

Global ordered pick indices (G2-001): the single authoritative next global pick
index comes from the committed history (``latest_pick_index + 1``) and is passed
in as ``global_start_index``. Position ``i`` of the daily plan receives global
index ``global_start_index + i``; cooldown is evaluated at each exact position,
never once against the first position only.

Bounded complete solving (G2-002): instead of probabilistic rejection sampling,
the planner enumerates every valid ordered sequence (respecting per-position
cooldown plus family/parent set constraints) up to a bound and samples uniformly
from the valid space. A satisfiable pool can therefore never be mislabeled
insufficient because of random luck; truly unsatisfiable pools terminate with an
explicit ``InsufficientCandidatesError``.
"""

from __future__ import annotations

import random
from collections import Counter
from collections.abc import Mapping, Sequence
from functools import lru_cache

from omda.core.cooldown import DEFAULT_COOLDOWN_PICKS, is_available
from omda.core.diversity import DEFAULT_FAMILY_LIMITS
from omda.ports.domain import GenreRef
from omda.ports.errors import InsufficientCandidatesError

MAX_ENUMERATED_SOLUTIONS = 100_000


def sort_genres(genres: Sequence[GenreRef]) -> list[GenreRef]:
    """Stable canonical ordering by genre_id (iteration-order independent)."""
    return sorted(genres, key=lambda genre: genre.genre_id)


def next_pick_index(pick_history: Mapping[str, Sequence[int]]) -> int:
    """Global pick index the next committed pick would receive (1-based).

    NOTE: callers MUST prefer ``HistoryPort.latest_pick_index() + 1`` when
    available — this fallback derives the index only from the supplied history
    (G2-001: never infer the global clock solely from currently visible Genres).
    """
    return max((max(indices) for indices in pick_history.values() if indices), default=0) + 1


def enumerate_valid_selections(
    eligible: Sequence[GenreRef],
    count: int,
    pick_history: Mapping[str, Sequence[int]],
    global_start_index: int,
    cooldown_picks: int = DEFAULT_COOLDOWN_PICKS,
    family_limits: Mapping[str, int] | None = None,
    parent_limits: Mapping[str, int] | None = None,
    parents_by_genre: Mapping[str, Sequence[str]] | None = None,
    max_solutions: int = MAX_ENUMERATED_SOLUTIONS,
) -> list[tuple[GenreRef, ...]]:
    """Enumerate every valid ordered selection (bounded; memoized per input).

    A sequence is valid when, at each position ``i`` with global index
    ``global_start_index + i``:
    - the Genre is not in cooldown at that exact position;
    - per-family limits (set constraint) are respected across the run;
    - per-parent limits (taxonomy ``parents``) are respected across the run;
    - each Genre appears at most once.

    Results are cached by input parameters so repeated planning for the same
    inputs (e.g. statistical property tests) does not re-enumerate.
    """
    family_limits = DEFAULT_FAMILY_LIMITS if family_limits is None else family_limits
    parent_limits = {} if parent_limits is None else parent_limits
    parents_by_genre = {} if parents_by_genre is None else parents_by_genre
    by_id = {g.genre_id: g for g in eligible}

    key = (
        tuple(sorted((g.genre_id, g.family) for g in eligible)),
        count,
        frozenset((k, tuple(v)) for k, v in pick_history.items()),
        global_start_index,
        cooldown_picks,
        frozenset(family_limits.items()),
        frozenset(parent_limits.items()),
        frozenset((k, tuple(v)) for k, v in parents_by_genre.items()),
        max_solutions,
    )
    cached = _enumerate_cached(*key)
    return [tuple(by_id[genre_id] for genre_id in sequence) for sequence in cached]


@lru_cache(maxsize=128)
def _enumerate_cached(
    eligible_frozen: tuple[tuple[str, str], ...],
    count: int,
    pick_history_frozen: frozenset,
    global_start_index: int,
    cooldown_picks: int,
    family_limits_frozen: frozenset,
    parent_limits_frozen: frozenset,
    parents_frozen: frozenset,
    max_solutions: int,
) -> tuple[tuple[str, ...], ...]:
    pick_history: dict[str, tuple[int, ...]] = dict(pick_history_frozen)
    family_limits: dict[str, int] = dict(family_limits_frozen)
    parent_limits: dict[str, int] = dict(parent_limits_frozen)
    parents_by_genre: dict[str, tuple[str, ...]] = dict(parents_frozen)
    candidates = [GenreRef(gid, gid, family) for gid, family in eligible_frozen]
    solutions: list[tuple[str, ...]] = []

    def backtrack(
        path: list[GenreRef],
        family_counts: Counter,
        parent_counts: Counter,
    ) -> None:
        if len(solutions) >= max_solutions:
            return
        if len(path) == count:
            solutions.append(tuple(g.genre_id for g in path))
            return
        position_index = global_start_index + len(path)
        chosen_ids = {g.genre_id for g in path}
        for genre in candidates:
            if genre.genre_id in chosen_ids:
                continue
            if not is_available(
                pick_history.get(genre.genre_id, ()), position_index, cooldown_picks
            ):
                continue
            family_limit = family_limits.get(genre.family)
            if family_limit is not None and family_counts[genre.family] >= family_limit:
                continue
            genre_parents = parents_by_genre.get(genre.genre_id, ())
            parent_violated = False
            for parent in genre_parents:
                parent_limit = parent_limits.get(parent)
                if parent_limit is not None and parent_counts[parent] >= parent_limit:
                    parent_violated = True
                    break
            if parent_violated:
                continue
            family_counts[genre.family] += 1
            for parent in genre_parents:
                parent_counts[parent] += 1
            path.append(genre)
            backtrack(path, family_counts, parent_counts)
            path.pop()
            family_counts[genre.family] -= 1
            for parent in genre_parents:
                parent_counts[parent] -= 1

    backtrack([], Counter(), Counter())
    return tuple(solutions)


def select_daily_genres(
    eligible: Sequence[GenreRef],
    count: int,
    rng: random.Random,
    pick_history: Mapping[str, Sequence[int]] | None = None,
    global_start_index: int | None = None,
    cooldown_picks: int = DEFAULT_COOLDOWN_PICKS,
    family_limits: Mapping[str, int] | None = None,
    parent_limits: Mapping[str, int] | None = None,
    parents_by_genre: Mapping[str, Sequence[str]] | None = None,
    max_solutions: int = MAX_ENUMERATED_SOLUTIONS,
) -> list[GenreRef]:
    """Select ``count`` ordered Genres with equal opportunity, sampling uniformly
    from the valid solution space (bounded complete; G2-001/G2-002).

    - ``global_start_index`` is the authoritative next global pick index
      (``latest_pick_index + 1``); when omitted it is derived from the supplied
      history as a documented fallback;
    - cooldown is evaluated at each exact global position;
    - family/parent limits are set constraints, never scores;
    - the input ``eligible`` sequence is never mutated.
    """
    pick_history = {} if pick_history is None else pick_history
    start = (
        global_start_index
        if global_start_index is not None
        else next_pick_index(pick_history)
    )
    solutions = enumerate_valid_selections(
        eligible,
        count,
        pick_history,
        start,
        cooldown_picks,
        family_limits,
        parent_limits,
        parents_by_genre,
        max_solutions,
    )
    if not solutions:
        raise InsufficientCandidatesError(
            f"no ordered selection of {count} genres satisfies cooldown and "
            "family/parent constraints (bounded complete solve found none)"
        )
    return list(solutions[rng.randrange(len(solutions))])


__all__ = [
    "MAX_ENUMERATED_SOLUTIONS",
    "enumerate_valid_selections",
    "next_pick_index",
    "select_daily_genres",
    "sort_genres",
]
