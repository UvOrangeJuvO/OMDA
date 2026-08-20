"""T2.4 Album identity, exclusion and deduplication tests (repaired G2-003):
exact album_id exclusion without nested identity, namespaced canonical
matching, ambiguous protection, Unicode-aware normalization and non-Latin
distinctness."""

from __future__ import annotations

from omda.core.album import (
    dedup_key,
    dedupe_candidates,
    filter_candidates,
    is_permanently_excluded,
    normalized_text,
)
from omda.ports.domain import AlbumCandidate, AlbumIdentity

MB1 = AlbumIdentity(
    "alb-1", canonical_id="mb-1", canonical_source="musicbrainz", identity_confidence="exact"
)
MB2 = AlbumIdentity(
    "alb-2", canonical_id="mb-2", canonical_source="musicbrainz", identity_confidence="exact"
)
DISC_1 = AlbumIdentity(
    "alb-9", canonical_id="123", canonical_source="discogs", identity_confidence="exact"
)
PLAIN = AlbumIdentity("alb-3", identity_confidence="exact")
AMBIG = AlbumIdentity("alb-9", identity_confidence="ambiguous")


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


def test_normalized_text_unicode_aware() -> None:
    # Accented Latin normalizes predictably; casefold is locale-independent.
    assert normalized_text("café") == normalized_text("cafe")
    assert normalized_text("Múm") == "mum"
    # Non-Latin scripts are preserved (combining marks kept on non-Latin bases)
    # and are deterministic and collision-free.
    assert normalized_text("スピッツ") == normalized_text("スピッツ")
    assert normalized_text("世界") == "世界"
    assert normalized_text("東京") != normalized_text("大阪")
    assert normalized_text("スピッツ") != normalized_text("スピーツ")


def test_exact_album_id_exclusion_without_nested_identity() -> None:
    # G2-003: a candidate with identity=None is still excluded by exact album_id.
    candidate = _album("alb-3", "Blue Train", "Coltrane", 1958, None)
    assert is_permanently_excluded(candidate, frozenset({PLAIN}))
    assert filter_candidates([candidate], frozenset({PLAIN})) == []


def test_canonical_same_release_different_name_is_excluded() -> None:
    candidate = _album("alb-99", "Selected Ambient Works 85-92", "Aphex Twin", 1992, MB1)
    assert is_permanently_excluded(candidate, frozenset({MB1}))


def test_canonical_namespaced_by_source() -> None:
    # G2-003: same raw canonical id under a DIFFERENT source must not match.
    other_source = AlbumIdentity(
        "alb-x", canonical_id="mb-1", canonical_source="discogs", identity_confidence="exact"
    )
    candidate = _album("alb-1", "A", "X", 2000, MB1)
    assert not is_permanently_excluded(candidate, frozenset({other_source}))
    # Same source + same id matches.
    assert is_permanently_excluded(candidate, frozenset({MB1}))


def test_canonical_without_source_never_matches_destructively() -> None:
    # Missing source on either side makes the namespace unprovable -> no match
    # (album_ids differ so only the canonical dimension is exercised).
    no_source = AlbumIdentity("alb-9", canonical_id="mb-1", identity_confidence="exact")
    candidate = _album("alb-99", "A", "X", 2000, MB1)
    assert not is_permanently_excluded(candidate, frozenset({no_source}))


def test_ambiguous_candidate_never_destructively_matched() -> None:
    # Ambiguity protects canonical matching; album_ids differ so only the
    # canonical dimension is exercised.
    ambiguous_candidate = _album("alb-5", "Untitled", "Someone", 2020, AMBIG)
    assert not is_permanently_excluded(ambiguous_candidate, frozenset({DISC_1}))


def test_ambiguous_exclusion_never_permanently_blocks() -> None:
    candidate = _album("alb-9", "Untitled", "Someone", 2020, PLAIN)
    assert not is_permanently_excluded(candidate, frozenset({AMBIG}))


def test_different_release_not_merged_by_name() -> None:
    candidate = _album("alb-5", "Giant Steps", "Coltrane", 1960, MB2)
    assert not is_permanently_excluded(candidate, frozenset({MB1}))


def test_filter_candidates_removes_excluded_only() -> None:
    candidates = [
        _album("alb-1", "A", "X", 2000, MB1),
        _album("alb-2", "B", "Y", 2001, MB2),
        _album("alb-3", "C", "Z", 2002, PLAIN),
    ]
    result = filter_candidates(candidates, frozenset({MB1}))
    assert [c.album_id for c in result] == ["alb-2", "alb-3"]
    assert len(candidates) == 3  # input untouched


def test_dedup_key_namespaced_canonical() -> None:
    c1 = _album("alb-a", "Name A", "Artist", 2020, MB1)
    c2 = _album("alb-b", "Name B", "Artist", 2020, MB1)
    assert dedup_key(c1) == dedup_key(c2)
    # Different source, same raw id -> distinct keys.
    c3 = _album("alb-c", "Name C", "Artist", 2020, DISC_1)
    assert dedup_key(c1) != dedup_key(c3)


def test_dedup_key_same_name_different_year_not_merged() -> None:
    c1 = _album("alb-a", "Eponymous", "Band", 1990, None)
    c2 = _album("alb-b", "Eponymous", "Band", 1999, None)
    assert dedup_key(c1) != dedup_key(c2)


def test_dedup_key_non_latin_distinct() -> None:
    a = _album("alb-a", "東京", "アーティスト", 2020, None)
    b = _album("alb-b", "大阪", "アーティスト", 2020, None)
    assert dedup_key(a) != dedup_key(b)


def test_dedupe_within_run_across_genres() -> None:
    c1 = _album("alb-a", "Name A", "Artist", 2020, MB1)
    c2 = _album("alb-b", "Name B", "Artist", 2020, MB1)
    assert len(dedupe_candidates([c1, c2])) == 1


def test_multi_run_permanent_exclusion() -> None:
    # After a successful run, the same album offered in a later run is excluded
    # by exact album_id even when the later candidate carries no nested identity.
    later = _album("alb-3", "Blue Train (Reissue)", "Coltrane", 1958, None)
    exclusions = frozenset({PLAIN})
    assert is_permanently_excluded(later, exclusions)
    assert filter_candidates([later], exclusions) == []
