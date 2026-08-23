"""G3-007 Re-review 2 failure-first tests (G3-007-003/007/010/011)."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from omda.adapters.curated import CuratedAlbumSource, RuntimeCache
from omda.ports.domain import GenreRef
from omda.ports.errors import InvalidInputError
from omda.ports.source import (
    BATCH_SCHEMA_VERSION,
    AlbumCandidateRecord,
    CandidateBatch,
    GenreSourceDescriptor,
    assemble_validated_source_set,
    digest_batch,
    digest_genre_ids,
    digest_genre_records,
    verify_batch_integrity,
)
from omda.sources.registry import SourceRegistry

REPO = Path(__file__).resolve().parents[2]
REGISTRY = REPO / "data" / "sources" / "registry.jsonl"
GENRES = REPO / "data" / "genres" / "curated-omda"
ALBUMS = REPO / "data" / "albums" / "curated-omda"
AMBIENT = GenreRef(genre_id="ambient", name="Ambient", family="x", eligible=True)


def _registry() -> SourceRegistry:
    return SourceRegistry.load(REGISTRY)


def _ambient_batch() -> CandidateBatch:
    return CuratedAlbumSource(ALBUMS).source_batch(
        AMBIENT
    )


def _genre_descriptor() -> GenreSourceDescriptor:
    from omda.adapters.datasets import GenreDatasetAdapter

    return GenreDatasetAdapter(GENRES).descriptor()


# --- G3-007-003: eligible membership must be registry/content bound -----------


def test_forged_eligible_genre_ids_are_rejected() -> None:
    # Reviewer reproduction: appending `phantom` to a REAL registered
    # descriptor's eligible_genre_ids must fail, even with a self-consistent
    # relabelled batch and recomputed digest.
    base = _genre_descriptor()
    descriptor = replace(base, eligible_genre_ids=base.eligible_genre_ids + ("phantom",))
    registry = _registry()
    with pytest.raises(InvalidInputError):
        assemble_validated_source_set(
            registry,
            genre_descriptors=(descriptor,),
            batches=(_ambient_batch(),),
            selected_genre_ids=("phantom",),
        )
    # Even forging the eligible digest does not help: the registry binds the
    # reviewed value, so a self-computed digest fails registry verification.
    forged = replace(descriptor, eligible_digest=digest_genre_ids(descriptor.eligible_genre_ids))
    with pytest.raises(InvalidInputError):
        assemble_validated_source_set(
            registry,
            genre_descriptors=(forged,),
            batches=(_ambient_batch(),),
            selected_genre_ids=("phantom",),
        )


def test_genuine_descriptor_still_validates() -> None:
    registry = _registry()
    result = assemble_validated_source_set(
        registry,
        genre_descriptors=(_genre_descriptor(),),
        batches=(_ambient_batch(),),
        selected_genre_ids=("ambient",),
    )
    assert result.is_demo is False


# --- G3-007-007: deserialization must pass the tracked schema -----------------


def _cache_with(payload: dict, tmp_path: Path) -> RuntimeCache:
    cache = RuntimeCache(tmp_path / "cache")
    # Emulate a corrupted cache entry with the exact key the adapter uses.
    from omda.adapters.curated import CuratedAlbumSource

    probe = CuratedAlbumSource(ALBUMS)
    probe.source_batch(AMBIENT)  # warm nothing; the key is deterministic
    key = probe._cache_key(AMBIENT)
    cache.put(key, {"value": payload})
    return cache


def _valid_payload() -> dict:
    from omda.adapters.curated import CuratedAlbumSource

    probe = CuratedAlbumSource(ALBUMS)
    return probe._batch_to_json(probe.source_batch(AMBIENT))


def test_cache_hit_rejects_unknown_top_level_field(tmp_path: Path) -> None:
    payload = _valid_payload()
    payload["evil"] = True
    cache = _cache_with({"digest": payload["digest"]} | payload, tmp_path)
    source = CuratedAlbumSource(ALBUMS, cache=cache)
    batch = source.source_batch(AMBIENT)
    assert batch.schema_version == BATCH_SCHEMA_VERSION  # rebuilt, not the unknown-field entry
    assert "evil" not in source._batch_to_json(batch)


def test_cache_hit_rejects_unsupported_schema_version(tmp_path: Path) -> None:
    payload = _valid_payload()
    payload["schema_version"] = "999"
    cache = _cache_with(payload, tmp_path)
    source = CuratedAlbumSource(ALBUMS, cache=cache)
    batch = source.source_batch(AMBIENT)
    assert batch.schema_version == BATCH_SCHEMA_VERSION  # typed miss -> rebuilt at v2


def test_cache_hit_rejects_malformed_nested_source(tmp_path: Path) -> None:
    payload = _valid_payload()
    del payload["source"]["origin_url"]
    cache = _cache_with(payload, tmp_path)
    source = CuratedAlbumSource(ALBUMS, cache=cache)
    batch = source.source_batch(AMBIENT)
    assert batch.source.origin_url  # rebuilt from the package


def test_cache_hit_rejects_malformed_candidates(tmp_path: Path) -> None:
    payload = _valid_payload()
    payload["candidates"][0]["title"] = ""
    cache = _cache_with(payload, tmp_path)
    source = CuratedAlbumSource(ALBUMS, cache=cache)
    batch = source.source_batch(AMBIENT)
    assert all(c.title for c in batch.candidates)


def test_verify_rejects_unsupported_schema_version() -> None:
    batch = replace(_ambient_batch(), schema_version="999")
    with pytest.raises(InvalidInputError):
        verify_batch_integrity(batch)


# --- G3-007-010: unambiguous canonical digest encoding ------------------------


def _record(title: str, artist: str) -> AlbumCandidateRecord:
    return AlbumCandidateRecord(
        album_id="x-1", genre_id="ambient", title=title, artist=artist, year=2000,
        mbid="00000000-0000-0000-0000-000000000001",
    )


def test_digest_batch_collision_for_separator_in_free_text() -> None:
    # (title="A|B", artist="C") and (title="A", artist="B|C") must NEVER share
    # a digest — the encoding is unambiguous for every allowed text value.
    a = digest_batch(replace(_ambient_batch(), candidates=(_record("A|B", "C"),)))
    b = digest_batch(replace(_ambient_batch(), candidates=(_record("A", "B|C"),)))
    assert a != b
    # Same for other separator-ish characters.
    c = digest_batch(replace(_ambient_batch(), candidates=(_record("A\x1fB", "C"),)))
    d = digest_batch(replace(_ambient_batch(), candidates=(_record("A", "B\x1fC"),)))
    assert c != d


def test_digest_genre_records_collision_for_separator_in_free_text() -> None:
    def genre_digest(name: str, family: str) -> str:
        return digest_genre_records(
            (( "g1", name, family, "", "true", "https://e.org/g1", "curated-omda"),)
        )

    assert genre_digest("A|B", "C") != genre_digest("A", "B|C")
    assert genre_digest("A\x1fB", "C") != genre_digest("A", "B\x1fC")


# --- G3-007-011: CandidateBatch source.kind must be album ---------------------


def test_genre_kind_batch_is_rejected_by_domain_and_assembly() -> None:
    batch = replace(_ambient_batch(), source=_genre_descriptor())
    batch = replace(batch, digest=digest_batch(batch))
    # Domain integrity rejects a Genre source on an Album batch.
    with pytest.raises(InvalidInputError):
        verify_batch_integrity(batch)
    # Assembly rejects it before registry lookup.
    with pytest.raises(InvalidInputError):
        assemble_validated_source_set(
            _registry(),
            genre_descriptors=(_genre_descriptor(),),
            batches=(batch,),
            selected_genre_ids=("ambient",),
        )


def test_schema_rejects_genre_kind_source() -> None:
    payload = _valid_payload()
    payload["source"]["kind"] = "genre"
    from omda.adapters.curated import _validate_record

    with pytest.raises(InvalidInputError):
        _validate_record("candidate_batch", payload, "<candidate_batch>")
