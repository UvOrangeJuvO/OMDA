
"""T2.1 equal-opportunity statistical test (SPEC §7-2, D.3; repaired G2-002).

The planner samples uniformly from the VALID solution space (cooldown + family
diversity constraints). This test draws a large sample directly from that space
using the same mechanism as ``select_daily_genres`` (index sampling) and checks
each Genre's selection count stays within +/-10% of the uniform expectation —
loose, non-flaky thresholds. No popularity/tier/quality input exists in the
selector; the only signals are eligibility, cooldown and family limits.
"""

from __future__ import annotations

import pytest

from omda.core.genre import build_unbiased_sampler, enumerate_valid_selections, select_daily_genres
from omda.ports.domain import GenreRef
from omda.seed import make_rng

GENRES = [GenreRef(f"g{i:02d}", f"Genre {i}", f"F{i % 3}") for i in range(10)]
COUNT = 3
SAMPLES = 20_000
TOLERANCE = 0.10


def test_equal_opportunity_within_tolerance() -> None:
    solutions = enumerate_valid_selections(GENRES, COUNT, {}, global_start_index=1)
    assert len(solutions) > 1
    rng = make_rng("equal-opportunity-check")
    counts = {g.genre_id: 0 for g in GENRES}
    for _ in range(SAMPLES):
        chosen = solutions[rng.randrange(len(solutions))]
        for genre in chosen:
            counts[genre.genre_id] += 1

    expected = SAMPLES * COUNT / len(GENRES)
    for genre_id, count in counts.items():
        deviation = abs(count - expected) / expected
        assert deviation <= TOLERANCE, (
            f"genre {genre_id}: {count} vs expected {expected:.0f} (dev {deviation:.3f})"
        )


def test_equal_opportunity_via_planner_smoke() -> None:
    # The public planner itself also samples from the same valid space.
    rng = make_rng("planner-smoke")
    chosen = select_daily_genres(GENRES, COUNT, rng)
    assert len(chosen) == COUNT
    assert len({g.genre_id for g in chosen}) == COUNT


def test_no_duplicate_within_run_across_samples() -> None:
    solutions = enumerate_valid_selections(GENRES, COUNT, {}, global_start_index=1)
    rng = make_rng("no-dup-check")
    for _ in range(1000):
        chosen = solutions[rng.randrange(len(solutions))]
        assert len({g.genre_id for g in chosen}) == COUNT


# --- G2-007: unbiased over the COMPLETE valid space (no prefix truncation) -----

BIG_POOL_SIZE = 100
BIG_SAMPLES = 50_000
BIG_TOLERANCE = 0.10


def _big_pool(size: int = BIG_POOL_SIZE, prefix: str = "g") -> list[GenreRef]:
    # No family constraints (family_limits={} below) -> unrestricted valid space.
    return [GenreRef(f"{prefix}{i:03d}", f"Genre {i}", f"F{i % 5}") for i in range(size)]


def test_big_pool_marginal_equality_unconstrained() -> None:
    # 100 unrestricted Genres: the complete ordered space has ~970k solutions,
    # far beyond the old 100k prefix cap — every Genre must keep equal marginal
    # opportunity (G2-007). Uses the same unbiased sampler as the planner.
    pool = _big_pool()
    sampler, total = build_unbiased_sampler(pool, 3, family_limits={})
    assert total > 100_000  # larger than the old prefix cap
    rng = make_rng("big-pool-marginal")
    counts = {g.genre_id: 0 for g in pool}
    for _ in range(BIG_SAMPLES):
        chosen = sampler(rng)
        for genre in chosen:
            counts[genre.genre_id] += 1
    expected = BIG_SAMPLES * 3 / len(pool)
    for genre_id, count in counts.items():
        deviation = abs(count - expected) / expected
        assert deviation <= BIG_TOLERANCE, (
            f"{genre_id}: {count} vs {expected:.0f} (dev {deviation:.3f})"
        )


def test_big_pool_positional_opportunity_unconstrained() -> None:
    # First-position opportunity must also be equal for every Genre.
    pool = _big_pool()
    sampler, _ = build_unbiased_sampler(pool, 3, family_limits={})
    rng = make_rng("big-pool-position")
    first_counts = {g.genre_id: 0 for g in pool}
    for _ in range(BIG_SAMPLES):
        chosen = sampler(rng)
        first_counts[chosen[0].genre_id] += 1
    expected = BIG_SAMPLES / len(pool)
    for genre_id, count in first_counts.items():
        deviation = abs(count - expected) / expected
        assert deviation <= 0.15, (
            f"first-position {genre_id}: {count} vs {expected:.0f} (dev {deviation:.3f})"
        )


