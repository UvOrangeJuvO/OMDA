"""Curated album source and Git-ignored runtime cache (G3-007, ADR-0002).

``CuratedAlbumSource`` implements the EXISTING ``AlbumSource`` port over a
reviewable curated album package (``data/albums/<source_id>/``: ``source.yaml``
validated against ``album_source`` schema + ``albums.jsonl`` validated against
``album_candidate`` schema). Every record is bound to the package ``source_id``
and the adapter builds a versioned :class:`CandidateBatch` with a content
digest; consumers assemble a :class:`ValidatedSourceSet` through the reviewed
``SourceRegistry`` AFTER fetch and BEFORE selection/delivery (ADR-0002 §8.4).

Demo packages load fine (so dry-run and tests can use them) but are exposed via
``batch.source.demo`` for the G4 delivery gate to reject; this adapter never
decides delivery policy.

``RuntimeCache`` is the local, bounded, Git-ignored runtime cache (ADR-0002
§8.6): it lives under ``var/cache/``, keys embed package/query-policy versions,
entries expire by TTL and are evicted FIFO at a hard cap, and it is safe to
delete. An ordinary run never writes tracked repository data.
"""

from __future__ import annotations

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
)

_SOURCE_YAML_NAME = "source.yaml"


def _validate_record(schema_name: str, record: dict, location: str) -> None:
    from omda.adapters.datasets import _validate_record as _base

    _base(schema_name, record, location)  # schema-validate + translate errors


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
                genres=(genre.genre_id,),
                identity=_identity_for(record),
            )
            for record in batch.candidates
        ]
        if limit is not None:
            candidates = candidates[:limit]
        return candidates

    # -- G3-007 batch API -----------------------------------------------------
    def batch_for_genre(self, genre: GenreRef) -> CandidateBatch:
        """Return the versioned, digest-bound CandidateBatch for a genre.

        The batch is memoized per genre within this adapter instance and served
        through the runtime cache (keyed by source/package version + genre) when
        one is configured; the digest makes every served copy verifiable.
        """
        if genre.genre_id in self._batch_cache:
            return self._batch_cache[genre.genre_id]
        key = self._cache_key(genre)
        if self._cache is not None:
            cached = self._cache.get(key)
            if cached is not None:
                batch = self._batch_from_json(cached)
                if batch is not None:
                    self._batch_cache[genre.genre_id] = batch
                    return batch
        batch = self._build_batch(genre)
        self._batch_cache[genre.genre_id] = batch
        if self._cache is not None:
            self._cache.put(key, self._batch_to_json(batch))
        return batch

    def descriptor(self) -> SourceDescriptor:
        meta = self._source_meta()
        return SourceDescriptor(
            source_id=meta["source_id"],
            kind="album",
            display_name=meta["display_name"],
            license=meta["license"],
            origin_url=meta["origin_url"],
            retrieved_at=meta["retrieved_at"],
            dataset_version=meta["dataset_version"],
            schema_version=meta["schema_version"],
            data_scope=meta["data_scope"],
            records_file=meta["records_file"],
            demo=bool(meta["demo"]),
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
                # Singles/EPs and any other type are rejected, never filtered
                # silently (a wrong type is malformed package data).
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
            records.append(record)
        self._records_cache = records
        return records

    def _build_batch(self, genre: GenreRef) -> CandidateBatch:
        meta = self._source_meta()
        records = [
            AlbumCandidateRecord(
                album_id=record["album_id"],
                title=record["title"],
                artist=record["artist"],
                year=record.get("year"),
                mbid=record.get("mbid"),
                release_type=record["release_type"],
                score=record.get("score"),
            )
            for record in self._records()
        ]
        descriptor = self.descriptor()
        batch = CandidateBatch(
            schema_version=BATCH_SCHEMA_VERSION,
            query_policy_version=meta["schema_version"],
            source=descriptor,
            digest="",
            candidates=tuple(records),
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
            },
            "digest": batch.digest,
            "candidates": [
                {
                    "album_id": record.album_id,
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


class RuntimeCache:
    """Bounded, local, Git-ignored runtime cache (ADR-0002 §8.6)."""

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
        # Bounded FIFO eviction: never grow past the hard cap.
        existing = sorted(p.name for p in self.root.glob("*.json"))
        while len(existing) >= self._max_entries:
            self._safe_delete(self.root / existing.pop(0))
        self._path_for(key).write_text(
            json.dumps({"value": payload, "_cached_at": self._clock()}, ensure_ascii=False),
            encoding="utf-8",
        )

    def clear(self) -> None:
        for child in list(self.root.glob("*.json")):
            self._safe_delete(child)

    def _path_for(self, key: str) -> Path:
        safe = "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in key)
        return self.root / f"{safe}.json"

    def _safe_delete(self, path: Path) -> None:
        import contextlib

        with contextlib.suppress(OSError):
            path.unlink()


__all__ = ["CuratedAlbumSource", "RuntimeCache"]
