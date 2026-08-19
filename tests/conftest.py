"""Shared pytest fixtures and fixture-data loaders (T1.6)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from omda.ports.domain import AlbumCandidate, GenreRef
from omda.storage import SqliteHistory
from tests.fakes import InMemoryHistory

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


def load_jsonl(path: Path) -> list[dict]:
    records: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            records.append(json.loads(line))
    return records


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES_DIR


@pytest.fixture
def sample_genres() -> list[GenreRef]:
    return [
        GenreRef(
            genre_id=r["genre_id"],
            name=r["name"],
            family=r["family"],
            eligible=r["eligible"],
        )
        for r in load_jsonl(FIXTURES_DIR / "genres" / "sample.jsonl")
    ]


@pytest.fixture
def sample_albums() -> list[AlbumCandidate]:
    return [
        AlbumCandidate(
            album_id=r["album_id"],
            title=r["title"],
            artist=r["artist"],
            year=r.get("year"),
            genres=tuple(r.get("genres", [])),
        )
        for r in load_jsonl(FIXTURES_DIR / "albums" / "sample.jsonl")
    ]


@pytest.fixture
def in_memory_history() -> InMemoryHistory:
    return InMemoryHistory()


@pytest.fixture
def sqlite_history(tmp_path) -> SqliteHistory:
    db = SqliteHistory(tmp_path / "state.sqlite3")
    yield db
    db.close()
