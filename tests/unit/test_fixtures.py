"""T1.6 fixture integrity: every fixture record passes its versioned schema."""

from __future__ import annotations

import json

from tests.conftest import FIXTURES_DIR, load_jsonl

from omda.schemas import validate


def test_genre_fixture_records_pass_schema() -> None:
    records = load_jsonl(FIXTURES_DIR / "genres" / "sample.jsonl")
    assert len(records) >= 4
    for idx, record in enumerate(records):
        validate("genre", record, f"genres/sample.jsonl:{idx + 1}")


def test_album_fixture_records_pass_schema() -> None:
    records = load_jsonl(FIXTURES_DIR / "albums" / "sample.jsonl")
    assert len(records) >= 9
    for idx, record in enumerate(records):
        validate("album", record, f"albums/sample.jsonl:{idx + 1}")


def test_critic_source_fixture_passes_schema() -> None:
    source_path = FIXTURES_DIR / "critics" / "sample_source.json"
    source = json.loads(source_path.read_text(encoding="utf-8"))
    validate("critic_source", source, "critics/sample_source.json:1")


def test_critic_rating_fixture_rows_pass_schema() -> None:
    rows = load_jsonl(FIXTURES_DIR / "critics" / "sample_ratings.jsonl")
    assert len(rows) == 3
    for idx, row in enumerate(rows):
        validate("critic_rating", row, f"critics/sample_ratings.jsonl:{idx + 1}")


def test_conftest_sample_fixtures_are_available(
    sample_genres, sample_albums, fixtures_dir
) -> None:
    assert len(sample_genres) == 5
    assert len(sample_albums) == 10
    assert fixtures_dir.is_dir()
    # Families span more than one category so diversity tests (G2) have material.
    assert {g.family for g in sample_genres} >= {"Electronic", "Jazz", "Rock", "Regional"}
