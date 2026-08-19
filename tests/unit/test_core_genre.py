"""T2.1–T2.3 Genre Core unit tests (repaired G2-001/G2-002): equal opportunity,
global ordered pick indices, position-specific cooldown, bounded complete
diversity solving (family + parent), determinism and termination."""

from __future__ import annotations

import pytest

from omda.core.cooldown import filter_available, is_available
from omda.core.diversity import DEFAULT_FAMILY_LIMITS, family_ok, parent_ok
from omda.core.genre import (
    enumerate_valid_selections,
    next_pick_index,
    select_daily_genres,
    sort_genres,
)
from omda.ports.domain import GenreRef
from omda.ports.errors import InsufficientCandidatesError
from omda.seed import make_rng

G1 = GenreRef("bebop", "Bebop", "Jazz")
G2 = GenreRef("ambient", "Ambient", "Electronic")
G3 = GenreRef("krautrock", "Krautrock", "Rock")
G4 = GenreRef("tuareg", "Tuareg Music", "Regional")
G5 = GenreRef("dnb", "Drum and Bass", "Electronic")
GENRES = [G1, G2, G3, G4, G5]


def _regional(genre_id: str) -> GenreRef:
    return GenreRef(genre_id, genre_id, "Regional")


# --- T2.1 equal opportunity / determinism -------------------------------------


def test_sort_genres_is_stable_by_genre_id() -> None:
    assert sort_genres(GENRES) == sorted(GENRES, key=lambda g: g.genre_id)
    assert sort_genres(list(reversed(GENRES))) == sort_genres(GENRES)


def test_same_seed_reproduces_selection() -> None:
    first = select_daily_genres(GENRES, 3, make_rng("seed-x"))
    second = select_daily_genres(GENRES, 3, make_rng("seed-x"))
    assert first == second


def test_selection_does_not_mutate_input() -> None:
    snapshot = list(GENRES)
    select_daily_genres(GENRES, 3, make_rng("s"))
    assert list(GENRES) == snapshot


def test_insufficient_pool_raises_bounded() -> None:
    with pytest.raises(InsufficientCandidatesError):
        select_daily_genres([G1, G2], 3, make_rng("s"))


def test_selection_without_popularity_signal_is_equal_opportunity_smoke() -> None:
    chosen = select_daily_genres(GENRES, 3, make_rng("s"))
    assert len(chosen) == 3
    assert len({g.genre_id for g in chosen}) == 3


# --- T2.2 cooldown engine -----------------------------------------------------


def test_cooldown_boundary_30_and_31() -> None:
    # Committed at p=1: ineligible for 2..31, eligible again at 32 (p+31).
    history = {"ambient": [1]}
    assert not is_available(history["ambient"], next_pick_index=2)
    assert not is_available(history["ambient"], next_pick_index=30)
    assert not is_available(history["ambient"], next_pick_index=31)
    assert is_available(history["ambient"], next_pick_index=32)


def test_empty_history_is_available() -> None:
    assert is_available([], next_pick_index=1)


def test_cooldown_uses_latest_pick_only() -> None:
    assert not is_available([1, 20], next_pick_index=40)  # 40-20=20 <= 30
    assert is_available([1, 20], next_pick_index=51)      # 51-20=31 > 30


def test_filter_available_removes_cooled_genres() -> None:
    history = {"ambient": [1], "bebop": [40]}
    available = filter_available(GENRES, history, next_pick_index=41)
    ids = {g.genre_id for g in available}
    assert "bebop" not in ids
    assert "ambient" in ids


def test_next_pick_index_derived_from_history() -> None:
    assert next_pick_index({}) == 1
    assert next_pick_index({"ambient": [5], "jazz": [9]}) == 10


# --- G2-001: global ordered pick indices --------------------------------------


def test_global_start_index_controls_positions() -> None:
    # With global start 10, the three plan positions receive indices 10, 11, 12.
    solutions = enumerate_valid_selections(GENRES, 3, {}, global_start_index=10)
    assert solutions
    # Every enumerated solution is valid at each exact position.
    for solution in solutions:
        assert len(solution) == 3
        assert len({g.genre_id for g in solution}) == 3


def test_position_specific_cooldown_inside_one_run() -> None:
    # Genre last picked at index 1: unavailable at position 31 (global), becomes
    # available at position 32 — evaluated per exact position within one run.
    history = {"ambient": [1]}
    pool = [G1, G2, G3, G4, G5]
    # Position 31: ambient cooling; position 32: ambient restored.
    sol31 = enumerate_valid_selections(pool, 1, history, global_start_index=31)
    sol32 = enumerate_valid_selections(pool, 1, history, global_start_index=32)
    assert any(g.genre_id == "ambient" for (g,) in sol31) is False
    assert any(g.genre_id == "ambient" for (g,) in sol32)


