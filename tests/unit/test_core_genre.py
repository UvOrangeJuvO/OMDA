"""T2.1–T2.3 Genre Core unit tests: equal opportunity, cooldown boundaries,
family diversity, determinism and bounded termination."""

from __future__ import annotations

import pytest

from omda.core.cooldown import filter_available, is_available
from omda.core.diversity import DEFAULT_FAMILY_LIMITS, family_ok
from omda.core.genre import next_pick_index, sample_genres, select_daily_genres, sort_genres
from omda.ports.domain import GenreRef
from omda.ports.errors import InsufficientCandidatesError
from omda.seed import make_rng

G1 = GenreRef("bebop", "Bebop", "Jazz")
G2 = GenreRef("ambient", "Ambient", "Electronic")
G3 = GenreRef("krautrock", "Krautrock", "Rock")
G4 = GenreRef("tuareg", "Tuareg Music", "Regional")
G5 = GenreRef("dnb", "Drum and Bass", "Electronic")
GENRES = [G1, G2, G3, G4, G5]


# --- T2.1 equal opportunity / determinism -------------------------------------


def test_sort_genres_is_stable_by_genre_id() -> None:
    assert sort_genres(GENRES) == sorted(GENRES, key=lambda g: g.genre_id)
    # Order of input must not matter.
    assert sort_genres(list(reversed(GENRES))) == sort_genres(GENRES)


def test_same_seed_reproduces_selection() -> None:
    first = select_daily_genres(GENRES, 3, make_rng("seed-x"))
    second = select_daily_genres(GENRES, 3, make_rng("seed-x"))
    assert first == second


def test_sample_insufficient_pool_raises_bounded() -> None:
    with pytest.raises(InsufficientCandidatesError):
        sample_genres([G1, G2], 3, make_rng("s"))


def test_selection_does_not_mutate_input() -> None:
    snapshot = list(GENRES)
    select_daily_genres(GENRES, 3, make_rng("s"))
    assert list(GENRES) == snapshot


def test_selection_without_popularity_signal_is_equal_opportunity_smoke() -> None:
    # GenreRef carries no popularity/rating/tier field; the selector can only see
    # identity/eligibility. A fixed small sample must still span families.
    chosen = select_daily_genres(GENRES, 3, make_rng("s"))
    assert len(chosen) == 3
    assert len({g.genre_id for g in chosen}) == 3


# --- T2.2 cooldown engine -----------------------------------------------------


def test_cooldown_boundary_30_and_31() -> None:
    # Committed at p=1: ineligible for 2..31, eligible again at 32 (p+31).
    history = {"ambient": [1]}
    assert not is_available(history["ambient"], next_pick_index=2)   # p+1
    assert not is_available(history["ambient"], next_pick_index=30)  # p+29
    assert not is_available(history["ambient"], next_pick_index=31)  # p+30
    assert is_available(history["ambient"], next_pick_index=32)      # p+31


def test_empty_history_is_available() -> None:
    assert is_available([], next_pick_index=1)


def test_cooldown_uses_latest_pick_only() -> None:
    # Multiple committed picks: the most recent one governs eligibility.
    assert not is_available([1, 20], next_pick_index=40)   # 40-20=20 <= 30
    assert is_available([1, 20], next_pick_index=51)       # 51-20=31 > 30


def test_filter_available_removes_cooled_genres() -> None:
    history = {"ambient": [1], "bebop": [40]}
    available = filter_available(GENRES, history, next_pick_index=41)
    ids = {g.genre_id for g in available}
    assert "bebop" not in ids  # 41-40=1 -> cooling
    assert "ambient" in ids    # 41-1=40 > 30 -> restored


def test_next_pick_index_derived_from_history() -> None:
    assert next_pick_index({}) == 1
    assert next_pick_index({"ambient": [5], "jazz": [9]}) == 10


# --- T2.3 family diversity ----------------------------------------------------


def test_family_limit_default_regional_one_per_run() -> None:
    assert DEFAULT_FAMILY_LIMITS["Regional"] == 1
    assert family_ok([G1, G2, G3])  # all distinct families
    # Electronic has no default limit: two Electronic genres are allowed.
    assert family_ok([G2, G5, G1])
    assert family_ok([G2, G5, G3])


def test_family_limit_regional_two_selected_rejected() -> None:
    regional_b = GenreRef("regional-x", "Regional X", "Regional")
    assert not family_ok([G4, regional_b, G1])  # two Regional > limit 1


def test_diversity_satisfiable_uses_distinct_families() -> None:
    chosen = select_daily_genres(GENRES, 3, make_rng("s"))
    assert len({g.family for g in chosen}) >= 2  # not all same family, bounded


def test_diversity_unsatisfiable_terminates_bounded() -> None:
    # Only one genre is not in cooldown -> cannot pick 3.
    history = {g.genre_id: [1] for g in GENRES if g.genre_id != "ambient"}
    with pytest.raises(InsufficientCandidatesError):
        select_daily_genres(GENRES, 3, make_rng("s"), pick_history=history)


def test_family_limits_do_not_starve_family_across_runs() -> None:
    # Constraint is per-run; over many runs each genre keeps being selected
    # (no permanent starvation): run 1 picks Regional once, run 2 may again.
    for run in range(10):
        chosen = select_daily_genres(GENRES, 3, make_rng(f"run-{run}"))
        assert sum(1 for g in chosen if g.family == "Regional") <= 1
    # Regional genre is eventually picked across runs (not permanently excluded).
    picked_regional = any(
        any(g.genre_id == "tuareg" for g in select_daily_genres(GENRES, 3, make_rng(f"s-{i}")))
        for i in range(50)
    )
    assert picked_regional
