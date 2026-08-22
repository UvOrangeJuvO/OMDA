"""Source-side contracts for curated community data (G3-007, ADR-0002).

Defines the versioned envelope contract for curated Genre and Album packages:

- ``SourceDescriptor`` / ``GenreSourceDescriptor``: immutable package metadata
  (license layers, origin, retrieval, schema version, demo policy, content
  digest for Genre packages);
- ``AlbumCandidateRecord``: one curated album candidate bound to a reviewed
  Genre (``genre_id``) with a verified canonical release-group MBID;
- ``CandidateBatch``: a versioned, digest-bound batch of candidates for ONE
  Genre produced by one source package;
- ``ValidatedSourceSet``: the trusted assembly consumed by selection — composed
  and validated by the trusted application boundary AFTER FETCH and BEFORE any
  selection or delivery claim (ADR-0002 §8.4).

Digest semantics (ADR-0002 §8.5): content digests prove INTEGRITY (the package
content has not changed since validation), NOT authenticity. Authenticity comes
from the reviewed :class:`SourceRegistry` which binds ``source_id`` to the
expected origin/license/schema/demo policy AND, for Genre packages, to the
reviewed content digest; any mismatch fails closed. We never claim resistance
to malicious modification by an actor with local write access to the repository
(that would require a signature-trust ADR).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Protocol

from omda.ports.errors import InvalidInputError

BATCH_SCHEMA_VERSION = "2"

_DIGEST_SEPARATOR = "|"
_DIGEST_RECORD_SEPARATOR = "\x1f"

# ADR-0002 D1: curated packages distinguish the four license/provenance layers
# instead of a blanket claim (G3-007-005).
_DATA_DERIVATIONS = frozenset({"independently_curated", "derived_from_upstream"})


@dataclass(frozen=True)
class SourceDescriptor:
    """Immutable metadata of one curated community package (SPEC §3.3, MP §5).

    License/provenance is recorded per layer (ADR-0002 D1/D2): the package-level
    ``license`` identifier, the derivation basis, the upstream license and the
    four explicit layers. The reviewed SourceRegistry remains the authority.
    """

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
    data_derivation: str  # "independently_curated" | "derived_from_upstream"
    upstream_license: str
    license_core_facts: str
    license_supplementary_used: str
    license_service_terms: str
    license_derived_package: str


@dataclass(frozen=True)
class GenreSourceDescriptor(SourceDescriptor):
    """A curated Genre package descriptor (kind == "genre").

    ``content_digest`` is the SHA-256 over the reviewed manifest + Genre records
    (G3-007-003); the registry records the digest reviewed at install time, so a
    tampered Genre package fails closed at the source-set boundary.
    """

    content_digest: str = ""


@dataclass(frozen=True)
class AlbumCandidateRecord:
    """One curated album candidate fact record.

    ``genre_id`` is the REVIEWED Genre membership (G3-007-001) and ``mbid`` is
    the verified MusicBrainz release-group canonical identity (G3-007-002).
    """

    album_id: str
    genre_id: str
    title: str
    artist: str
    year: int | None = None
    mbid: str | None = None  # required for production records; demo-only may be None
    release_type: str = "album"  # curated packages only ship primary-type Album
    score: float | None = None  # relevance only, never a popularity signal


@dataclass(frozen=True)
class CandidateBatch:
    """A versioned, digest-bound batch of candidates for ONE Genre.

    ``genre_id`` is the exact Genre the batch answers; ``digest`` is the SHA-256
    over the canonical serialization and covers genre binding + MBID (so a
    membership or identity change is detectable).
    """

    schema_version: str
    query_policy_version: str
    genre_id: str
    source: SourceDescriptor
    digest: str
    candidates: tuple[AlbumCandidateRecord, ...]


@dataclass(frozen=True)
class ValidatedSourceSet:
    """The trusted, registry-validated source assembly for one recommendation run.

    Every Genre descriptor and Album batch inside has passed:
    1. registry lookup + full descriptor verification (origin/license/schema/
       demo/records_file/derivation/upstream license/content digest must equal
       the reviewed registry entry);
    2. Genre content-digest verification and Album batch digest verification;
    3. completeness: at least one Genre and at least one batch, with every
       declared Genre covered by >= ``required_candidates_per_genre`` candidates.

    ``is_demo`` covers BOTH Genre descriptors and Album batches (G3-007-003), so
    a registered demo Genre can never be paired with production Albums and yield
    a false production result.
    """

    genre_descriptors: tuple[GenreSourceDescriptor, ...]
    batches: tuple[CandidateBatch, ...]

    @property
    def is_demo(self) -> bool:
        return any(d.demo for d in self.genre_descriptors) or any(
            b.source.demo for b in self.batches
        )


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
            source.data_derivation,
            source.upstream_license,
        )
    )


def digest_batch(batch: CandidateBatch) -> str:
    """Return the SHA-256 hex digest over the batch's canonical serialization.

    The canonical form includes schema/query-policy versions, the exact Genre,
    the digest-relevant source fields and every candidate record (sorted by
    album_id): genre binding and MBID are part of the digest, so changing a
    Genre membership or canonical identity changes the digest (G3-007-001/002).
    """
    record_lines = [
        _DIGEST_SEPARATOR.join(
            (
                record.album_id,
                record.genre_id,
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
            batch.genre_id,
            _source_digest_fields(batch.source),
            _DIGEST_RECORD_SEPARATOR.join(record_lines),
        )
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def digest_genre_records(records: tuple[tuple[str, ...], ...]) -> str:
    """SHA-256 over canonical Genre record lines (G3-007-003).

    Each line: (genre_id, name, family, sorted(parents), eligible, url, source)
    sorted by genre_id so the digest is deterministic regardless of file order.
    """
    lines = [
        _DIGEST_SEPARATOR.join(record)
        for record in sorted(records, key=lambda r: r[0])
    ]
    return hashlib.sha256(
        _DIGEST_RECORD_SEPARATOR.join(lines).encode("utf-8")
    ).hexdigest()


def verify_batch_integrity(batch: CandidateBatch) -> None:
    """Fail closed when the batch content does not match its declared digest."""
    expected = digest_batch(batch)
    if not isinstance(batch.digest, str) or len(batch.digest) != 64 or batch.digest != expected:
        raise InvalidInputError(
            f"candidate batch {batch.source.source_id!r} [{batch.genre_id!r}]: digest "
            f"mismatch (declared {batch.digest!r}, recomputed {expected!r})"
        )


def assemble_validated_source_set(
    registry: SourceRegistryLike,
    *,
    genre_descriptors: tuple[GenreSourceDescriptor, ...],
    batches: tuple[CandidateBatch, ...],
    selected_genre_ids: tuple[str, ...],
    required_candidates_per_genre: int = 3,
) -> ValidatedSourceSet:
    """Assemble and validate the trusted source set (ADR-0002 §8.4/§8.5).

    ``selected_genre_ids`` is the set of Genres the run actually selected (from
    the GenreSource); every selected Genre must be covered by exactly one Album
    batch with >= ``required_candidates_per_genre`` candidates.

    Fails closed (``InvalidInputError``) when:
    - the source set or selected-genre set is empty;
    - a Genre descriptor or Album batch disagrees with the reviewed registry
      (origin/license/schema/demo/derivation/upstream license/content digest);
    - a batch digest is tampered or a Genre package content digest mismatches;
    - a selected Genre has no batch, has fewer than the required candidates, or
      a batch claims a Genre while carrying records of another Genre (unrelated
      batch, G3-007-001/003).

    No network, no journal, no delivery side effects here.
    """
    if not genre_descriptors or not batches or not selected_genre_ids:
        raise InvalidInputError(
            "validated source set must contain at least one Genre descriptor, one "
            "Album batch and one selected Genre"
        )
    if not isinstance(required_candidates_per_genre, int) or isinstance(
        required_candidates_per_genre, bool
    ) or required_candidates_per_genre <= 0:
        raise InvalidInputError(
            f"required_candidates_per_genre must be a positive integer, got "
            f"{required_candidates_per_genre!r}"
        )
    selected = set(selected_genre_ids)
    for descriptor in genre_descriptors:
        registry.verify_descriptor(descriptor)
        _verify_genre_digest(descriptor)
    covered: dict[str, int] = {}
    seen_batch_genres: set[str] = set()
    for batch in batches:
        verify_batch_integrity(batch)
        registry.verify_descriptor(batch.source)
        if batch.genre_id in seen_batch_genres:
            raise InvalidInputError(
                f"duplicate album batch for genre {batch.genre_id!r}"
            )
        seen_batch_genres.add(batch.genre_id)
        if batch.genre_id not in selected:
            raise InvalidInputError(
                f"album batch for genre {batch.genre_id!r} is not in the selected "
                f"genres {sorted(selected)}"
            )
        # G3-007-001/003: every candidate must belong to the batch's Genre —
        # a batch that claims Genre X while carrying Genre Y records is
        # unrelated/rejected, never relabelled.
        for record in batch.candidates:
            if record.genre_id != batch.genre_id:
                raise InvalidInputError(
                    f"album batch {batch.genre_id!r} contains record "
                    f"{record.album_id!r} of genre {record.genre_id!r}"
                )
        covered[batch.genre_id] = len(batch.candidates)
    for genre_id in sorted(selected):
        if genre_id not in covered:
            raise InvalidInputError(
                f"selected genre {genre_id!r} has no album batch in the source set"
            )
        if covered[genre_id] < required_candidates_per_genre:
            raise InvalidInputError(
                f"selected genre {genre_id!r} has {covered[genre_id]} candidates, below "
                f"the required {required_candidates_per_genre}"
            )
    return ValidatedSourceSet(
        genre_descriptors=tuple(genre_descriptors),
        batches=tuple(batches),
    )


def _verify_genre_digest(descriptor: GenreSourceDescriptor) -> None:
    if (
        not isinstance(descriptor.content_digest, str)
        or len(descriptor.content_digest) != 64
    ):
        raise InvalidInputError(
            f"genre source {descriptor.source_id!r}: missing or malformed content_digest"
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
    "digest_genre_records",
    "verify_batch_integrity",
]
