"""Curated album source and Git-ignored runtime cache (G3-007, ADR-0002).

``CuratedAlbumSource`` implements the EXISTING ``AlbumSource`` port (both the
candidate list and the provider-neutral ``source_batch`` envelope) over a
reviewable curated album package (``data/albums/<source_id>/``: ``source.yaml``
validated against ``album_source`` schema + ``albums.jsonl`` validated against
``album_candidate`` schema).

Every record is bound to a REVIEWED Genre (``genre_id``) and carries a verified
MusicBrainz release-group MBID for production packages (G3-007-001/002). The
adapter builds one versioned :class:`CandidateBatch` PER Genre, filtering by
exact reviewed Genre membership — it never relabels unrelated records; a Genre
with no coverage fails clearly. Consumers assemble a :class:`ValidatedSourceSet`
through the reviewed ``SourceRegistry`` AFTER fetch and BEFORE selection/delivery
(ADR-0002 §8.4).

Cached batches are digest-verified before being served; an invalid cache entry
is a typed miss (rebuilt), never trusted (G3-007-004).

``RuntimeCache`` is the local, bounded, Git-ignored runtime cache (ADR-0002
§8.6): it lives under ``var/cache/``, keys are collision-resistant, entries
expire by a validated positive-finite TTL and are evicted in INSERTION order
(FIFO) at a hard cap, and it is safe to delete. An ordinary run never writes
tracked repository data.
"""

from __future__ import annotations

import hashlib
import json
import time as _time
from dataclasses import replace
from pathlib import Path
from typing import Any

from omda.adapters._miniyaml import load_flat_yaml
from omda.ports.domain import AlbumCandidate, AlbumIdentity, GenreRef
from omda.ports.errors import InvalidInputError
from omda.ports.source import (
    BATCH_SCHEMA_VERSION,
    AlbumCandidateRecord,
    CandidateBatch,
    SourceDescriptor,
    digest_batch,
    verify_batch_integrity,
)

_SOURCE_YAML_NAME = "source.yaml"


def _validate_record(schema_name: str, record: dict, location: str) -> None:
    from omda.adapters.datasets import _validate_record as _base

    _base(schema_name, record, location)  # schema-validate + translate errors


def _descriptor_fields(meta: dict, kind: str) -> dict:
    return {
        "source_id": meta["source_id"],
        "kind": kind,
        "display_name": meta["display_name"],
        "license": meta["license"],
        "origin_url": meta["origin_url"],
        "retrieved_at": meta["retrieved_at"],
        "dataset_version": meta["dataset_version"],
        "schema_version": meta["schema_version"],
        "data_scope": meta["data_scope"],
        "records_file": meta["records_file"],
        "demo": bool(meta["demo"]),
        "data_derivation": meta["data_derivation"],
        "upstream_license": meta["upstream_license"],
        "license_core_facts": meta["license_core_facts"],
        "license_supplementary_used": meta["license_supplementary_used"],
        "license_service_terms": meta["license_service_terms"],
        "license_derived_package": meta["license_derived_package"],
    }


