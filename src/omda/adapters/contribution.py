"""Explicit curated import/export contribution workflow (G3-007, ADR-0002 §8.6).

A normal recommendation run NEVER writes tracked repository data. The ONLY path
that materializes a reviewable Git package is this EXPLICIT workflow:

- :func:`export_curated_package` writes a validated :class:`CandidateBatch` to
  an explicitly supplied target directory (``source.yaml`` + ``albums.jsonl``).
  The target is always explicit — never ``data/`` by default — and demo batches
  are refused unless the caller explicitly acknowledges review.
- :func:`import_curated_package` re-validates an on-disk package against its
  schema and the reviewed ``SourceRegistry`` before anything consumes it.

Human review and an explicit commit are what promote a package into tracked
data; this module never writes Git-tracked paths on its own.
"""

from __future__ import annotations

import json
from pathlib import Path

from omda.adapters.curated import CuratedAlbumSource
from omda.ports.domain import GenreRef
from omda.ports.errors import InvalidInputError
from omda.ports.source import (
    AlbumCandidateRecord,
    CandidateBatch,
    SourceDescriptor,
    verify_batch_integrity,
)
from omda.sources.registry import SourceRegistry

_REVIEW_MARKER = "REVIEW.md"


def export_curated_package(
    batch: CandidateBatch,
    *,
    target_dir: Path,
    review_acknowledged: bool = False,
) -> Path:
    """Materialize a validated batch as a curated package directory.

    The target directory must be EXPLICIT (never defaulted to tracked ``data/``).
    Demo batches are refused unless ``review_acknowledged`` is true, because a
    demo package has no business in a production contribution path.
    """
    verify_batch_integrity(batch)
    if batch.source.demo and not review_acknowledged:
        raise InvalidInputError(
            f"cannot export demo package {batch.source.source_id!r}: "
            "human review acknowledgement is required"
        )
    target_dir = Path(target_dir)
    if target_dir.name != batch.source.source_id:
        raise InvalidInputError(
            f"export target directory {target_dir.name!r} must equal the package "
            f"source_id {batch.source.source_id!r}"
        )
    target_dir.mkdir(parents=True, exist_ok=True)
    (target_dir / "source.yaml").write_text(_source_yaml(batch.source), encoding="utf-8")
    lines = []
    for record in sorted(batch.candidates, key=lambda r: r.album_id):
        row: dict = {
            "album_id": record.album_id,
            "title": record.title,
            "artist": record.artist,
            "release_type": record.release_type,
            "source": batch.source.source_id,
        }
        if record.year is not None:
            row["year"] = record.year
        if record.mbid:
            row["mbid"] = record.mbid
        if record.score is not None:
            row["score"] = record.score
        lines.append(json.dumps(row, ensure_ascii=False, sort_keys=True))
    (target_dir / "albums.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (target_dir / _REVIEW_MARKER).write_text(
        "Curated package export — REVIEW REQUIRED before promotion to tracked data.\n"
        "Check license/origin provenance, demo policy and schema; then register in\n"
        "data/sources/registry.jsonl and commit explicitly (ADR-0002 §8.6).\n",
        encoding="utf-8",
    )
    return target_dir


def import_curated_package(
    source_dir: Path, registry: SourceRegistry
) -> tuple[SourceDescriptor, list[AlbumCandidateRecord]]:
    """Validate an on-disk curated package and return descriptor + records.

    No file is written. The package must parse + schema-validate (through
    :class:`CuratedAlbumSource`) and its descriptor must exactly match the
    reviewed registry entry (demo policy, origin, license, schema, records
    file). Raises ``InvalidInputError`` on any inconsistency.
    """
    adapter = CuratedAlbumSource(source_dir)
    descriptor = adapter.descriptor()
    registry.verify_descriptor(descriptor)
    genre = GenreRef(genre_id="*", name="*", family="*", eligible=True)
    batch = adapter.batch_for_genre(genre)
    verify_batch_integrity(batch)
    return descriptor, list(batch.candidates)


def _source_yaml(source: SourceDescriptor) -> str:
    # Scalar strings are quoted so numeric-looking values (e.g. schema_version)
    # are not coerced by the flat-YAML parser on import.
    lines = [
        "# Curated package source manifest (album_source schema).",
        f"source_id: \"{source.source_id}\"",
        f"kind: \"{source.kind}\"",
        f"display_name: \"{source.display_name}\"",
        f"license: \"{source.license}\"",
        f"origin_url: \"{source.origin_url}\"",
        f"retrieved_at: \"{source.retrieved_at}\"",
        f"dataset_version: \"{source.dataset_version}\"",
        f"schema_version: \"{source.schema_version}\"",
        f"data_scope: \"{source.data_scope}\"",
        f"records_file: \"{source.records_file}\"",
        f"demo: {'true' if source.demo else 'false'}",
        "",
    ]
    return "\n".join(lines)


__all__ = ["export_curated_package", "import_curated_package"]
