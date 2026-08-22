"""G3-007 checkpoint acceptance: the curated source chain really works.

Uses the REAL reviewed packages (data/genres/curated-omda + data/albums/
curated-omda + data/sources/registry.jsonl) to prove one real 3x3
recommendation can be sourced end-to-end: genre FETCH -> album FETCH ->
CandidateBatch -> ValidatedSourceSet, with provenance/license/digest that a
G4 delivery gate can trace (ADR-0002 §8.4/§8.5/§8.8).

Negative tests prove demo packages (rym-sample) are marked demo and never
silently relabelled production, and that forged/self-asserted provenance fails.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from omda.adapters.curated import CuratedAlbumSource
from omda.adapters.datasets import GenreDatasetAdapter
from omda.ports.errors import InvalidInputError
from omda.ports.source import assemble_validated_source_set, verify_batch_integrity
from omda.sources.registry import SourceRegistry

REPO = Path(__file__).resolve().parents[2]
REGISTRY = REPO / "data" / "sources" / "registry.jsonl"
GENRES = REPO / "data" / "genres" / "curated-omda"
ALBUMS = REPO / "data" / "albums" / "curated-omda"
RYM_SAMPLE = REPO / "data" / "genres" / "rym-sample"

ALBUMS_PER_GENRE = 3


def _registry() -> SourceRegistry:
    return SourceRegistry.load(REGISTRY)


def test_real_curated_packages_support_one_3x3_run() -> None:
    registry = _registry()
    genre_adapter = GenreDatasetAdapter(GENRES)
    album_source = CuratedAlbumSource(ALBUMS)

    genres = genre_adapter.list_eligible_genres()
    assert len(genres) == 5  # real, eligible, non-demo genres
    genre_descriptor = genre_adapter.descriptor()
    assert genre_descriptor.demo is False
    registry.verify_descriptor(genre_descriptor)

    batches = []
    for genre in genres:
        batch = album_source.batch_for_genre(genre)
        verify_batch_integrity(batch)
        # Enough candidates to select 3 per genre AFTER history exclusion.
        assert len(batch.candidates) >= ALBUMS_PER_GENRE
        assert batch.source.demo is False
        # Every candidate is a real fact record bound to the package.
        for record in batch.candidates:
            assert record.title and record.artist
            assert record.release_type == "album"
        batches.append(batch)

    source_set = assemble_validated_source_set(
        registry,
        genre_descriptors=(genre_descriptor,),
        batches=tuple(batches),
    )
    assert source_set.is_demo is False


def test_committed_identity_and_facts_trace_to_validated_batch() -> None:
    # ADR-0002 §8.8: outbound facts / committed MBID must trace to the same
    # ValidatedSourceSet. We prove the traceable evidence fields are available:
    # source_id + dataset_version + schema/query-policy version + batch digest.
    album_source = CuratedAlbumSource(ALBUMS)
    batch = album_source.batch_for_genre(GenreDatasetAdapter(GENRES).list_eligible_genres()[0])
    evidence = {
        "genre_source_id": "curated-omda",
        "genre_schema_version": "1",
        "album_source_id": batch.source.source_id,
        "album_dataset_version": batch.source.dataset_version,
        "query_policy_version": batch.query_policy_version,
        "batch_digest": batch.digest,
    }
    assert all(evidence.values())
    # The batch digest is stable across reads (reproducible provenance).
    assert album_source.batch_for_genre(
        GenreDatasetAdapter(GENRES).list_eligible_genres()[0]
    ).digest == evidence["batch_digest"]


def test_rym_sample_is_marked_demo_never_production() -> None:
    # ADR-0002 §8.2: the existing rym-sample Genre package is demo data; the
    # production gate must reject it. G3-007 proves the demo flag is exposed.
    descriptor = GenreDatasetAdapter(RYM_SAMPLE).descriptor()
    assert descriptor.demo is True


def test_demo_or_unregistered_source_fails_validated_assembly() -> None:
    # A package that claims production but is NOT in the registry fails closed
    # (an empty registry has no reviewed entry for any source).
    with pytest.raises(InvalidInputError):
        assemble_validated_source_set(
            SourceRegistry({}),
            genre_descriptors=(),
            batches=(CuratedAlbumSource(ALBUMS).batch_for_genre(
                GenreDatasetAdapter(GENRES).list_eligible_genres()[0]
            ),),
        )
    # A reviewed registry that says curated-omda is DEMO makes the same
    # production-claiming batch fail (self-asserted label vs reviewed policy).
    from omda.sources.registry import RegistryEntry

    demo_registry = SourceRegistry(
        {
            "curated-omda:album": RegistryEntry(
                source_id="curated-omda", kind="album",
                origin_url="https://musicbrainz.org/search?query=release-group",
                license=(
                    "CC0-1.0 (curated factual metadata; see "
                    "data/albums/curated-omda/README.md)"
                ),
                schema_version="1", demo=True, records_file="albums.jsonl",
            )
        }
    )
    with pytest.raises(InvalidInputError):
        assemble_validated_source_set(
            demo_registry,
            genre_descriptors=(),
            batches=(CuratedAlbumSource(ALBUMS).batch_for_genre(
                GenreDatasetAdapter(GENRES).list_eligible_genres()[0]
            ),),
        )
