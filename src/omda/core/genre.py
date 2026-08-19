"""Genre equal-opportunity selection (T2.1) and the daily Genre planner
(repaired G2-001/G2-002/G2-007).

Equal opportunity (SPEC §2.1): every valid, eligible Genre outside cooldown has
equal base selection opportunity. No popularity, follower/rating count,
accessibility, LLM judgment or tier probability ever enters this module.

Global ordered pick indices (G2-001): the single authoritative next global pick
index comes from the committed history (``latest_pick_index + 1``) and is passed
in as ``global_start_index``. Position ``i`` of the daily plan receives global
index ``global_start_index + i``; cooldown is evaluated at each exact position.

Unbiased bounded solving (G2-007): selection samples uniformly over the COMPLETE
valid ordered solution space using count-based dynamic programming + unranking —
never a lexicographically early prefix. ``enumerate_valid_selections`` remains
for small-space inspection, but the planner itself never truncates the solution
space, so a Genre's identifier can never become a probability weight.
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
    """Enumerate valid ordered selections (INSPECTION ONLY, small spaces).

    Used by property tests and audits on pools whose valid space is small. The
    planner never uses this for sampling — it is unbiased via
    :func:`select_daily_genres` (G2-007).
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


@lru_cache(maxsize=4)
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


@lru_cache(maxsize=4)
def _counts_cached(
    eligible_frozen: tuple[tuple[str, str], ...],
    pick_count: int,
    pick_history_frozen: frozenset,
    global_start_index: int,
    cooldown_picks: int,
    family_limits_frozen: frozenset,
    parent_limits_frozen: frozenset,
    parents_frozen: frozenset,
) -> tuple[tuple[str, ...], dict[tuple, int]]:
    """Count completions for reachable non-terminal states (G2-007 unbiased
    solver; G2-013 bounded resources).

    Returns ``(candidate_ids, memo)`` where ``memo`` maps non-terminal
    ``(chosen_frozen, family_counts_frozen, parent_counts_frozen)`` states to the
    number of valid completions. Terminal states are NEVER memoized, and the LRU
    retains at most a handful of input variants, so memory stays bounded even for
    large pools or many distinct run histories.
    """
    pick_history: dict[str, tuple[int, ...]] = dict(pick_history_frozen)
    family_limits: dict[str, int] = dict(family_limits_frozen)
    parent_limits: dict[str, int] = dict(parent_limits_frozen)
    parents_by_genre: dict[str, tuple[str, ...]] = dict(parents_frozen)
    candidate_ids = tuple(gid for gid, _ in eligible_frozen)
    families = {gid: family for gid, family in eligible_frozen}
    memo: dict[tuple, int] = {}

    def count_completions(
        chosen: frozenset,
        fam: tuple,
        par: tuple,
    ) -> int:
        position = len(chosen)
        if position == pick_count:
            # Terminal state: exactly one completion (itself); never memoized.
            return 1
        key = (chosen, fam, par)
        if key in memo:
            return memo[key]
        fam_map = dict(fam)
        par_map = dict(par)
        position_index = global_start_index + position
        total = 0
        for genre_id in candidate_ids:
            if genre_id in chosen:
                continue
            if not is_available(pick_history.get(genre_id, ()), position_index, cooldown_picks):
                continue
            family_limit = family_limits.get(families[genre_id])
            if family_limit is not None and fam_map.get(families[genre_id], 0) >= family_limit:
                continue
            genre_parents = parents_by_genre.get(genre_id, ())
            parent_violated = False
            for parent in genre_parents:
                parent_limit = parent_limits.get(parent)
                if parent_limit is not None and par_map.get(parent, 0) >= parent_limit:
                    parent_violated = True
                    break
            if parent_violated:
                continue
            new_fam = dict(fam_map)
            new_fam[families[genre_id]] = new_fam.get(families[genre_id], 0) + 1
            new_par = dict(par_map)
            for parent in genre_parents:
                new_par[parent] = new_par.get(parent, 0) + 1
            total += count_completions(
                chosen | {genre_id},
                tuple(sorted(new_fam.items())),
                tuple(sorted(new_par.items())),
            )
        memo[key] = total
        return total

    count_completions(
        frozenset(),
        tuple(),
        tuple(),
    )
    return candidate_ids, memo


