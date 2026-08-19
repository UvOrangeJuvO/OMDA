"""T2.1 equal-opportunity statistical test (SPEC §7-2, D.3).

Loose, non-flaky thresholds: with a fixed seed and a large sample, each genre's
selection count must stay within +/-10% of the uniform expectation. No
popularity/tier/quality input exists in the selector — the only signal is
eligibility + cooldown + family limits.
"""

from __future__ import annotations

from omda.core.genre import select_daily_genres
from omda.ports.domain import GenreRef
from omda.seed import make_rng

GENRES = [GenreRef(f"g{i:02d}", f"Genre {i}", f"F{i % 3}") for i in range(10)]
COUNT = 3
SAMPLES = 20_000
TOLERANCE = 0.10


def test_equal_opportunity_within_tolerance() -> None:
    rng = make_rng("equal-opportunity-check")
    counts = {g.genre_id: 0 for g in GENRES}
    for _ in range(SAMPLES):
        chosen = select_daily_genres(GENRES, COUNT, rng)
        for genre in chosen:
            counts[genre.genre_id] += 1

    expected = SAMPLES * COUNT / len(GENRES)
    for genre_id, count in counts.items():
        deviation = abs(count - expected) / expected
        assert deviation <= TOLERANCE, (
            f"genre {genre_id}: {count} vs expected {expected:.0f} (dev {deviation:.3f})"
        )


def test_no_duplicate_within_run_across_samples() -> None:
    rng = make_rng("no-dup-check")
    for _ in range(1000):
        chosen = select_daily_genres(GENRES, COUNT, rng)
        assert len({g.genre_id for g in chosen}) == COUNT
