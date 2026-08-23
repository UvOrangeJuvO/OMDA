"""G3-007 source contracts: descriptors, CandidateBatch, digests, registry,
ValidatedSourceSet (ADR-0002 D2/D6, §8.4/§8.5/§8.6). Failure tests first."""

from __future__ import annotations

from dataclasses import replace

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

_MBID1 = "11111111-1111-1111-1111-111111111111"
_MBID2 = "22222222-2222-2222-2222-222222222222"

BASE_FIELDS = dict(
    source_id="curated-omda",
    display_name="OMDA Curated",
    license="CC0-1.0 (independently curated factual metadata only)",
    origin_url="https://example.org/source",
    retrieved_at="2026-08-22T00:00:00+00:00",
    dataset_version="2026-08-22",
    schema_version="1",
    data_scope="curated records",
    records_file="records.jsonl",
    demo=False,
    data_derivation="independently_curated",
    upstream_license="none incorporated",
    license_core_facts="CC0-1.0",
    license_supplementary_used="none",
    license_service_terms="n/a",
    license_derived_package="CC0-1.0",
)


def _genre_descriptor(**overrides) -> GenreSourceDescriptor:
    base = {
        **BASE_FIELDS,
        "kind": "genre",
        "content_digest": "g" * 64,
        "eligible_genre_ids": ("ambient",),
    }
    base.update(overrides)
    return GenreSourceDescriptor(**base)


def _album_descriptor(**overrides) -> SourceDescriptor:
    base = {**BASE_FIELDS, "kind": "album"}
    base.update(overrides)
    return SourceDescriptor(**base)


