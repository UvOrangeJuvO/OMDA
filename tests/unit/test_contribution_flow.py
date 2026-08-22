"""G3-007 curated import/export contribution workflow (ADR-0002 §8.6 / D2).

A normal recommendation run never writes tracked data. The ONLY path that
creates a reviewable Git package is an EXPLICIT export/import contribution
workflow: export validates + materializes the package (to an explicit target),
import re-validates schema + registry before anything consumes it; human review
and an explicit commit are what promote a package into tracked data."""

from __future__ import annotations

from pathlib import Path

import pytest

from omda.adapters.contribution import export_curated_package, import_curated_package
from omda.adapters.curated import CuratedAlbumSource
from omda.ports.errors import InvalidInputError
from omda.ports.source import (
    AlbumCandidateRecord,
    CandidateBatch,
    SourceDescriptor,
    digest_batch,
)
from omda.sources.registry import RegistryEntry, SourceRegistry

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


def _batch() -> CandidateBatch:
    source = SourceDescriptor(**ALBUM_META)
    records = (
        AlbumCandidateRecord(
            album_id="curated-omda-ambient-0001",
            title="Ambient 1: Music for Airports",
            artist="Brian Eno",
            year=1978,
        ),
        AlbumCandidateRecord(
            album_id="curated-omda-ambient-0002",
            title="Selected Ambient Works 85-92",
            artist="Aphex Twin",
            year=1992,
        ),
    )
    batch = CandidateBatch(
        schema_version="1", query_policy_version="1", source=source, digest="", candidates=records
    )
    from dataclasses import replace

    return replace(batch, digest=digest_batch(batch))


def _registry() -> SourceRegistry:
    return SourceRegistry(
        {
            "curated-omda:album": RegistryEntry(
                source_id="curated-omda", kind="album",
                origin_url=ALBUM_META["origin_url"], license=ALBUM_META["license"],
                schema_version="1", demo=False, records_file="albums.jsonl",
            )
        }
    )


def test_export_writes_package_only_to_explicit_target(tmp_path: Path) -> None:
    target = tmp_path / "var" / "export" / "curated-omda"
    exported = export_curated_package(_batch(), target_dir=target)
    assert (exported / "source.yaml").exists()
    assert (exported / "albums.jsonl").exists()
    # The exported package round-trips through the adapter with the same digest.
    source = CuratedAlbumSource(exported)
    batch = source.batch_for_genre(_genre())
    assert batch.digest == _batch().digest
    # Nothing was written outside the explicit target.
    assert (tmp_path / "data").exists() is False


def test_export_requires_review_for_demo_packages(tmp_path: Path) -> None:
    demo = _batch()
    demo = demo.__class__(
        schema_version=demo.schema_version,
        query_policy_version=demo.query_policy_version,
        source=SourceDescriptor(**{**ALBUM_META, "demo": True}),
        digest="",
        candidates=demo.candidates,
    )
    from dataclasses import replace

    demo = replace(demo, digest=digest_batch(demo))
    with pytest.raises(InvalidInputError):
        export_curated_package(demo, target_dir=tmp_path / "out")  # review required


def test_import_validates_schema_and_registry(tmp_path: Path) -> None:
    exported = export_curated_package(_batch(), target_dir=tmp_path / "curated-omda")
    descriptor, records = import_curated_package(exported, _registry())
    assert descriptor.source_id == "curated-omda"
    assert descriptor.demo is False
    assert len(records) == 2


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


def _genre():
    from omda.ports.domain import GenreRef

    return GenreRef(genre_id="ambient", name="Ambient", family="Electronic", eligible=True)