class CuratedAlbumSource:
    """``AlbumSource`` over a curated album package (data/albums/<source_id>/)."""

    def __init__(self, source_dir: Path, *, cache: RuntimeCache | None = None) -> None:
        self._source_dir = Path(source_dir)
        self._cache = cache
        self._meta: dict | None = None
        self._records_cache: list[dict] | None = None
        self._batch_cache: dict[str, CandidateBatch] = {}

    # -- AlbumSource port -----------------------------------------------------
    def candidates_for_genre(
        self, genre: GenreRef, limit: int | None = None
    ) -> list[AlbumCandidate]:
        batch = self.batch_for_genre(genre)
        candidates = [
            AlbumCandidate(
                album_id=record.album_id,
                title=record.title,
                artist=record.artist,
                year=record.year,
                genres=(record.genre_id,),  # the REVIEWED membership, never relabelled
                identity=_identity_for(record),
            )
            for record in batch.candidates
        ]
        if limit is not None:
            candidates = candidates[:limit]
        return candidates

    def source_batch(self, genre: GenreRef) -> CandidateBatch:
        """Provider-neutral envelope Port method (G3-007-004): return the
        versioned, digest-bound batch for a Genre."""
        return self.batch_for_genre(genre)

    # -- G3-007 batch API -----------------------------------------------------
    def batch_for_genre(self, genre: GenreRef) -> CandidateBatch:
        """Return the versioned, digest-bound CandidateBatch for ONE Genre.

        The batch is filtered by the reviewed ``genre_id`` membership and is
        memoized per Genre; cached copies are digest-verified before serving
        (an invalid cache entry is treated as a typed miss and rebuilt).
        """
        if genre.genre_id in self._batch_cache:
            return self._batch_cache[genre.genre_id]
        key = self._cache_key(genre)
        if self._cache is not None:
            cached = self._cache.get(key)
            if cached is not None:
                batch = self._batch_from_json(cached)
                if batch is not None:
                    try:
                        verify_batch_integrity(batch)
                    except InvalidInputError:
                        # G3-007-004: an invalid cached entry must never be
                        # trusted — treat as a miss and rebuild from the package.
                        self._cache.delete(key)
                    else:
                        if batch.genre_id == genre.genre_id:
                            self._batch_cache[genre.genre_id] = batch
                            return batch
        batch = self._build_batch(genre)
        self._batch_cache[genre.genre_id] = batch
        if self._cache is not None:
            self._cache.put(key, self._batch_to_json(batch))
        return batch

    def descriptor(self) -> SourceDescriptor:
        return SourceDescriptor(**_descriptor_fields(self._source_meta(), "album"))

    def all_records(self) -> tuple[AlbumCandidateRecord, ...]:
        """Every package record as a domain record (for import/validation).

        Unlike ``source_batch`` this is NOT Genre-filtered: it validates the
        whole package (schema, uniqueness, canonical IDs) for the explicit
        contribution workflow.
        """
        return tuple(
            AlbumCandidateRecord(
                album_id=record["album_id"],
                genre_id=record["genre_id"],
                title=record["title"],
                artist=record["artist"],
                year=record.get("year"),
                mbid=record.get("mbid"),
                release_type=record["release_type"],
                score=record.get("score"),
            )
            for record in self._records()
        )

    # -- internals -------------------------------------------------------------
    def _source_meta(self) -> dict:
        if self._meta is None:
            yaml_path = self._source_dir / _SOURCE_YAML_NAME
            if not yaml_path.exists():
                raise InvalidInputError(f"{self._source_dir}: missing {_SOURCE_YAML_NAME}")
            meta = load_flat_yaml(yaml_path)
            _validate_record("album_source", meta, str(yaml_path))
            if meta["source_id"] != self._source_dir.name:
                raise InvalidInputError(
                    f"{self._source_dir}: source.yaml source_id {meta['source_id']!r} "
                    f"does not match package directory {self._source_dir.name!r}"
                )
            self._meta = meta
        return self._meta

    def _records_path(self) -> Path:
        meta = self._source_meta()
        raw = meta["records_file"]
        candidate = Path(raw)
        if candidate.is_absolute():
            raise InvalidInputError(
                f"{self._source_dir}: records_file must be relative, got {raw!r}"
            )
        base = self._source_dir.resolve()
        resolved = (self._source_dir / raw).resolve()
        if resolved != base and base not in resolved.parents:
            raise InvalidInputError(
                f"{self._source_dir}: records_file {raw!r} escapes the package directory"
            )
        return resolved

    def _records(self) -> list[dict]:
        if self._records_cache is not None:
            return self._records_cache
        meta = self._source_meta()
        records_file = self._records_path()
        if not records_file.exists():
            raise InvalidInputError(f"{records_file}: records file missing")
        records: list[dict] = []
        seen: dict[str, int] = {}
        seen_mbids: dict[str, str] = {}
        for line_no, line in enumerate(
            records_file.read_text(encoding="utf-8").splitlines(), start=1
        ):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                record = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise InvalidInputError(f"{records_file}:{line_no}: invalid JSON: {exc}") from exc
            if not isinstance(record, dict):
                raise InvalidInputError(f"{records_file}:{line_no}: record must be a JSON object")
            _validate_record("album_candidate", record, f"{records_file}:{line_no}")
            if record["source"] != meta["source_id"]:
                raise InvalidInputError(
                    f"{records_file}:{line_no}: record source {record['source']!r} does not "
                    f"match source.yaml source_id {meta['source_id']!r}"
                )
            if record["release_type"] != "album":
                # ADR-0002 D3: curated packages only ship primary-type Album;
                # any other type is rejected, never filtered silently.
                raise InvalidInputError(
                    f"{records_file}:{line_no}: release_type must be 'album', "
                    f"got {record['release_type']!r}"
                )
            if record["album_id"] in seen:
                raise InvalidInputError(
                    f"{records_file}:{line_no}: duplicate album_id "
                    f"{record['album_id']!r} (first at line {seen[record['album_id']]})"
                )
            seen[record["album_id"]] = line_no
            mbid = record.get("mbid")
            if not meta["demo"] and not mbid:
                # G3-007-002: production Album records MUST carry a verified
                # canonical MBID (release-group identity for permanent
                # exclusion); demo/legacy fixtures may omit it.
                raise InvalidInputError(
                    f"{records_file}:{line_no}: production record "
                    f"{record['album_id']!r} lacks a canonical mbid"
                )
            if mbid:
                # G3-007-002: duplicate canonical IDs are rejected — a stable
                # identity must be unique within the package.
                if mbid in seen_mbids:
                    raise InvalidInputError(
                        f"{records_file}:{line_no}: duplicate canonical mbid {mbid!r} "
                        f"(first at line {seen_mbids[mbid]})"
                    )
                seen_mbids[mbid] = line_no
            records.append(record)
        self._records_cache = records
        return records

    def _build_batch(self, genre: GenreRef) -> CandidateBatch:
        meta = self._source_meta()
        matched = [
            record
            for record in self._records()
            if record["genre_id"] == genre.genre_id
        ]
        if not matched:
            # G3-007-001: unknown/empty Genre coverage fails clearly — never
            # serve another Genre's records under the requested Genre.
            raise InvalidInputError(
                f"album package {meta['source_id']!r} has no records for genre "
                f"{genre.genre_id!r} (declared genres: "
                f"{sorted({r['genre_id'] for r in self._records()})})"
            )
        records = tuple(
            AlbumCandidateRecord(
                album_id=record["album_id"],
                genre_id=record["genre_id"],
                title=record["title"],
                artist=record["artist"],
                year=record.get("year"),
                mbid=record.get("mbid"),
                release_type=record["release_type"],
                score=record.get("score"),
            )
            for record in matched
        )
        descriptor = self.descriptor()
        batch = CandidateBatch(
            schema_version=BATCH_SCHEMA_VERSION,
            query_policy_version=meta["schema_version"],
            genre_id=genre.genre_id,
            source=descriptor,
            digest="",
            candidates=records,
        )
        return replace(batch, digest=digest_batch(batch))

    def _cache_key(self, genre: GenreRef) -> str:
        meta = self._source_meta()
        # Query/package/policy version is part of the key so a policy change
        # never serves a stale entry (ADR-0002 §8.6).
        return (
            f"{meta['source_id']}|{meta['dataset_version']}|"
            f"{meta['schema_version']}|{genre.genre_id}"
        )

    def _batch_to_json(self, batch: CandidateBatch) -> dict[str, Any]:
        return {
            "schema_version": batch.schema_version,
            "query_policy_version": batch.query_policy_version,
            "genre_id": batch.genre_id,
            "source": {
                "source_id": batch.source.source_id,
                "kind": batch.source.kind,
                "display_name": batch.source.display_name,
                "license": batch.source.license,
                "origin_url": batch.source.origin_url,
                "retrieved_at": batch.source.retrieved_at,
                "dataset_version": batch.source.dataset_version,
                "schema_version": batch.source.schema_version,
                "data_scope": batch.source.data_scope,
                "records_file": batch.source.records_file,
                "demo": batch.source.demo,
                "data_derivation": batch.source.data_derivation,
                "upstream_license": batch.source.upstream_license,
                "license_core_facts": batch.source.license_core_facts,
                "license_supplementary_used": batch.source.license_supplementary_used,
                "license_service_terms": batch.source.license_service_terms,
                "license_derived_package": batch.source.license_derived_package,
            },
            "digest": batch.digest,
            "candidates": [
                {
                    "album_id": record.album_id,
                    "genre_id": record.genre_id,
                    "title": record.title,
                    "artist": record.artist,
                    "year": record.year,
                    "mbid": record.mbid,
                    "release_type": record.release_type,
                    "score": record.score,
                }
                for record in batch.candidates
            ],
        }

    def _batch_from_json(self, payload: dict) -> CandidateBatch | None:
        try:
            source = SourceDescriptor(**payload["source"])
            records = tuple(
                AlbumCandidateRecord(
                    album_id=item["album_id"],
                    genre_id=item["genre_id"],
                    title=item["title"],
                    artist=item["artist"],
                    year=item.get("year"),
                    mbid=item.get("mbid"),
                    release_type=item.get("release_type", "album"),
                    score=item.get("score"),
                )
                for item in payload["candidates"]
            )
            batch = CandidateBatch(
                schema_version=payload["schema_version"],
                query_policy_version=payload["query_policy_version"],
                genre_id=payload["genre_id"],
                source=source,
                digest=payload["digest"],
                candidates=records,
            )
            return batch
        except (KeyError, TypeError, ValueError):
            return None  # malformed cache entry: treat as a miss, never trust it


