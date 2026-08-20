"""G3 T3.5 — a new critic source requires NO Recommendation Core change (SPEC
§2.6; MP §3.3). The contribution package feeds the existing rating composition
through the existing CriticRatingSource port, and Core stays adapter-free."""

from __future__ import annotations

from pathlib import Path

from omda.adapters.datasets import CriticDatasetAdapter
from omda.core.rating import compose_rating
from omda.ports.domain import AlbumCandidate

REPO = Path(__file__).resolve().parents[2]


def test_new_critic_package_feeds_core_without_core_change() -> None:
    adapter = CriticDatasetAdapter(REPO / "data" / "critics" / "example-source")
    album = AlbumCandidate(album_id="ambient-album-a", title="A", artist="X")
    rows = adapter.ratings_for(album)
    assert len(rows) == 1
    score = compose_rating(rows, {"example-source": 1.0})
    assert score == 4.0 / 5.0


def test_critic_package_all_ratings_are_domain_rows() -> None:
    adapter = CriticDatasetAdapter(REPO / "data" / "critics" / "example-source")
    rows = adapter.all_ratings()
    assert {r.album_id for r in rows} == {
        "ambient-album-a",
        "bebop-album-b",
        "krautrock-album-c",
    }
    for row in rows:
        assert 1.0 <= row.rating <= 5.0