def _records() -> tuple[AlbumCandidateRecord, ...]:
    return (
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


def _batch(**overrides) -> CandidateBatch:
    base = dict(
        schema_version="2",
        query_policy_version="1",
        genre_id="ambient",
        source=_album_descriptor(),
        digest="",
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
        display_name=BASE_FIELDS["display_name"],
        origin_url=BASE_FIELDS["origin_url"],
        license=BASE_FIELDS["license"],
        retrieved_at=BASE_FIELDS["retrieved_at"],
        dataset_version=BASE_FIELDS["dataset_version"],
        schema_version="1",
        data_scope=BASE_FIELDS["data_scope"],
        demo=False,
        records_file="records.jsonl",
        data_derivation="independently_curated",
        upstream_license="none incorporated",
        license_core_facts=BASE_FIELDS["license_core_facts"],
        license_supplementary_used=BASE_FIELDS["license_supplementary_used"],
        license_service_terms=BASE_FIELDS["license_service_terms"],
        license_derived_package=BASE_FIELDS["license_derived_package"],
        content_digest=None,
    )
    base.update(overrides)
    return RegistryEntry(**base)


def test_batch_digest_is_stable_and_content_sensitive() -> None:
    d1 = digest_batch(_batch())
    assert d1 == digest_batch(_batch())  # deterministic
    assert len(d1) == 64  # SHA-256 hex
    # Genre binding is part of the digest (G3-007-001).
    assert digest_batch(_batch(genre_id="bebop")) != d1
    # A canonical MBID change is part of the digest (G3-007-002).
    changed = _records()[0]
    altered = _batch(
        candidates=(
            replace(changed, mbid="33333333-3333-3333-3333-333333333333"),
            _records()[1],
        )
    )
    assert digest_batch(altered) != d1
    # License/origin derivation are part of the digest envelope.
    assert digest_batch(_batch(source=_album_descriptor(license="MIT"))) != d1
    derived = _album_descriptor(data_derivation="derived_from_upstream")
    assert digest_batch(_batch(source=derived)) != d1


def test_verify_batch_integrity_rejects_tampered_digest() -> None:
    verify_batch_integrity(_batch())  # ok
    with pytest.raises(InvalidInputError):
        verify_batch_integrity(_batch(digest="f" * 64))
    with pytest.raises(InvalidInputError):
        verify_batch_integrity(_batch(digest=digest_batch(_batch())[:-1] + "0"))


def test_registry_load_and_lookup() -> None:
    registry = SourceRegistry({"curated-omda:album": _entry()})
    assert registry.get("curated-omda", "album").source_id == "curated-omda"
    assert registry.demo_policy("curated-omda", "album") is False
    with pytest.raises(InvalidInputError):
        registry.get("missing", "album")


@pytest.mark.parametrize(
    "field,value",
    [
        ("display_name", "Evil Display Name"),
        ("origin_url", "https://evil.example"),
        ("license", "MIT"),
        ("retrieved_at", "2099-01-01T00:00:00+00:00"),
        ("dataset_version", "2099-01-01"),
        ("schema_version", "999"),
        ("data_scope", "evil scope"),
        ("records_file", "evil.jsonl"),
        ("demo", True),
        ("data_derivation", "derived_from_upstream"),
        ("upstream_license", "CC BY-SA 4.0"),
        ("license_core_facts", "MIT"),
        ("license_supplementary_used", "MIT"),
        ("license_service_terms", "MIT"),
        ("license_derived_package", "MIT"),
    ],
)
def test_registry_verify_descriptor_mismatch_fails_closed(field, value) -> None:
    # G3-007-005: EVERY immutable delivery/governance field is bound to the
    # reviewed registry — a forged value in any field fails closed.
    registry = SourceRegistry({"curated-omda:album": _entry()})
    registry.verify_descriptor(_album_descriptor())
    with pytest.raises(InvalidInputError):
        registry.verify_descriptor(_album_descriptor(**{field: value}))


def test_genre_content_digest_is_bound_by_registry() -> None:
    # G3-007-003: the registry records the digest reviewed at install time; a
    # Genre descriptor carrying a different digest fails closed.
    registry = SourceRegistry(
        {
            "curated-omda:genre": _entry(kind="genre", content_digest="a" * 64),
            "curated-omda:album": _entry(),
        }
    )
    registry.verify_descriptor(_genre_descriptor(content_digest="a" * 64))
    with pytest.raises(InvalidInputError):
        registry.verify_descriptor(_genre_descriptor(content_digest="b" * 64))  # tampered


def test_assemble_validated_source_set() -> None:
    registry = SourceRegistry(
        {
            "curated-omda:genre": _entry(
                kind="genre", records_file="records.jsonl", content_digest="g" * 64
            ),
            "curated-omda:album": _entry(),
        }
    )
    batch = _batch()
    result = assemble_validated_source_set(
        registry,
        genre_descriptors=(_genre_descriptor(),),
        batches=(batch,),
        selected_genre_ids=("ambient",),
        required_candidates_per_genre=2,
    )
    assert isinstance(result, ValidatedSourceSet)
    assert result.batches[0].digest == batch.digest
    assert result.is_demo is False


def test_assemble_rejects_tampered_forged_or_unregistered_inputs() -> None:
    registry = SourceRegistry(
        {
            "curated-omda:genre": _entry(
                kind="genre", records_file="records.jsonl", content_digest="g" * 64
            ),
            "curated-omda:album": _entry(),
        }
    )
    # Tampered batch digest fails before any consumer sees it.
    with pytest.raises(InvalidInputError):
        assemble_validated_source_set(
            registry,
            genre_descriptors=(),
            batches=(_batch(digest="0" * 64),),
            selected_genre_ids=("ambient",),
        )
    # Forged production label: descriptor says demo=False but the reviewed
    # registry says demo=True (self-asserted label is not provenance, §8.5).
    demo_registry = SourceRegistry({"curated-omda:album": _entry(demo=True)})
    with pytest.raises(InvalidInputError):
        assemble_validated_source_set(
            demo_registry,
            genre_descriptors=(),
            batches=(_batch(),),
            selected_genre_ids=("ambient",),
        )
    # Unregistered source rejected outright.
    with pytest.raises(InvalidInputError):
        assemble_validated_source_set(
            SourceRegistry({}),
            genre_descriptors=(),
            batches=(_batch(),),
            selected_genre_ids=("ambient",),
        )


def test_selected_phantom_genre_is_rejected() -> None:
    # G3-007-003 Re-review 1: a caller-supplied Genre ID absent from the
    # reviewed Genre package can never cross the boundary, even when the batch
    # is internally consistent.
    registry = SourceRegistry(
        {
            "curated-omda:genre": _entry(
                kind="genre", records_file="records.jsonl", content_digest="g" * 64
            ),
            "curated-omda:album": _entry(),
        }
    )
    batch = _batch()
    with pytest.raises(InvalidInputError) as exc:
        assemble_validated_source_set(
            registry,
            genre_descriptors=(_genre_descriptor(),),
            batches=(batch,),
            selected_genre_ids=("phantom",),
        )
    assert "phantom" in str(exc.value)


def test_assemble_rejects_empty_and_incomplete_source_sets() -> None:
    registry = SourceRegistry({"curated-omda:album": _entry()})
    # G3-007-003: empty assembly is never a validated production set.
    with pytest.raises(InvalidInputError):
        assemble_validated_source_set(
            registry, genre_descriptors=(), batches=(), selected_genre_ids=("ambient",)
        )
    # A declared Genre with no album batch fails coverage.
    with pytest.raises(InvalidInputError):
        assemble_validated_source_set(
            registry,
            genre_descriptors=(_genre_descriptor(),),
            batches=(_batch(genre_id="bebop"),),
            selected_genre_ids=("ambient",),
        )
    # Below the required 3x3 coverage fails.
    with pytest.raises(InvalidInputError):
        assemble_validated_source_set(
            registry,
            genre_descriptors=(_genre_descriptor(),),
            batches=(_batch(),),
            selected_genre_ids=("ambient",),
            required_candidates_per_genre=3,
        )


def test_demo_status_covers_genre_descriptors_too() -> None:
    # G3-007-003: a registered demo Genre + production Albums must yield
    # is_demo=True — the delivery gate could otherwise trust a demo package.
    registry = SourceRegistry(
        {
            "curated-omda:genre": _entry(
                kind="genre", demo=True, records_file="records.jsonl", content_digest="g" * 64
            ),
            "curated-omda:album": _entry(),
        }
    )
    demo_genre = _genre_descriptor(demo=True)
    result = assemble_validated_source_set(
        registry,
        genre_descriptors=(demo_genre,),
        batches=(_batch(),),
        selected_genre_ids=("ambient",),
        required_candidates_per_genre=2,
    )
    assert result.is_demo is True


def test_duplicate_album_batch_for_genre_is_rejected() -> None:
    registry = SourceRegistry({"curated-omda:album": _entry()})
    with pytest.raises(InvalidInputError):
        assemble_validated_source_set(
            registry,
            genre_descriptors=(),
            batches=(_batch(), _batch()),
            selected_genre_ids=("ambient",),
        )
