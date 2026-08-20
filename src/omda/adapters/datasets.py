"""Community text dataset adapters (G3 T3.1/T3.2/T3.5).

Implements the EXISTING ``GenreSource`` and ``CriticRatingSource`` ports from
Git-reviewable text under ``data/``. Community text (JSONL/CSV/YAML) is the
source of truth (SPEC §3.3); every source declares license, provenance and
retrieved/updated time; parse/validation errors pinpoint file, record/line and
field (SPEC §7-1). No popularity/quality signal ever enters these adapters.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path

from omda.adapters._miniyaml import load_flat_yaml
from omda.ports.critic import CriticRatingRow
from omda.ports.domain import GenreRef
from omda.ports.errors import InvalidInputError
from omda.schemas import validate
from omda.schemas.validator import RecordValidationError

_SOURCE_YAML_NAME = "source.yaml"


@dataclass(frozen=True)
class DatasetProvenance:
    """Provenance of one community dataset (SPEC §3.3, MP §5)."""

    source_id: str
    display_name: str
    license: str
    origin_url: str
    retrieved_at: str
    dataset_version: str
    data_scope: str
    records_file: str


def _validate_record(schema_name: str, record: dict, location: str) -> None:
    """Schema-validate a record and translate failures into the domain error
    taxonomy (SPEC §8); the offending file/line/field stays in the message."""
    try:
        validate(schema_name, record, location)
    except RecordValidationError as exc:
        raise InvalidInputError(str(exc), detail={"errors": exc.errors}) from exc


def _load_source_meta(source_dir: Path, schema_name: str) -> dict:
    yaml_path = source_dir / _SOURCE_YAML_NAME
    if not yaml_path.exists():
        raise InvalidInputError(f"{source_dir}: missing {_SOURCE_YAML_NAME}")
    meta = load_flat_yaml(yaml_path)
    _validate_record(schema_name, meta, str(yaml_path))
    return meta


def _provenance_from_meta(meta: dict, records_file: str) -> DatasetProvenance:
    # critic packages declare "scrape_date" (iso8601 date); genre packages
    # declare "retrieved_at" (iso8601 datetime). Both mean the retrieval time.
    retrieved = meta.get("retrieved_at") or meta.get("scrape_date")
    return DatasetProvenance(
        source_id=meta["source_id"],
        display_name=meta["display_name"],
        license=meta["license"],
        origin_url=meta["origin_url"],
        retrieved_at=str(retrieved),
        dataset_version=meta.get("dataset_version") or meta.get("scrape_date"),
        data_scope=meta.get("data_scope", ""),
        records_file=meta.get("records_file", records_file),
    )


class GenreDatasetAdapter:
    """``GenreSource`` over a ``data/genres/<source>/`` package.

    Layout: ``source.yaml`` (genre_source schema) + ``genres.jsonl`` where each
    line is a record validated against the ``genre`` schema (genre_id, name,
    url, family, parents, eligible, source). The adapter returns the domain
    ``GenreRef`` values the Recommendation Core consumes and exposes dataset
    provenance separately.
    """

    def __init__(self, source_dir: Path) -> None:
        self._source_dir = Path(source_dir)
        self._meta: dict | None = None
        self._records_cache: list[dict] | None = None

    # -- GenreSource port ------------------------------------------------------
    def list_eligible_genres(self) -> list[GenreRef]:
        """Parse + schema-validate all records and map them to domain values.

        Validation errors name the file, the record line and the offending
        field. Duplicate genre_ids are rejected (records must be reviewable and
        unique). ``eligible`` only reflects data validity, never popularity.
        """
        meta = self._source_meta()
        records = self._records()
        seen: dict[str, int] = {}
        genres: list[GenreRef] = []
        records_file = self._source_dir / meta["records_file"]
        for line_no, record in enumerate(records, start=1):
            if record["genre_id"] in seen:
                raise InvalidInputError(
                    f"{records_file}:{line_no}: duplicate genre_id "
                    f"{record['genre_id']!r} (first at line {seen[record['genre_id']]})"
                )
            seen[record["genre_id"]] = line_no
            genres.append(
                GenreRef(
                    genre_id=record["genre_id"],
                    name=record["name"],
                    family=record["family"],
                    eligible=record["eligible"],
                    parents=tuple(record["parents"]),
                )
            )
        if not genres:
            raise InvalidInputError(f"{records_file}: no genre records found")
        return genres

    def provenance(self) -> DatasetProvenance:
        return _provenance_from_meta(self._source_meta(), "genres.jsonl")

    # -- internals -------------------------------------------------------------
    def _source_meta(self) -> dict:
        if self._meta is None:
            self._meta = _load_source_meta(self._source_dir, "genre_source")
        return self._meta

    def _records(self) -> list[dict]:
        if self._records_cache is not None:
            return self._records_cache
        meta = self._source_meta()
        records_file = self._source_dir / meta["records_file"]
        if not records_file.exists():
            raise InvalidInputError(f"{records_file}: records file missing")
        records: list[dict] = []
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
            _validate_record("genre", record, f"{records_file}:{line_no}")
            records.append(record)
        self._records_cache = records
        return records


class CriticDatasetAdapter:
    """``CriticRatingSource`` over a ``data/critics/<source>/`` package.

    Layout: ``source.yaml`` (critic_source schema) + ``ratings.csv`` with header
    ``source_id,album_id,rating,rating_max,review_url``. Each CSV row is
    validated against the ``critic_rating`` schema and checked for consistency
    with ``source.yaml`` (source_id match, rating within the declared scale).
    """

    def __init__(self, source_dir: Path) -> None:
        self._source_dir = Path(source_dir)
        self._meta: dict | None = None
        self._rows_cache: list[CriticRatingRow] | None = None

    # -- CriticRatingSource port ----------------------------------------------
    def ratings_for(self, album) -> list[CriticRatingRow]:
        """Return rows whose album_id matches the candidate's album_id."""
        rows = self._rows()
        return [row for row in rows if row.album_id == album.album_id]

    def all_ratings(self) -> list[CriticRatingRow]:
        return list(self._rows())

    def provenance(self) -> DatasetProvenance:
        return _provenance_from_meta(self._source_meta(), "ratings.csv")

    # -- internals -------------------------------------------------------------
    def _source_meta(self) -> dict:
        if self._meta is None:
            self._meta = _load_source_meta(self._source_dir, "critic_source")
        return self._meta

    def _rows(self) -> list[CriticRatingRow]:
        if self._rows_cache is not None:
            return self._rows_cache
        meta = self._source_meta()
        csv_path = self._source_dir / "ratings.csv"
        if not csv_path.exists():
            raise InvalidInputError(f"{csv_path}: ratings.csv missing")
        scale_min = meta["rating_scale_min"]
        scale_max = meta["rating_scale_max"]
        rows: list[CriticRatingRow] = []
        seen: set[tuple[str, str]] = set()
        with csv_path.open(encoding="utf-8", newline="") as handle:
            reader = csv.reader(handle)
            header = next(reader, None)
            if header is None or [h.strip() for h in header] != [
                "source_id",
                "album_id",
                "rating",
                "rating_max",
                "review_url",
            ]:
                raise InvalidInputError(
                    f"{csv_path}:1: header must be "
                    "source_id,album_id,rating,rating_max,review_url"
                )
            for row_no, cells in enumerate(reader, start=2):
                if not cells or all(not c.strip() for c in cells):
                    continue
                if len(cells) != 5:
                    raise InvalidInputError(
                        f"{csv_path}:{row_no}: expected 5 columns, got {len(cells)}"
                    )
                source_id = cells[0].strip()
                album_id = cells[1].strip()
                rating_cell = cells[2].strip()
                rating_max_cell = cells[3].strip()
                review_url_cell = cells[4].strip()
                try:
                    rating = float(rating_cell)
                except ValueError as exc:
                    raise InvalidInputError(
                        f"{csv_path}:{row_no}: rating {rating_cell!r} must be a number"
                    ) from exc
                record: dict = {
                    "source_id": source_id,
                    "album_id": album_id,
                    "rating": rating,
                }
                if rating_max_cell:
                    try:
                        record["rating_max"] = float(rating_max_cell)
                    except ValueError as exc:
                        raise InvalidInputError(
                            f"{csv_path}:{row_no}: rating_max {rating_max_cell!r} "
                            "must be a number"
                        ) from exc
                if review_url_cell:
                    record["review_url"] = review_url_cell
                _validate_record("critic_rating", record, f"{csv_path}:{row_no}")
                if source_id != meta["source_id"]:
                    raise InvalidInputError(
                        f"{csv_path}:{row_no}: source_id {source_id!r} does not match "
                        f"source.yaml ({meta['source_id']!r})"
                    )
                rating_max = record.get("rating_max")
                if not (scale_min <= rating <= scale_max):
                    raise InvalidInputError(
                        f"{csv_path}:{row_no}: rating {rating} outside declared scale "
                        f"[{scale_min}, {scale_max}]"
                    )
                if (source_id, album_id) in seen:
                    raise InvalidInputError(
                        f"{csv_path}:{row_no}: duplicate (source_id, album_id) "
                        f"({source_id!r}, {album_id!r})"
                    )
                seen.add((source_id, album_id))
                rows.append(
                    CriticRatingRow(
                        source_id=source_id,
                        album_id=album_id,
                        rating=rating,
                        rating_max=rating_max,
                        review_url=record.get("review_url"),
                    )
                )
        if not rows:
            raise InvalidInputError(f"{csv_path}: no rating rows found")
        self._rows_cache = rows
        return rows


__all__ = [
    "CriticDatasetAdapter",
    "DatasetProvenance",
    "GenreDatasetAdapter",
]