def _identity_for(record: AlbumCandidateRecord) -> AlbumIdentity | None:
    if not record.mbid:
        return None
    return AlbumIdentity(
        album_id=record.album_id,
        canonical_id=record.mbid,
        canonical_source="musicbrainz",
        identity_confidence="exact",
    )


def _is_finite_positive(value: float) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and value > 0
        and value != float("inf")
        and value != float("nan")
    )


class RuntimeCache:
    """Bounded, local, Git-ignored runtime cache (ADR-0002 §8.6).

    - positive finite TTL enforced at construction (G3-007-006);
    - collision-resistant keys: the file name is the SHA-256 of the key;
    - insertion-order FIFO eviction via a manifest, not filename sorting;
    - safe to delete; ordinary runs never write tracked data.
    """

    _MANIFEST = "manifest.json"

    def __init__(
        self,
        cache_dir: Path,
        *,
        max_entries: int = 64,
        ttl_seconds: float = 7 * 24 * 3600,
        clock: Any = None,
    ) -> None:
        if not isinstance(max_entries, int) or isinstance(max_entries, bool) or max_entries <= 0:
            raise ValueError(f"max_entries must be a positive integer, got {max_entries!r}")
        if not _is_finite_positive(ttl_seconds):
            raise ValueError(f"ttl_seconds must be a finite positive number, got {ttl_seconds!r}")
        self.root = Path(cache_dir)
        self._max_entries = max_entries
        self._ttl = ttl_seconds
        self._clock = clock or _time.time

    def get(self, key: str) -> dict | None:
        path = self._path_for(key)
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None
        stamp = payload.get("_cached_at")
        if not isinstance(stamp, (int, float)) or (self._clock() - stamp) > self._ttl:
            return None
        return payload.get("value")

    def put(self, key: str, payload: dict) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self._touch_manifest(key)
        self._evict_fifo()
        self._path_for(key).write_text(
            json.dumps({"value": payload, "_cached_at": self._clock()}, ensure_ascii=False),
            encoding="utf-8",
        )

    def delete(self, key: str) -> None:
        """Delete one cache entry (used for invalid cached batches)."""
        path = self._path_for(key)
        with _suppress(OSError):
            path.unlink()
        self._drop_manifest(key)

    def clear(self) -> None:
        for child in list(self.root.glob("*.json")):
            with _suppress(OSError):
                child.unlink()

    # -- internals -------------------------------------------------------------
    def _path_for(self, key: str) -> Path:
        # G3-007-006: SHA-256 of the key — distinct keys (a/b vs a_b) can never
        # collide on the same file.
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
        return self.root / f"{digest}.json"

    def _manifest_path(self) -> Path:
        return self.root / self._MANIFEST

    def _manifest(self) -> list[str]:
        path = self._manifest_path()
        if not path.exists():
            return []
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return []
        if not isinstance(data, list):
            return []
        return [item for item in data if isinstance(item, str)]

    def _touch_manifest(self, key: str) -> None:
        order = self._manifest()
        order = [k for k in order if k != key]  # refresh position on re-put
        order.append(key)
        self._write_manifest(order)

    def _drop_manifest(self, key: str) -> None:
        self._write_manifest([k for k in self._manifest() if k != key])

    def _write_manifest(self, order: list[str]) -> None:
        self._manifest_path().write_text(json.dumps(order), encoding="utf-8")

    def _evict_fifo(self) -> None:
        """Evict in INSERTION order until the hard cap is satisfied."""
        order = self._manifest()
        while len(order) > self._max_entries:
            oldest = order.pop(0)  # FIFO: first inserted is evicted first
            with _suppress(OSError):
                self._path_for(oldest).unlink()
        self._write_manifest(order)


def _suppress(*exceptions: type[BaseException]):
    import contextlib

    return contextlib.suppress(*exceptions)


__all__ = ["CuratedAlbumSource", "RuntimeCache"]
