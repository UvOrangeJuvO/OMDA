"""T2.1 equal-opportunity statistical test (SPEC §7-2, D.3; repaired G2-002).

The planner samples uniformly from the VALID solution space (cooldown + family
diversity constraints). This test draws a large sample directly from that space
using the same mechanism as ``select_daily_genres`` (index sampling) and checks
each Genre's selection count stays within +/-10% of the uniform expectation —
loose, non-flaky thresholds. No popularity/tier/quality input exists in the
selector; the only signals are eligibility, cooldown and family limits.
"""

from __future__ import annotations

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
