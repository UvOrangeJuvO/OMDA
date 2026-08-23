"""G3-007 curated import/export contribution workflow (ADR-0002 §8.6 / D2).

A normal recommendation run never writes tracked data. The ONLY path that
creates a reviewable Git package is an EXPLICIT export/import contribution
workflow: export validates + materializes the package (to an explicit target),
import re-validates schema + registry before anything consumes it; human review
and an explicit commit are what promote a package into tracked data."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from omda.adapters.contribution import export_curated_package, import_curated_package
from omda.adapters.curated import CuratedAlbumSource
from omda.ports.domain import GenreRef
from omda.ports.errors import InvalidInputError
from omda.ports.source import (
    AlbumCandidateRecord,
    CandidateBatch,
    SourceDescriptor,
    digest_batch,
)
from omda.sources.registry import RegistryEntry, SourceRegistry

_MBID1 = "11111111-1111-1111-1111-111111111111"
_MBID2 = "22222222-2222-2222-2222-222222222222"

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


def _batch(*, demo: bool = False) -> CandidateBatch:
    source = SourceDescriptor(**{**ALBUM_META, "demo": demo})
    records = (
        AlbumCandidateRecord(
            album_id="curated-omda-ambient-0001",
            genre_id="ambient",
            title="Ambient 1: Music for Airports",
            artist="Brian Eno",
            year=1978,
            mbid=_MBID1,
        ),
        AlbumCandidateRecord(
            album_id="curated-omda-ambient-0002",
            genre_id="ambient",
            title="Selected Ambient Works 85-92",
            artist="Aphex Twin",
            year=1992,
            mbid=_MBID2,
        ),
    )
    batch = CandidateBatch(
        schema_version="2",
        query_policy_version=ALBUM_META["schema_version"],
        genre_id="ambient",
        source=source,
        digest="",
        candidates=records,
    )
    return replace(batch, digest=digest_batch(batch))


def _registry() -> SourceRegistry:
    return SourceRegistry(
        {
            "curated-omda:album": RegistryEntry(
                source_id="curated-omda", kind="album",
                display_name=ALBUM_META["display_name"],
                origin_url=ALBUM_META["origin_url"], license=ALBUM_META["license"],
                retrieved_at=ALBUM_META["retrieved_at"],
                dataset_version=ALBUM_META["dataset_version"],
                schema_version="2", data_scope=ALBUM_META["data_scope"],
                demo=False, records_file="albums.jsonl",
                data_derivation="independently_curated",
                upstream_license="none incorporated",
                license_core_facts=ALBUM_META["license_core_facts"],
                license_supplementary_used=ALBUM_META["license_supplementary_used"],
                license_service_terms=ALBUM_META["license_service_terms"],
                license_derived_package=ALBUM_META["license_derived_package"],
            )
        }
    )


def _genre() -> GenreRef:
    return GenreRef(genre_id="ambient", name="Ambient", family="Electronic", eligible=True)


def test_export_writes_package_only_to_explicit_target(tmp_path: Path) -> None:
    target = tmp_path / "curated-omda"
    exported = export_curated_package(_batch(), target_dir=target)
    assert (exported / "source.yaml").exists()
    assert (exported / "albums.jsonl").exists()
    # Genre binding and MBID round-trip through the exported package.
    source = CuratedAlbumSource(exported)
    batch = source.batch_for_genre(_genre())
    assert batch.digest == _batch().digest
    assert batch.candidates[0].genre_id == "ambient"
    assert batch.candidates[0].mbid == _MBID1
    # Nothing was written outside the explicit target.
    assert (tmp_path / "data").exists() is False


def test_export_requires_review_for_demo_packages(tmp_path: Path) -> None:
    with pytest.raises(InvalidInputError):
        export_curated_package(_batch(demo=True), target_dir=tmp_path / "curated-omda")


def test_export_refuses_production_package_without_mbid(tmp_path: Path) -> None:
    # G3-007-002: a production package with a missing canonical MBID must never
    # be exported as reviewable production data.
    batch = _batch()
    missing = replace(batch.candidates[0], mbid=None)
    bad = replace(batch, candidates=(missing, batch.candidates[1]))
    bad = replace(bad, digest=digest_batch(bad))
    with pytest.raises(InvalidInputError):
        export_curated_package(bad, target_dir=tmp_path / "curated-omda")


def test_import_validates_schema_and_registry(tmp_path: Path) -> None:
    exported = export_curated_package(_batch(), target_dir=tmp_path / "curated-omda")
    descriptor, records = import_curated_package(exported, _registry())
    assert descriptor.source_id == "curated-omda"
    assert descriptor.demo is False
    assert len(records) == 2
    assert records[0].mbid == _MBID1


def test_import_rejects_unregistered_or_mismatched_package(tmp_path: Path) -> None:
    exported = export_curated_package(_batch(), target_dir=tmp_path / "curated-omda")
    with pytest.raises(InvalidInputError):
        import_curated_package(exported, SourceRegistry({}))  # not registered
    # A tampered origin in the exported source.yaml fails registry verification.
    meta = (exported / "source.yaml").read_text(encoding="utf-8").replace(
        "https://example.org/albums", "https://evil.example"
    )
    (exported / "source.yaml").write_text(meta, encoding="utf-8")
    with pytest.raises(InvalidInputError):
        import_curated_package(exported, _registry())
