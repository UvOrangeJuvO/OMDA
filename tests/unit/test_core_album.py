"""T2.4 Album identity, exclusion and deduplication tests."""

from __future__ import annotations

from omda.core.album import (
    dedup_key,
    dedupe_candidates,
    filter_candidates,
    is_permanently_excluded,
    normalized_text,
)
from omda.ports.domain import AlbumCandidate, AlbumIdentity

A1 = AlbumIdentity(
    "alb-1", canonical_id="mb-1", canonical_source="musicbrainz", identity_confidence="exact"
)
A2 = AlbumIdentity(
    "alb-2", canonical_id="mb-2", canonical_source="musicbrainz", identity_confidence="exact"
)
AMBIG = AlbumIdentity("alb-9", identity_confidence="ambiguous")
PLAIN = AlbumIdentity("alb-3", identity_confidence="exact")


def _album(
    album_id: str, title: str, artist: str, year: int | None, identity=None
) -> AlbumCandidate:
    return AlbumCandidate(
        album_id=album_id,
        title=title,
        artist=artist,
        year=year,
        identity=identity,
    )


def test_normalized_text_is_deterministic() -> None:
    assert normalized_text("The Cure") == normalized_text("the cure")
    assert normalized_text("Múm") == "mm"
    assert normalized_text("  spaced  out ") == "spacedout"


def test_canonical_same_release_different_name_is_excluded() -> None:
    # Different album_id/name, same canonical release-group -> permanently excluded.
    candidate = _album("alb-99", "Selected Ambient Works 85-92", "Aphex Twin", 1992, A1)
    assert is_permanently_excluded(candidate, frozenset({A1}))


def test_different_release_not_merged_by_name() -> None:
    # Same name but different release identity -> NOT excluded.
    candidate = _album("alb-5", "Giant Steps", "Coltrane", 1960, A2)
    assert not is_permanently_excluded(candidate, frozenset({A1}))


def test_ambiguous_exclusion_never_permanently_blocks() -> None:
    candidate = _album("alb-9", "Untitled", "Someone", 2020, PLAIN)
    # Ambiguous exclusion exists with same album_id; it must not permanently exclude.
    assert not is_permanently_excluded(candidate, frozenset({AMBIG}))


def test_no_canonical_uses_album_id_exact() -> None:
    candidate = _album("alb-3", "Blue Train", "Coltrane", 1958, PLAIN)
    assert is_permanently_excluded(candidate, frozenset({PLAIN}))


def test_filter_candidates_removes_excluded_only() -> None:
    candidates = [
        _album("alb-1", "A", "X", 2000, A1),
        _album("alb-2", "B", "Y", 2001, A2),
        _album("alb-3", "C", "Z", 2002, PLAIN),
    ]
    result = filter_candidates(candidates, frozenset({A1}))
    assert [c.album_id for c in result] == ["alb-2", "alb-3"]
    # Input unchanged.
    assert len(candidates) == 3


def test_dedup_key_canonical_preferred_over_name() -> None:
    c1 = _album("alb-a", "Name A", "Artist", 2020, A1)
    c2 = _album("alb-b", "Name B", "Artist", 2020, A1)  # same canonical, different name
    assert dedup_key(c1) == dedup_key(c2)


def test_dedup_key_same_name_different_year_not_merged() -> None:
    c1 = _album("alb-a", "Eponymous", "Band", 1990, None)
    c2 = _album("alb-b", "Eponymous", "Band", 1999, None)
    assert dedup_key(c1) != dedup_key(c2)


def test_dedupe_within_run_across_genres() -> None:
    # Same canonical release offered under two names must appear once.
    c1 = _album("alb-a", "Name A", "Artist", 2020, A1)
    c2 = _album("alb-b", "Name B", "Artist", 2020, A1)
    result = dedupe_candidates([c1, c2])
    assert len(result) == 1


def test_dedupe_respects_already_selected() -> None:
    selected = [_album("alb-a", "Name A", "Artist", 2020, A1)]
    candidates = [_album("alb-b", "Name B", "Artist", 2020, A1)]
    assert dedupe_candidates(candidates, already_selected=selected) == []


def test_exclusion_input_is_immutable_frozenset_semantics() -> None:
    # Caller passes a frozenset; filter must not mutate or depend on mutability.
    exclusions = frozenset({A1, A2})
    candidates = [_album("alb-1", "A", "X", 2000, A1)]
    assert filter_candidates(candidates, exclusions) == []
    assert exclusions == frozenset({A1, A2})
