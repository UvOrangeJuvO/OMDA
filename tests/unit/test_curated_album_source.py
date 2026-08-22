"""G3-007 CuratedAlbumSource over curated album packages (ADR-0002 D1/D2/D6).

Failure tests first: package parsing, Genre binding (G3-007-001), canonical MBID
requirements (G3-007-002), batch building, demo marking, limits, release-type
filtering, directory/source binding and path safety."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from omda.adapters.curated import CuratedAlbumSource
from omda.ports.domain import AlbumCandidate, GenreRef
from omda.ports.errors import InvalidInputError

GENRE = GenreRef(genre_id="ambient", name="Ambient", family="Electronic", eligible=True)
BEBOP = GenreRef(genre_id="bebop", name="Bebop", family="Jazz", eligible=True)
_MBID = "00000000-0000-0000-0000-000000000001"
_MBID2 = "00000000-0000-0000-0000-000000000002"

ALBUM_META = {
    "source_id": "curated-omda",
    "kind": "album",
    "display_name": "OMDA Curated Albums",
    "license": "CC0-1.0 (independently curated factual metadata only)",
    "origin_url": "https://example.org/albums",
    "retrieved_at": "2026-08-22T00:00:00+00:00",
    "dataset_version": "2026-08-22",
    "schema_version": "2",
    "data_scope": "curated album candidates",
    "records_file": "albums.jsonl",
    "demo": False,
    "data_derivation": "independently_curated",
    "upstream_license": "none incorporated",
    "license_core_facts": "CC0-1.0",
    "license_supplementary_used": "none",
    "license_service_terms": "n/a",
    "license_derived_package": "CC0-1.0",
}


def _write_package(
    tmp_path: Path,
    *,
    source_id: str = "curated-omda",
    records: list[dict] | None = None,
    meta_overrides: dict | None = None,
) -> Path:
    pkg = tmp_path / source_id
    pkg.mkdir(parents=True, exist_ok=True)
    meta = dict(ALBUM_META)
    if meta_overrides:
        meta.update(meta_overrides)
    lines = []
    for k, v in meta.items():
        if isinstance(v, bool):
            lines.append(f"{k}: {'true' if v else 'false'}")
        else:
            lines.append(f"{k}: \"{v}\"")
    (pkg / "source.yaml").write_text("\n".join(lines) + "\n", encoding="utf-8")
    if records is None:
        records = [
            {
                "album_id": "curated-omda-ambient-0001",
                "genre_id": "ambient",
                "title": "Ambient 1: Music for Airports",
                "artist": "Brian Eno",
                "year": 1978,
                "mbid": _MBID,
                "release_type": "album",
                "source": source_id,
            },
            {
                "album_id": "curated-omda-ambient-0002",
                "genre_id": "ambient",
                "title": "Selected Ambient Works 85-92",
                "artist": "Aphex Twin",
                "year": 1992,
                "mbid": _MBID2,
                "release_type": "album",
                "source": source_id,
            },
        ]
    body = "\n".join(json.dumps(r, ensure_ascii=False) for r in records)
    (pkg / "albums.jsonl").write_text(body + "\n", encoding="utf-8")
    return pkg


def test_batch_is_filtered_to_the_requested_genre_only(tmp_path: Path) -> None:
    # G3-007-001: records of OTHER Genres can never enter the requested batch.
    records = [
        {
            "album_id": "curated-omda-ambient-0001",
            "genre_id": "ambient",
            "title": "Ambient 1: Music for Airports",
            "artist": "Brian Eno",
            "year": 1978,
            "mbid": _MBID,
            "release_type": "album",
            "source": "curated-omda",
        },
        {
            "album_id": "curated-omda-bebop-0001",
            "genre_id": "bebop",
            "title": "Brilliant Corners",
            "artist": "Thelonious Monk",
            "year": 1957,
            "mbid": _MBID2,
            "release_type": "album",
            "source": "curated-omda",
        },
    ]
    source = CuratedAlbumSource(_write_package(tmp_path, records=records))
    ambient = source.batch_for_genre(GENRE)
    assert [r.album_id for r in ambient.candidates] == ["curated-omda-ambient-0001"]
    assert all(r.genre_id == "ambient" for r in ambient.candidates)
    bebop = source.batch_for_genre(BEBOP)
    assert [r.album_id for r in bebop.candidates] == ["curated-omda-bebop-0001"]


def test_unknown_genre_coverage_fails_clearly(tmp_path: Path) -> None:
    # G3-007-001: an unknown/empty Genre must fail, never served another
    # Genre's records.
    source = CuratedAlbumSource(_write_package(tmp_path))
    with pytest.raises(InvalidInputError):
        source.batch_for_genre(BEBOP)


def test_candidates_carry_reviewed_genre_membership(tmp_path: Path) -> None:
    source = CuratedAlbumSource(_write_package(tmp_path))
    candidates = source.candidates_for_genre(GENRE, limit=1)
    assert len(candidates) == 1
    candidate = candidates[0]
    assert isinstance(candidate, AlbumCandidate)
    assert candidate.genres == ("ambient",)  # the REVIEWED membership, not relabelled
    assert candidate.artist == "Brian Eno"
    assert candidate.year == 1978


def test_mbid_becomes_canonical_identity(tmp_path: Path) -> None:
    source = CuratedAlbumSource(_write_package(tmp_path))
    candidate = source.candidates_for_genre(GENRE)[0]
    assert candidate.identity is not None
    assert candidate.identity.canonical_id == _MBID
    assert candidate.identity.canonical_source == "musicbrainz"
    assert candidate.identity.identity_confidence == "exact"


def test_production_record_without_mbid_is_rejected(tmp_path: Path) -> None:
    # G3-007-002: production packages MUST carry verified canonical MBIDs.
    records = [
        {
            "album_id": "curated-omda-ambient-0001",
            "genre_id": "ambient",
            "title": "Some Album",
            "artist": "Some Artist",
            "year": 2000,
            "release_type": "album",
            "source": "curated-omda",
        }
    ]
    with pytest.raises(InvalidInputError):
        CuratedAlbumSource(_write_package(tmp_path, records=records)).batch_for_genre(GENRE)


def test_duplicate_canonical_mbid_is_rejected(tmp_path: Path) -> None:
    # G3-007-002: a stable identity must be unique within the package.
    records = [
        {
            "album_id": "curated-omda-ambient-0001",
            "genre_id": "ambient",
            "title": "A",
            "artist": "X",
            "year": 2000,
            "mbid": _MBID,
            "release_type": "album",
            "source": "curated-omda",
        },
        {
            "album_id": "curated-omda-ambient-0002",
            "genre_id": "ambient",
            "title": "B",
            "artist": "Y",
            "year": 2001,
            "mbid": _MBID,
            "release_type": "album",
            "source": "curated-omda",
        },
    ]
    with pytest.raises(InvalidInputError):
        CuratedAlbumSource(_write_package(tmp_path, records=records)).batch_for_genre(GENRE)


def test_demo_package_may_omit_mbid(tmp_path: Path) -> None:
    # Demo/legacy fixtures are the only place MBIDs may be absent.
    pkg = _write_package(
        tmp_path,
        source_id="demo-curated",
        meta_overrides={"demo": True, "source_id": "demo-curated"},
        records=[
            {
                "album_id": "demo-curated-ambient-0001",
                "genre_id": "ambient",
                "title": "Demo Album",
                "artist": "Demo Artist",
                "year": 2000,
                "release_type": "album",
                "source": "demo-curated",
            }
        ],
    )
    batch = CuratedAlbumSource(pkg).batch_for_genre(GENRE)
    assert batch.source.demo is True
    assert batch.candidates[0].mbid is None


def test_non_album_release_type_is_rejected(tmp_path: Path) -> None:
    records = [
        {
            "album_id": "curated-omda-ambient-0001",
            "genre_id": "ambient",
            "title": "Some Single",
            "artist": "Artist",
            "year": 2020,
            "mbid": _MBID,
            "release_type": "single",  # ADR-0002 D3: only primary-type Album
            "source": "curated-omda",
        }
    ]
    with pytest.raises(InvalidInputError):
        CuratedAlbumSource(_write_package(tmp_path, records=records)).batch_for_genre(GENRE)


def test_package_dir_must_match_source_id(tmp_path: Path) -> None:
    pkg = _write_package(tmp_path)
    forged = tmp_path / "forged-name"
    forged.mkdir()
    (forged / "source.yaml").write_text(
        (pkg / "source.yaml").read_text(encoding="utf-8"), encoding="utf-8"
    )
    (forged / "albums.jsonl").write_text(
        (pkg / "albums.jsonl").read_text(encoding="utf-8"), encoding="utf-8"
    )
    with pytest.raises(InvalidInputError):
        CuratedAlbumSource(forged).batch_for_genre(GENRE)


def test_records_file_escape_is_rejected(tmp_path: Path) -> None:
    pkg = _write_package(tmp_path, meta_overrides={"records_file": "../outside.jsonl"})
    with pytest.raises(InvalidInputError):
        CuratedAlbumSource(pkg).batch_for_genre(GENRE)


def test_missing_package_files_fail(tmp_path: Path) -> None:
    empty = tmp_path / "curated-omda"
    empty.mkdir()
    with pytest.raises(InvalidInputError):
        CuratedAlbumSource(empty).batch_for_genre(GENRE)


def test_duplicate_album_id_is_rejected(tmp_path: Path) -> None:
    records = [
        {
            "album_id": "curated-omda-ambient-0001",
            "genre_id": "ambient",
            "title": "A",
            "artist": "X",
            "year": 2000,
            "mbid": _MBID,
            "release_type": "album",
            "source": "curated-omda",
        },
        {
            "album_id": "curated-omda-ambient-0001",
            "genre_id": "ambient",
            "title": "B",
            "artist": "Y",
            "year": 2001,
            "mbid": _MBID2,
            "release_type": "album",
            "source": "curated-omda",
        },
    ]
    with pytest.raises(InvalidInputError):
        CuratedAlbumSource(_write_package(tmp_path, records=records)).batch_for_genre(GENRE)
