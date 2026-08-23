"""G3-007-007: tracked machine schemas must agree with the runtime source
contract, and the serialized boundary must validate against the tracked schema.

Version-drift tests: if the runtime constants and the tracked JSON schemas ever
disagree (or a package manifest declares a schema version the schema no longer
publishes), these tests fail."""

from __future__ import annotations

import json
from pathlib import Path

from omda.adapters.curated import CuratedAlbumSource, _validate_record
from omda.ports.domain import GenreRef
from omda.ports.source import BATCH_SCHEMA_VERSION

REPO = Path(__file__).resolve().parents[2]


def _schema(name: str) -> dict:
    return json.loads((REPO / "data" / "schemas" / f"{name}.schema.json").read_text("utf-8"))


def test_candidate_batch_schema_version_matches_runtime() -> None:
    # The tracked candidate_batch schema is the version the runtime serializes.
    assert _schema("candidate_batch")["schema_version"] == int(BATCH_SCHEMA_VERSION)


def test_genre_package_schema_version_matches_tracked_genre_source_schema() -> None:
    # G3-007-007: every Genre package manifest declares the version of the
    # tracked genre_source schema that governs it.
    expected = str(_schema("genre_source")["schema_version"])  # "3"
    for pkg in (REPO / "data" / "genres" / "curated-omda", REPO / "data" / "genres" / "rym-sample"):
        meta = _load_meta(pkg / "source.yaml")
        assert meta["schema_version"] == expected, pkg
    # And the registry records the same version for the reviewed Genre package.
    registry = [
        json.loads(line)
        for line in (REPO / "data" / "sources" / "registry.jsonl").read_text("utf-8").splitlines()
        if line.strip()
    ]
    for entry in registry:
        if entry["kind"] == "genre":
            assert entry["schema_version"] == expected
        else:
            assert entry["schema_version"] == str(_schema("album_source")["schema_version"])


def test_album_package_schema_version_matches_tracked_album_source_schema() -> None:
    meta = _load_meta(REPO / "data" / "albums" / "curated-omda" / "source.yaml")
    assert meta["schema_version"] == str(_schema("album_source")["schema_version"])


def test_serialized_batch_validates_against_tracked_schema() -> None:
    # The runtime serialization boundary (cache/export envelope) must validate
    # against the tracked candidate_batch v2 schema.
    source = CuratedAlbumSource(REPO / "data" / "albums" / "curated-omda")
    genre = GenreRef(genre_id="ambient", name="Ambient", family="x", eligible=True)
    payload = source._batch_to_json(source.batch_for_genre(genre))
    _validate_record("candidate_batch", payload, "<candidate_batch>")  # must not raise
    assert payload["schema_version"] == BATCH_SCHEMA_VERSION
    assert payload["genre_id"] == "ambient"


def _load_meta(path: Path) -> dict:
    from omda.adapters._miniyaml import load_flat_yaml

    return load_flat_yaml(path)