def build_unbiased_sampler(
    eligible: Sequence[GenreRef],
    count: int,
    pick_history: Mapping[str, Sequence[int]] | None = None,
    global_start_index: int | None = None,
    cooldown_picks: int = DEFAULT_COOLDOWN_PICKS,
    family_limits: Mapping[str, int] | None = None,
    parent_limits: Mapping[str, int] | None = None,
    parents_by_genre: Mapping[str, Sequence[str]] | None = None,
) -> tuple[object, int]:
    """Build an unbiased sampler over the COMPLETE valid solution space (G2-007).

    Returns ``(sampler, total)`` where ``sampler(rng) -> list[GenreRef]`` draws a
    uniformly random valid ordered selection and ``total`` is the number of valid
    solutions (0 -> unsatisfiable).

    G2-013: the unconstrained fast path runs BEFORE any DP construction, so large
    unrestricted pools never build combinatorial state; constrained cases build a
    compact non-terminal memo once and reuse it across draws.
    """
    pick_history = {} if pick_history is None else pick_history
    family_limits = DEFAULT_FAMILY_LIMITS if family_limits is None else family_limits
    parent_limits = {} if parent_limits is None else parent_limits
    parents_by_genre = {} if parents_by_genre is None else parents_by_genre
    start = (
        global_start_index
        if global_start_index is not None
        else next_pick_index(pick_history)
    )

    by_id = {g.genre_id: g for g in eligible}
    candidate_ids = tuple(sorted(by_id))

    if not pick_history and not family_limits and not parent_limits:
        # G2-013 fast path: uniform sampling over all ordered selections is
        # exactly rng.sample — no DP, no combinatorial memory (G2-007 unbiased).
        from math import perm

        total = perm(len(candidate_ids), count) if len(candidate_ids) >= count else 0

        def fast_sampler(rng: random.Random) -> list[GenreRef]:
            return [by_id[gid] for gid in rng.sample(candidate_ids, count)]

        return fast_sampler, total

    key = (
        tuple(sorted((g.genre_id, g.family) for g in eligible)),
        count,
        frozenset((k, tuple(v)) for k, v in pick_history.items()),
        start,
        cooldown_picks,
        frozenset(family_limits.items()),
        frozenset(parent_limits.items()),
        frozenset((k, tuple(v)) for k, v in parents_by_genre.items()),
    )
    candidate_ids, memo = _counts_cached(*key)
    families = {g.genre_id: g.family for g in eligible}

    def sampler(rng: random.Random) -> list[GenreRef]:
        fam_map: dict[str, int] = {}
        par_map: dict[str, int] = {}
        chosen: set[str] = set()
        result: list[GenreRef] = []
        for position in range(count):
            position_index = start + position
            state = (
                frozenset(chosen),
                tuple(sorted(fam_map.items())),
                tuple(sorted(par_map.items())),
            )
            total = memo[state]
            if total <= 0:
                raise InsufficientCandidatesError("no valid completions (unbiased solver)")
            r = rng.randrange(total)
            picked_id: str | None = None
            for genre_id in candidate_ids:
                if genre_id in chosen:
                    continue
                if not is_available(
                    pick_history.get(genre_id, ()), position_index, cooldown_picks
                ):
                    continue
                family_limit = family_limits.get(families[genre_id])
                if (
                    family_limit is not None
                    and fam_map.get(families[genre_id], 0) >= family_limit
                ):
                    continue
                genre_parents = parents_by_genre.get(genre_id, ())
                if any(
                    parent_limits.get(p) is not None and par_map.get(p, 0) >= parent_limits[p]
                    for p in genre_parents
                ):
                    continue
                next_fam = dict(fam_map)
                next_fam[families[genre_id]] = next_fam.get(families[genre_id], 0) + 1
                next_par = dict(par_map)
                for parent in genre_parents:
                    next_par[parent] = next_par.get(parent, 0) + 1
                if len(chosen) + 1 == count:
                    # Terminal child: exactly one completion (never memoized).
                    branch_count = 1
                else:
                    branch_count = memo[
                        (
                            frozenset(chosen | {genre_id}),
                            tuple(sorted(next_fam.items())),
                            tuple(sorted(next_par.items())),
                        )
                    ]
                if r < branch_count:
                    picked_id = genre_id
                    chosen.add(genre_id)
                    fam_map = next_fam
                    par_map = next_par
                    break
                r -= branch_count
            if picked_id is None:
                raise InsufficientCandidatesError("no valid completions (unbiased solver)")
            result.append(by_id[picked_id])
        return result

    root_state = (frozenset(), tuple(), tuple())
    return sampler, memo.get(root_state, 0)


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
    over the COMPLETE valid solution space (unbiased, bounded; G2-001/G2-002/G2-007).

    - ``global_start_index`` is the authoritative next global pick index
      (``latest_pick_index + 1``); when omitted it is derived from the supplied
      history as a documented fallback;
    - cooldown is evaluated at each exact global position;
    - family/parent limits are set constraints, never scores;
    - the input ``eligible`` sequence is never mutated;
    - identifier ordering never influences opportunity (no prefix truncation).
    """
    sampler, _ = build_unbiased_sampler(
        eligible,
        count,
        pick_history,
        global_start_index,
        cooldown_picks,
        family_limits,
        parent_limits,
        parents_by_genre,
    )
    return sampler(rng)


__all__ = [
    "MAX_ENUMERATED_SOLUTIONS",
    "build_unbiased_sampler",
    "enumerate_valid_selections",
    "next_pick_index",
    "select_daily_genres",
    "sort_genres",
]