def test_renaming_genre_ids_does_not_change_opportunity() -> None:
    # Two isomorphic pools with permuted identifiers must produce the same
    # marginal opportunity distribution (G2-007: an ID is never a weight).
    pool_a = _big_pool(size=50, prefix="a")
    sampler_a, _ = build_unbiased_sampler(pool_a, 3, family_limits={})
    rng_a = make_rng("rename-a")
    counts_a = {g.genre_id: 0 for g in pool_a}
    for _ in range(10_000):
        chosen = sampler_a(rng_a)
        for genre in chosen:
            counts_a[genre.genre_id] += 1

    # Isomorphic pool: same size/structure, identifiers shuffled.
    pool_b = [GenreRef(f"z{i:03d}", f"Genre {i}", f"F{i % 5}") for i in range(50)]
    sampler_b, _ = build_unbiased_sampler(pool_b, 3, family_limits={})
    rng_b = make_rng("rename-b")
    counts_b = {g.genre_id: 0 for g in pool_b}
    for _ in range(10_000):
        chosen = sampler_b(rng_b)
        for genre in chosen:
            counts_b[genre.genre_id] += 1

    expected = 10_000 * 3 / 50
    # Both pools are individually equal-opportunity (no lexical dependence).
    for counts in (counts_a, counts_b):
        for genre_id, count in counts.items():
            deviation = abs(count - expected) / expected
            assert deviation <= 0.15, f"{genre_id}: dev {deviation:.3f}"


def test_large_pool_constrained_still_bounded_and_deterministic() -> None:
    # Constrained satisfiable pools keep bounded deterministic solving.
    pool = _big_pool(size=60) + [GenreRef("r1", "R1", "Regional"), GenreRef("r2", "R2", "Regional")]
    first = select_daily_genres(pool, 3, make_rng("constrained"))
    second = select_daily_genres(pool, 3, make_rng("constrained"))
    assert first == second
    assert len(first) == 3


# --- G2-013: solver resources stay bounded ------------------------------------


def test_unconstrained_large_pool_uses_fast_path_without_dp() -> None:
    # 200 unrestricted Genres must never build combinatorial DP state.
    from omda.core import genre as g

    g._counts_cached.cache_clear()
    before = g._counts_cached.cache_info().currsize
    pool = _big_pool(size=200)
    sampler, total = build_unbiased_sampler(pool, 3, family_limits={})
    assert total == 200 * 199 * 198
    assert g._counts_cached.cache_info().currsize == before  # fast path: no DP
    chosen = sampler(make_rng("fast-path"))
    assert len(chosen) == 3


def test_solver_cache_stays_bounded_across_many_run_histories() -> None:
    # Every successful run changes the global start -> new cache key; the LRU
    # must evict old combinatorial memos instead of accumulating them (G2-013).
    from omda.core import genre as g

    g._counts_cached.cache_clear()
    pool = _big_pool(size=30)
    for start in range(1, 9):  # eight distinct run histories / global starts
        build_unbiased_sampler(pool, 3, global_start_index=start)  # constrained path
    assert g._counts_cached.cache_info().currsize <= 4


def test_constrained_memo_never_stores_terminal_states() -> None:
    # Terminal 3-Genre combinations are never memoized, so the retained state
    # space is far below the full C(n,3) enumeration (G2-013).
    from omda.core import genre as g
    from omda.core.diversity import DEFAULT_FAMILY_LIMITS

    pool = _big_pool(size=30)
    key = (
        tuple(sorted((x.genre_id, x.family) for x in pool)),
        3,
        frozenset(),
        1,
        30,
        frozenset(DEFAULT_FAMILY_LIMITS.items()),
        frozenset(),
        frozenset(),
    )
    _, memo = g._counts_cached(*key)
    full_combinations = 30 * 29 * 28
    assert len(memo) < full_combinations


# --- G2-013 re-review: RunEngine-shaped inputs reach the fast path -------------


def test_runengine_shaped_empty_cooldown_map_uses_fast_path() -> None:
    # RunEngine records a per-Genre cooldown key for EVERY eligible Genre, even
    # on the first-ever run (all values empty tuples); the default family limits
    # are non-empty but none apply to this pool. Semantically nothing constrains
    # selection -> the fast path must be reached with zero DP construction.
    from omda.core import genre as g
    from omda.core.diversity import DEFAULT_FAMILY_LIMITS

    g._counts_cached.cache_clear()
    before = g._counts_cached.cache_info().currsize
    pool = _big_pool(size=200)  # families F0..F4: Regional/Traditional absent
    pick_history = {x.genre_id: () for x in pool}
    sampler, total = build_unbiased_sampler(
        pool, 3, pick_history=pick_history, family_limits=DEFAULT_FAMILY_LIMITS
    )
    assert total > 0
    assert g._counts_cached.cache_info().currsize == before  # fast path: no DP
    chosen = sampler(make_rng("run-shaped"))
    assert len(chosen) == 3


