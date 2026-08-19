"""T2.5 tests: rating composition (weights, missing policy, deterministic ties)
and year constraints (modern/older, degradation, shortage)."""

from __future__ import annotations

import pytest

from omda.core.rating import (
    MISSING_SKIP,
    MISSING_ZERO,
    compose_rating,
    rank_candidates,
)
from omda.core.year import is_modern, select_albums_for_genre
from omda.ports.critic import CriticRatingRow
from omda.ports.domain import AlbumCandidate
from omda.ports.errors import InsufficientCandidatesError


def _album(album_id: str, year: int | None = None, title: str | None = None) -> AlbumCandidate:
    return AlbumCandidate(
        album_id=album_id,
        title=title or album_id,
        artist="Artist",
        year=year,
    )


def _rating(
    source: str, album_id: str, value: float, maximum: float | None = 10.0
) -> CriticRatingRow:
    return CriticRatingRow(source_id=source, album_id=album_id, rating=value, rating_max=maximum)


# --- rating composition -------------------------------------------------------


def test_compose_rating_single_source_normalized() -> None:
    rows = [_rating("rym", "a", 8.0, 10.0)]
    assert compose_rating(rows, {"rym": 1.0}) == pytest.approx(0.8)


def test_compose_rating_multi_source_weighted() -> None:
    rows = [_rating("rym", "a", 8.0, 10.0), _rating("critic", "a", 6.0, 10.0)]
    # weights rym=1, critic=3 -> (0.8*1 + 0.6*3)/4 = 0.65
    assert compose_rating(rows, {"rym": 1.0, "critic": 3.0}) == pytest.approx(0.65)


def test_compose_rating_no_rows_returns_none() -> None:
    assert compose_rating([], {"rym": 1.0}) is None


def test_missing_policy_skip_ignores_missing_source() -> None:
    rows = [_rating("rym", "a", 8.0, 10.0)]
    # critic missing under "skip": weight renormalized to rym only.
    assert compose_rating(rows, {"rym": 1.0, "critic": 3.0}, MISSING_SKIP) == pytest.approx(0.8)


def test_missing_policy_zero_counts_missing_as_zero() -> None:
    rows = [_rating("rym", "a", 8.0, 10.0)]
    # critic missing under "zero": (0.8*1 + 0*3)/4 = 0.2
    assert compose_rating(rows, {"rym": 1.0, "critic": 3.0}, MISSING_ZERO) == pytest.approx(0.2)


def test_invalid_missing_policy_raises() -> None:
    with pytest.raises(ValueError):
        compose_rating([], {"rym": 1.0}, "bogus")


def test_rank_candidates_deterministic_ties() -> None:
    candidates = [
        _album("b", 2020, "Beta"),
        _album("a", 2020, "Alpha"),
    ]
    rows = {"a": [_rating("rym", "a", 8.0)], "b": [_rating("rym", "b", 8.0)]}
    first = rank_candidates(candidates, rows, {"rym": 1.0})
    second = rank_candidates(candidates, rows, {"rym": 1.0})
    assert [c.album_id for c in first] == [c.album_id for c in second] == ["a", "b"]


def test_rank_candidates_unrated_sort_last() -> None:
    candidates = [_album("unrated"), _album("rated", 2020)]
    rows = {"rated": [_rating("rym", "rated", 9.0)]}
    ranked = rank_candidates(candidates, rows, {"rym": 1.0})
    assert [c.album_id for c in ranked] == ["rated", "unrated"]


# --- year constraints ---------------------------------------------------------


def test_is_modern_year_and_unknown() -> None:
    assert is_modern(_album("a", 2010))
    assert is_modern(_album("a", 2024))
    assert not is_modern(_album("a", 2009))
    assert not is_modern(_album("a", None))


def test_select_at_least_one_modern() -> None:
    ranked = [
        _album("old1", 1995),
        _album("new1", 2015),
        _album("old2", 1990),
        _album("new2", 2018),
    ]
    chosen = select_albums_for_genre(ranked, count=3)
    assert len(chosen) == 3
    assert sum(1 for c in chosen if is_modern(c)) >= 1
    assert sum(1 for c in chosen if not is_modern(c)) <= 2


def test_select_modern_preferred_and_older_limited() -> None:
    ranked = [
        _album("old1", 1980),
        _album("old2", 1985),
        _album("old3", 1990),
        _album("new1", 2020),
    ]
    chosen = select_albums_for_genre(ranked, count=3)
    ids = {c.album_id for c in chosen}
    assert "new1" in ids  # modern always included when present
    assert sum(1 for c in chosen if not is_modern(c)) <= 2


def test_no_modern_candidates_degrades_observably() -> None:
    ranked = [_album("old1", 1980), _album("old2", 1985), _album("old3", 1990)]
    chosen = select_albums_for_genre(ranked, count=3)
    # Explicit degradation: top-3 older albums, none unrelated.
    assert [c.album_id for c in chosen] == ["old1", "old2", "old3"]
    assert all(not is_modern(c) for c in chosen)


def test_unknown_year_treated_as_older() -> None:
    ranked = [_album("unk", None), _album("old1", 1990), _album("new1", 2020)]
    chosen = select_albums_for_genre(ranked, count=3)
    assert len(chosen) == 3
    assert any(is_modern(c) for c in chosen)  # modern still included
    assert sum(1 for c in chosen if not is_modern(c)) <= 2


def test_candidate_shortage_raises_bounded() -> None:
    with pytest.raises(InsufficientCandidatesError):
        select_albums_for_genre([_album("only1", 2020)], count=3)


def test_no_unrelated_album_forced_in() -> None:
    # One modern + many older; count=3 keeps older<=2 and never adds extras beyond count.
    ranked = [
        _album("new1", 2021),
        _album("old1", 1970),
        _album("old2", 1975),
        _album("old3", 1980),
    ]
    chosen = select_albums_for_genre(ranked, count=3)
    assert len(chosen) == 3
    assert {c.album_id for c in chosen} <= {"new1", "old1", "old2", "old3"}
