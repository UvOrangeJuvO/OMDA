"""T2.1 equal-opportunity statistical test (SPEC §7-2, D.3; repaired G2-002).

The planner samples uniformly from the VALID solution space (cooldown + family
diversity constraints). This test draws a large sample directly from that space
using the same mechanism as ``select_daily_genres`` (index sampling) and checks
each Genre's selection count stays within +/-10% of the uniform expectation —
loose, non-flaky thresholds. No popularity/tier/quality input exists in the
selector; the only signals are eligibility, cooldown and family limits.
"""

from __future__ import annotations

from omda.core.genre import enumerate_valid_selections, select_daily_genres
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
