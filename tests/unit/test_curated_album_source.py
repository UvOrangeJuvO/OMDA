"""G3-007 CuratedAlbumSource over curated album packages (ADR-0002 D1/D2/D6).

Failure tests first: package parsing, batch building, demo marking, limits,
release-type filtering, directory/source binding and path safety."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from omda.adapters.curated import CuratedAlbumSource
from omda.ports.domain import AlbumCandidate, GenreRef
from omda.ports.errors import InvalidInputError
from omda.ports.source import CandidateBatch, verify_batch_integrity

GENRE = GenreRef(genre_id="ambient", name="Ambient", family="Electronic", eligible=True)

ALBUM_META = {
    "source_id": "curated-omda",
    "kind": "album",
    "display_name": "OMDA Curated Albums",
    "license": "CC0-1.0 (curated facts)",
    "origin_url": "https://example.org/albums",
    "retrieved_at": "2026-08-22T00:00:00+00:00",
    "dataset_version": "2026-08-22",
    "schema_version": "1",
    "data_scope": "curated album candidates",
    "records_file": "albums.jsonl",
    "demo": False,
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
            # Quote string values so numeric-looking strings (e.g. schema_version)
            # are NOT coerced to int by the flat-YAML parser.
            lines.append(f"{k}: \"{v}\"")
    (pkg / "source.yaml").write_text("\n".join(lines) + "\n", encoding="utf-8")
    if records is None:
        records = [
            {
                "album_id": "curated-omda-ambient-0001",
                "title": "Ambient 1: Music for Airports",
                "artist": "Brian Eno",
                "year": 1978,
                "release_type": "album",
                "source": source_id,
            },
            {
                "album_id": "curated-omda-ambient-0002",
                "title": "Selected Ambient Works 85-92",
                "artist": "Aphex Twin",
                "year": 1992,
                "release_type": "album",
                "source": source_id,
            },
        ]
    body = "\n".join(json.dumps(r, ensure_ascii=False) for r in records)
    (pkg / "albums.jsonl").write_text(body + "\n", encoding="utf-8")
    return pkg


def test_curated_source_builds_valid_digest_bound_batch(tmp_path: Path) -> None:
    source = CuratedAlbumSource(_write_package(tmp_path))
    batch = source.batch_for_genre(GENRE)
    assert isinstance(batch, CandidateBatch)
    assert batch.source.source_id == "curated-omda"
    assert batch.source.demo is False
    assert len(batch.candidates) == 2
    verify_batch_integrity(batch)  # digest is self-consistent


def test_candidates_for_genre_returns_domain_values_with_mbid_identity(tmp_path: Path) -> None:
    source = CuratedAlbumSource(_write_package(tmp_path))
    candidates = source.candidates_for_genre(GENRE, limit=1)
    assert len(candidates) == 1
    candidate = candidates[0]
    assert isinstance(candidate, AlbumCandidate)
    assert candidate.album_id == "curated-omda-ambient-0001"
    assert candidate.artist == "Brian Eno"
    assert candidate.year == 1978
    # An empty mbid stays None (enricher fills it later); a present mbid becomes
    # canonical identity.
    assert candidate.identity is None


def test_mbid_becomes_canonical_identity(tmp_path: Path) -> None:
    records = [
        {
            "album_id": "curated-omda-ambient-0001",
            "title": "Ambient 1: Music for Airports",
            "artist": "Brian Eno",
            "year": 1978,
            "mbid": "00000000-0000-0000-0000-000000000001",
            "release_type": "album",
            "source": "curated-omda",
        }
    ]
    source = CuratedAlbumSource(_write_package(tmp_path, records=records))
    candidate = source.candidates_for_genre(GENRE)[0]
    assert candidate.identity is not None
    assert candidate.identity.canonical_id == "00000000-0000-0000-0000-000000000001"
    assert candidate.identity.canonical_source == "musicbrainz"
    assert candidate.identity.identity_confidence == "exact"


def test_demo_package_is_marked_not_mislabeled(tmp_path: Path) -> None:
    pkg = _write_package(
        tmp_path,
        source_id="demo-curated",
        meta_overrides={"demo": True, "source_id": "demo-curated"},
    )
    # The package must be a distinct source_id; demo flag is exposed for the
    # delivery gate, never silently relabelled as production.
    source = CuratedAlbumSource(pkg)
    batch = source.batch_for_genre(GENRE)
    assert batch.source.demo is True


def test_non_album_release_type_is_rejected(tmp_path: Path) -> None:
    records = [
        {
            "album_id": "curated-omda-ambient-0001",
            "title": "Some Single",
            "artist": "Artist",
            "year": 2020,
            "release_type": "single",  # ADR-0002 D3: only primary-type Album
            "source": "curated-omda",
        }
    ]
    with pytest.raises(InvalidInputError):
        CuratedAlbumSource(_write_package(tmp_path, records=records)).batch_for_genre(GENRE)


def test_package_dir_must_match_source_id(tmp_path: Path) -> None:
    pkg = _write_package(tmp_path, source_id="curated-omda")
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
            "title": "A",
            "artist": "X",
            "year": 2000,
            "release_type": "album",
            "source": "curated-omda",
        },
        {
            "album_id": "curated-omda-ambient-0001",
            "title": "B",
            "artist": "Y",
            "year": 2001,
            "release_type": "album",
            "source": "curated-omda",
        },
    ]
    with pytest.raises(InvalidInputError):
        CuratedAlbumSource(_write_package(tmp_path, records=records)).batch_for_genre(GENRE)