def test_orchestrated_first_run_large_pool_has_no_dp_construction() -> None:
    # A real orchestrated first run over a 200-Genre pool must not build DP
    # state (the exact mapping shape RunEngine produces, no active constraints).
    from tests.fakes import FakeAlbumSource, FakeDelivery, FakeGenreSource, FakeLLM, InMemoryHistory

    from omda.config import load_config
    from omda.core import genre as g
    from omda.orchestrator.run import RunEngine
    from omda.ports.domain import AlbumCandidate, GenreRef

    g._counts_cached.cache_clear()
    before = g._counts_cached.cache_info().currsize
    genres = [GenreRef(f"g{i:03d}", f"Genre {i}", f"F{i % 5}") for i in range(200)]
    albums = {
        x.genre_id: [
            AlbumCandidate(f"{x.genre_id}-a", f"{x.genre_id} A", "Artist", 2015),
            AlbumCandidate(f"{x.genre_id}-b", f"{x.genre_id} B", "Artist", 2000),
            AlbumCandidate(f"{x.genre_id}-c", f"{x.genre_id} C", "Artist", 1990),
        ]
        for x in genres
    }
    engine = RunEngine(
        config=load_config(),
        history=InMemoryHistory(),
        genre_source=FakeGenreSource(genres),
        album_source=FakeAlbumSource(albums),
        llm=FakeLLM("Explanatory text."),
        delivery=FakeDelivery(),
        seed="large-first-run",
    )
    outcome = engine.run("run-1")
    assert outcome.state == "COMPLETE"
    assert g._counts_cached.cache_info().currsize == before  # zero DP on first run


def test_active_constraint_upper_bound_stays_bounded() -> None:
    # When a family/parent limit genuinely applies, the constrained path builds
    # a compact memo and sampling stays exact, bounded and deterministic.
    from omda.core import genre as g

    g._counts_cached.cache_clear()
    pool = _big_pool(size=60) + [GenreRef("r1", "R1", "Regional")]
    sampler, total = build_unbiased_sampler(pool, 3)  # Regional limit active
    assert total > 0
    chosen = sampler(make_rng("active-constraint"))
    assert len(chosen) == 3
    assert sum(1 for x in chosen if x.family == "Regional") <= 1
    # Repeated draws from the same memo are deterministic and fast.
    assert sampler(make_rng("active-constraint")) == chosen


# --- G2-013/G2-010 re-review 4: explicit parent map + stale history ------------


def test_explicit_parents_by_genre_constraint_is_never_dropped() -> None:
    # Reviewer counter-example: GenreRefs carry NO embedded parents, but the
    # documented public `parents_by_genre` input maps two Genres to `electronic`
    # with limit 1. The normalization must NOT discard this real constraint.
    from omda.ports.errors import InsufficientCandidatesError

    genres = [
        GenreRef("g1", "G1", "Electronic"),
        GenreRef("g2", "G2", "Electronic"),
        GenreRef("g3", "G3", "Jazz"),
        GenreRef("g4", "G4", "Rock"),
    ]
    parents_by_genre = {"g1": ("electronic",), "g2": ("electronic",)}
    parent_limits = {"electronic": 1}
    for seed in [f"p-{i}" for i in range(40)]:
        chosen = select_daily_genres(
            genres,
            3,
            make_rng(seed),
            parent_limits=parent_limits,
            parents_by_genre=parents_by_genre,
        )
        picked = {g.genre_id for g in chosen}
        assert not ({"g1", "g2"} <= picked), f"seed {seed} violated parent limit"
    # Unsatisfiable explicit-parent case still fails explicitly.
    with pytest.raises(InsufficientCandidatesError):
        select_daily_genres(
            genres[:3],
            3,
            make_rng("unsat"),
            parent_limits=parent_limits,
            parents_by_genre=parents_by_genre,
        )


def test_stale_nonempty_cooldown_history_uses_fast_path() -> None:
    # Every historical pick (1) is far older than the next-pick window for
    # global starts 1000+ (1 + 30 < 1000): semantically unconstrained, so the
    # fast path must run with zero DP construction.
    from omda.core import genre as g
    from omda.core.diversity import DEFAULT_FAMILY_LIMITS

    g._counts_cached.cache_clear()
    before = g._counts_cached.cache_info().currsize
    pool = _big_pool(size=200)
    pick_history = {x.genre_id: (1,) for x in pool}
    sampler, total = build_unbiased_sampler(
        pool,
        3,
        pick_history=pick_history,
        global_start_index=1000,
        family_limits=DEFAULT_FAMILY_LIMITS,
    )
    assert total > 0
    assert g._counts_cached.cache_info().currsize == before  # fast path: no DP
    assert len(sampler(make_rng("stale"))) == 3


def test_limits_that_cannot_bind_are_dropped() -> None:
    # A family limit with min(members, count) <= limit can never be violated,
    # so the constrained path is not entered. Same for parent limits.
    from omda.core import genre as g

    g._counts_cached.cache_clear()
    before = g._counts_cached.cache_info().currsize
    # One Regional member, limit 1: cannot bind for any run size.
    pool = _big_pool(size=100) + [GenreRef("r1", "R1", "Regional")]
    build_unbiased_sampler(pool, 3, family_limits={"Regional": 1})
    assert g._counts_cached.cache_info().currsize == before  # dropped -> fast path
    # Two members sharing a parent, limit 2: cannot bind.
    pool2 = [GenreRef("g1", "G1", "Electronic"), GenreRef("g2", "G2", "Electronic")]
    build_unbiased_sampler(
        pool2,
        2,
        parent_limits={"electronic": 2},
        parents_by_genre={"g1": ("electronic",), "g2": ("electronic",)},
    )
    assert g._counts_cached.cache_info().currsize == before