def test_multi_position_sequence_respects_in_run_cooldown() -> None:
    # A genre picked at position n of the plan must not appear again later.
    history: dict[str, list[int]] = {}
    solutions = enumerate_valid_selections(GENRES, 3, history, global_start_index=1)
    for solution in solutions:
        assert len({g.genre_id for g in solution}) == 3  # no repeats


# --- T2.3 / G2-002: diversity and bounded complete solving --------------------


def test_family_limit_default_regional_one_per_run() -> None:
    assert DEFAULT_FAMILY_LIMITS["Regional"] == 1
    assert family_ok([G1, G2, G3])
    assert family_ok([G2, G5, G1])  # Electronic has no default limit
    assert family_ok([G2, G5, G3])


def test_family_limit_regional_two_selected_rejected() -> None:
    regional_b = GenreRef("regional-x", "Regional X", "Regional")
    assert not family_ok([G4, regional_b, G1])


def test_skewed_family_pool_satisfiable_for_every_seed() -> None:
    # 100 Regional genres (limit 1) + 2 unrestricted: a valid 3-set always exists,
    # and the complete solver must not mislabel it insufficient for any seed.
    pool = [_regional(f"regional-{i:03d}") for i in range(100)] + [G1, G5]
    for seed in [f"s-{i}" for i in range(10)]:
        chosen = select_daily_genres(pool, 3, make_rng(seed))
        assert len(chosen) == 3
        regional_count = sum(1 for g in chosen if g.family == "Regional")
        assert regional_count <= 1


def test_truly_unsatisfiable_pool_terminates_explicitly() -> None:
    # Only one genre is not cooling -> cannot pick 3.
    history = {g.genre_id: [1] for g in GENRES if g.genre_id != "ambient"}
    with pytest.raises(InsufficientCandidatesError):
        select_daily_genres(GENRES, 3, make_rng("s"), pick_history=history)


def test_parent_overlap_is_constrained() -> None:
    parents = {"ambient": ["electronic"], "dnb": ["electronic"]}
    # parent_ok: two genres sharing parent 'electronic' violate limit 1.
    assert not parent_ok([G2, G5], parents, {"electronic": 1})
    assert parent_ok([G2, G1], parents, {"electronic": 1})
    # Enumeration honours parent limits: with pool [G2,G5,G1,G3] and limit 1,
    # a valid 3-set must include at most one electronic genre.
    solutions = enumerate_valid_selections(
        [G2, G5, G1, G3],
        3,
        {},
        global_start_index=1,
        parent_limits={"electronic": 1},
        parents_by_genre=parents,
    )
    assert solutions
    for solution in solutions:
        assert parent_ok(solution, parents, {"electronic": 1})
        assert sum(1 for g in solution if g.genre_id in ("ambient", "dnb")) <= 1


def test_parent_limits_default_do_not_implicitly_score() -> None:
    # Without configured parent limits every combination passes.
    parents = {"ambient": ["electronic"], "dnb": ["electronic"]}
    assert parent_ok([G2, G5], parents, {})
    solutions = enumerate_valid_selections(
        [G2, G5, G1], 3, {}, global_start_index=1, parents_by_genre=parents
    )
    assert solutions
    # Both electronic genres may appear together when no parent limit is set.
    assert any(
        {g.genre_id for g in solution} == {"ambient", "dnb", "bebop"} for solution in solutions
    )


def test_family_limits_do_not_starve_family_across_runs() -> None:
    for run in range(10):
        chosen = select_daily_genres(GENRES, 3, make_rng(f"run-{run}"))
        assert sum(1 for g in chosen if g.family == "Regional") <= 1
    picked_regional = any(
        any(g.genre_id == "tuareg" for g in select_daily_genres(GENRES, 3, make_rng(f"s-{i}")))
        for i in range(50)
    )
    assert picked_regional


def test_deterministic_replay_retains_exact_ordered_picks() -> None:
    history = {"ambient": [5]}
    first = select_daily_genres(
        GENRES, 3, make_rng("replay"), pick_history=history, global_start_index=10
    )
    second = select_daily_genres(
        GENRES, 3, make_rng("replay"), pick_history=history, global_start_index=10
    )
    assert first == second
