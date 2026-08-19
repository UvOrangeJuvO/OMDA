"""T1.6 property-test skeleton: seed determinism and reproducibility (SPEC §6).

Full Genre equal-opportunity statistics arrive with G2/T2.1 (reviewed
implementation choice, OD-9); this module pins the deterministic-RNG
foundation they build on. Thresholds here are deliberately loose to avoid
flaky failures (R-011).
"""

from __future__ import annotations

from omda.seed import make_rng, new_seed, reseed_rng


def test_same_seed_reproduces_exact_sequence() -> None:
    rng_a = make_rng("run-2026-08-19")
    rng_b = make_rng("run-2026-08-19")
    assert [rng_a.random() for _ in range(100)] == [rng_b.random() for _ in range(100)]


def test_different_seeds_give_different_sequences() -> None:
    rng_a = make_rng("seed-a")
    rng_b = make_rng("seed-b")
    assert [rng_a.random() for _ in range(50)] != [rng_b.random() for _ in range(50)]


def test_reseed_produces_independent_reproducible_stream() -> None:
    first = make_rng("fixed")
    values = [first.random() for _ in range(20)]
    second = reseed_rng(first, "fixed")  # fresh generator from the same seed
    assert [second.random() for _ in range(20)] == values


def test_new_seed_is_unpredictable_and_usable() -> None:
    a, b = new_seed(), new_seed()
    assert a != b
    assert make_rng(a).random() != make_rng(b).random()


def test_rough_uniformity_sanity_within_loose_bounds() -> None:
    # Loose statistical sanity only: 10k draws into 4 buckets must not be wildly skewed.
    rng = make_rng("uniformity-check")
    buckets = [0, 0, 0, 0]
    for _ in range(10_000):
        buckets[rng.randrange(4)] += 1
    expected = 10_000 / 4
    for count in buckets:
        assert abs(count - expected) / expected < 0.1  # 10% tolerance, non-flaky
