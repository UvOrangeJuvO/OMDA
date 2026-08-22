"""G3-007 source contracts: descriptors, CandidateBatch, digest, registry,
ValidatedSourceSet (ADR-0002 D2/D6, §8.4/§8.5/§8.6). Failure tests first."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from omda.ports.errors import InvalidInputError
from omda.ports.source import (
    AlbumCandidateRecord,
    CandidateBatch,
    GenreSourceDescriptor,
    SourceDescriptor,
    ValidatedSourceSet,
    assemble_validated_source_set,
    digest_batch,
    verify_batch_integrity,
)
from omda.sources.registry import RegistryEntry, SourceRegistry

GENRE_META = dict(
    source_id="curated-omda",
    kind="genre",
    display_name="OMDA Curated Genres",
    license="CC0-1.0 (curated facts)",
    origin_url="https://example.org/genres",
    retrieved_at="2026-08-22T00:00:00+00:00",
    dataset_version="2026-08-22",
    schema_version="1",
    data_scope="curated genre list",
    records_file="genres.jsonl",
    demo=False,
)
ALBUM_META = dict(
    source_id="curated-omda",
    kind="album",
    display_name="OMDA Curated Albums",
    license="CC0-1.0 (curated facts)",
    origin_url="https://example.org/albums",
    retrieved_at="2026-08-22T00:00:00+00:00",
    dataset_version="2026-08-22",
    schema_version="1",
    data_scope="curated album candidates",
    records_file="albums.jsonl",
    demo=False,
)


def _genre_descriptor(**overrides) -> GenreSourceDescriptor:
    return GenreSourceDescriptor(**({**GENRE_META, **overrides}))


def _album_descriptor(**overrides) -> SourceDescriptor:
    return SourceDescriptor(**({**ALBUM_META, **overrides}))


def _records() -> tuple[AlbumCandidateRecord, ...]:
    return (
        AlbumCandidateRecord(
            album_id="curated-omda-ambient-0001",
            title="Ambient 1: Music for Airports",
            artist="Brian Eno",
            year=1978,
            mbid=None,
        ),
        AlbumCandidateRecord(
            album_id="curated-omda-ambient-0002",
            title="Selected Ambient Works 85-92",
            artist="Aphex Twin",
            year=1992,
            mbid=None,
        ),
    )


def _batch(**overrides) -> CandidateBatch:
    base = dict(
        schema_version="1",
        query_policy_version="1",
        source=_album_descriptor(),
        digest="",  # filled below unless overridden
        candidates=_records(),
    )
    base.update(overrides)
    batch = CandidateBatch(**base)
    if "digest" not in overrides:
        batch = replace(batch, digest=digest_batch(batch))
    return batch


def _entry(**overrides) -> RegistryEntry:
    base = dict(
        source_id="curated-omda",
        kind="album",
        origin_url=ALBUM_META["origin_url"],
        license=ALBUM_META["license"],
        schema_version="1",
        demo=False,
        records_file="albums.jsonl",
    )
    base.update(overrides)
    return RegistryEntry(**base)


def test_batch_digest_is_stable_and_content_sensitive() -> None:
    first = _batch()
    second = _batch()
    d1 = digest_batch(first)
    assert d1 == digest_batch(second)  # deterministic
    assert len(d1) == 64  # SHA-256 hex
    # Any content change (a candidate title) changes the digest.
    altered = _batch(
        candidates=(
            AlbumCandidateRecord(
                album_id="curated-omda-ambient-0001",
                title="Ambient 1: Music for Airports (tampered)",
                artist="Brian Eno",
                year=1978,
                mbid=None,
            ),
            _records()[1],
        )
    )
    assert digest_batch(altered) != d1
    # The declared source license/origin are part of the digest envelope.
    assert digest_batch(_batch(source=_album_descriptor(license="MIT"))) != d1


def test_verify_batch_integrity_rejects_tampered_digest() -> None:
    batch = _batch(digest=digest_batch(_batch()))
    verify_batch_integrity(batch)  # ok
    with pytest.raises(InvalidInputError):
        verify_batch_integrity(_batch(digest="f" * 64))
    with pytest.raises(InvalidInputError):
        verify_batch_integrity(_batch(digest=digest_batch(_batch())[:-1] + "0"))


def test_registry_load_and_lookup() -> None:
    registry = SourceRegistry({"curated-omda:album": _entry()})
    entry = registry.get("curated-omda", "album")
    assert entry.source_id == "curated-omda"
    assert registry.demo_policy("curated-omda", "album") is False
    with pytest.raises(InvalidInputError):
        registry.get("missing", "album")


def test_registry_verify_descriptor_mismatch_fails_closed() -> None:
    registry = SourceRegistry({"curated-omda:album": _entry()})
    # Every field must match the reviewed registry entry.
    registry.verify_descriptor(_album_descriptor())
    with pytest.raises(InvalidInputError):
        registry.verify_descriptor(_album_descriptor(origin_url="https://evil.example"))
    with pytest.raises(InvalidInputError):
        registry.verify_descriptor(_album_descriptor(license="MIT"))
    with pytest.raises(InvalidInputError):
        registry.verify_descriptor(_album_descriptor(demo=True))
    with pytest.raises(InvalidInputError):
        registry.verify_descriptor(_album_descriptor(schema_version="999"))


def test_assemble_validated_source_set() -> None:
    registry = SourceRegistry(
        {
            "curated-omda:genre": RegistryEntry(
                source_id="curated-omda", kind="genre",
                origin_url=GENRE_META["origin_url"], license=GENRE_META["license"],
                schema_version="1", demo=False, records_file="genres.jsonl",
            ),
            "curated-omda:album": _entry(),
        }
    )
    batch = _batch(digest=digest_batch(_batch()))
    result = assemble_validated_source_set(
        registry,
        genre_descriptors=(_genre_descriptor(),),
        batches=(batch,),
    )
    assert isinstance(result, ValidatedSourceSet)
    assert result.genre_descriptors[0].source_id == "curated-omda"
    assert result.batches[0].digest == batch.digest
    assert result.is_demo is False


def test_assemble_rejects_tampered_batch_or_forged_production_label() -> None:
    registry = SourceRegistry({"curated-omda:album": _entry()})
    # Tampered digest fails before any consumer sees the batch.
    with pytest.raises(InvalidInputError):
        assemble_validated_source_set(
            registry, genre_descriptors=(), batches=(_batch(digest="0" * 64),)
        )
    # A package that falsely claims production (demo=False) while the reviewed
    # registry says it is demo fails closed — a self-asserted label is not
    # provenance (ADR-0002 §8.5).
    demo_registry = SourceRegistry({"curated-omda:album": _entry(demo=True)})
    with pytest.raises(InvalidInputError):
        assemble_validated_source_set(
            demo_registry,
            genre_descriptors=(),
            batches=(_batch(digest=digest_batch(_batch())),),
        )
    # Unregistered source is rejected outright.
    with pytest.raises(InvalidInputError):
        assemble_validated_source_set(
            SourceRegistry({}),
            genre_descriptors=(),
            batches=(_batch(digest=digest_batch(_batch())),),
        )


def test_demo_batch_is_exposed_but_never_mislabeled(tmp_path: Path) -> None:
    demo_entry = _entry(demo=True)
    registry = SourceRegistry({"curated-omda:album": demo_entry})
    demo_descriptor = _album_descriptor(demo=True)
    batch = _batch(source=demo_descriptor, digest=digest_batch(_batch(source=demo_descriptor)))
    result = assemble_validated_source_set(registry, genre_descriptors=(), batches=(batch,))
    assert result.is_demo is True  # exposed for the delivery gate to reject
