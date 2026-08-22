"""Source-side contracts for curated community data (G3-007, ADR-0002).

Defines the versioned envelope contract for curated Genre and Album packages:

- ``SourceDescriptor`` / ``GenreSourceDescriptor``: immutable package metadata
  (license, origin, retrieval, schema version, demo policy);
- ``AlbumCandidateRecord``: one curated album candidate (facts + optional
  canonical MBID that the run-time enricher may fill later);
- ``CandidateBatch``: a versioned, digest-bound batch of candidates produced by
  one source package;
- ``ValidatedSourceSet``: the trusted assembly consumed by selection — composed
  and validated by the trusted application boundary AFTER FETCH and BEFORE any
  selection or delivery claim (ADR-0002 §8.4).

Digest semantics (ADR-0002 §8.5): the content digest proves INTEGRITY (the
batch content has not changed since validation), NOT authenticity. Authenticity
comes from the reviewed :class:`SourceRegistry` which binds ``source_id`` to the
expected origin/license/schema/demo policy; any mismatch fails closed. We never
claim resistance to malicious modification by an actor with local write access
to the repository (that would require a signature-trust ADR).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Protocol

from omda.ports.errors import InvalidInputError

BATCH_SCHEMA_VERSION = "1"

_DIGEST_SEPARATOR = "|"
_DIGEST_RECORD_SEPARATOR = "\x1f"


@dataclass(frozen=True)
class SourceDescriptor:
    """Immutable metadata of one curated community package (SPEC §3.3, MP §5)."""

    source_id: str
    kind: str  # "genre" | "album"
    display_name: str
    license: str
    origin_url: str
    retrieved_at: str
    dataset_version: str
    schema_version: str
    data_scope: str
    records_file: str
    demo: bool  # demo policy flag; the registry is the trust anchor, not this


@dataclass(frozen=True)
class GenreSourceDescriptor(SourceDescriptor):
    """A curated Genre package descriptor (kind == "genre")."""


@dataclass(frozen=True)
class AlbumCandidateRecord:
    """One curated album candidate fact record (facts + optional canonical MBID)."""

    album_id: str
    title: str
    artist: str
    year: int | None = None
    mbid: str | None = None  # canonical identity; may be filled by the enricher
    release_type: str = "album"  # curated packages only ship primary-type Album
    score: float | None = None  # relevance only, never a popularity signal


@dataclass(frozen=True)
class CandidateBatch:
    """A versioned, digest-bound batch of candidates from one source package.

    ``digest`` is the SHA-256 over the canonical serialization (see
    :func:`digest_batch`); it proves the batch content is intact. The source
    descriptor inside the batch is subject to registry verification.
    """

    schema_version: str
    query_policy_version: str  # curated: package/policy version; live: query policy
    source: SourceDescriptor
    digest: str
    candidates: tuple[AlbumCandidateRecord, ...]


@dataclass(frozen=True)
class ValidatedSourceSet:
    """The trusted, registry-validated source assembly for one recommendation run.

    Every Genre descriptor and Album batch inside has passed:
    1. registry lookup + full descriptor verification (origin/license/schema/
       demo/records_file must equal the reviewed registry entry);
    2. batch content-digest integrity verification.

    ``is_demo`` is exposed so the G4 delivery gate can reject demo data before
    any external call; G3-007 only builds and validates, it never decides
    delivery policy.
    """

    genre_descriptors: tuple[GenreSourceDescriptor, ...]
    batches: tuple[CandidateBatch, ...]

    @property
    def is_demo(self) -> bool:
        return any(batch.source.demo for batch in self.batches)


def _source_digest_fields(source: SourceDescriptor) -> str:
    return _DIGEST_SEPARATOR.join(
        (
            source.source_id,
            source.kind,
            source.license,
            source.origin_url,
            source.dataset_version,
            source.schema_version,
            "demo" if source.demo else "production",
        )
    )


def digest_batch(batch: CandidateBatch) -> str:
    """Return the SHA-256 hex digest over the batch's canonical serialization.

    The canonical form includes schema/query-policy versions, the digest-relevant
    source fields and every candidate record (sorted by album_id so the digest is
    deterministic regardless of file order).
    """
    record_lines = [
        _DIGEST_SEPARATOR.join(
            (
                record.album_id,
                record.title,
                record.artist,
                str(record.year) if record.year is not None else "",
                record.mbid or "",
                record.release_type,
                str(record.score) if record.score is not None else "",
            )
        )
        for record in sorted(batch.candidates, key=lambda r: r.album_id)
    ]
    canonical = _DIGEST_RECORD_SEPARATOR.join(
        (
            batch.schema_version,
            batch.query_policy_version,
            _source_digest_fields(batch.source),
            _DIGEST_RECORD_SEPARATOR.join(record_lines),
        )
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def verify_batch_integrity(batch: CandidateBatch) -> None:
    """Fail closed when the batch content does not match its declared digest."""
    expected = digest_batch(batch)
    if not isinstance(batch.digest, str) or len(batch.digest) != 64 or batch.digest != expected:
        raise InvalidInputError(
            f"candidate batch {batch.source.source_id!r}: digest mismatch "
            f"(declared {batch.digest!r}, recomputed {expected!r})"
        )


def assemble_validated_source_set(
    registry: SourceRegistryLike,
    *,
    genre_descriptors: tuple[GenreSourceDescriptor, ...],
    batches: tuple[CandidateBatch, ...],
) -> ValidatedSourceSet:
    """Assemble and validate the trusted source set (ADR-0002 §8.4/§8.5).

    Raises ``InvalidInputError`` on the first registry inconsistency, forged
    production label (descriptor.demo != registry.demo), tampered digest or
    unknown source. No network, no journal, no delivery side effects here.
    """
    for descriptor in genre_descriptors:
        registry.verify_descriptor(descriptor)
    for batch in batches:
        verify_batch_integrity(batch)
        registry.verify_descriptor(batch.source)
    return ValidatedSourceSet(
        genre_descriptors=tuple(genre_descriptors),
        batches=tuple(batches),
    )


class SourceRegistryLike(Protocol):
    """Structural view of the registry used by the assembly function."""

    def verify_descriptor(self, descriptor: SourceDescriptor) -> None:
        ...


__all__ = [
    "AlbumCandidateRecord",
    "BATCH_SCHEMA_VERSION",
    "CandidateBatch",
    "GenreSourceDescriptor",
    "SourceDescriptor",
    "ValidatedSourceSet",
    "assemble_validated_source_set",
    "digest_batch",
    "verify_batch_integrity",
]
