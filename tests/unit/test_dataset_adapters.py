"""G3 T3.2/T3.5 — dataset adapter tests (SPEC §7-1 precise malformed rejection).

Covers: valid packages, unknown fields, missing fields, bad types, duplicate
identity, bad url/date/rating, CSV row errors, source.yaml <-> ratings.csv
inconsistency, missing license/provenance. Every error pinpoints file, line and
field; the adapter implements the EXISTING GenreSource/CriticRatingSource ports.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from omda.adapters.datasets import CriticDatasetAdapter, GenreDatasetAdapter
from omda.ports.domain import AlbumCandidate
from omda.ports.errors import InvalidInputError

REPO = Path(__file__).resolve().parents[2]
GENRE_PKG = REPO / "data" / "genres" / "rym-sample"
CRITIC_PKG = REPO / "data" / "critics" / "example-source"


# --- valid packages -----------------------------------------------------------


def test_valid_genre_package_maps_to_domain_values() -> None:
    adapter = GenreDatasetAdapter(GENRE_PKG)
    genres = adapter.list_eligible_genres()
    assert [g.genre_id for g in genres] == ["ambient", "bebop", "krautrock", "tuareg"]
    ambient = genres[0]
    assert ambient.name == "Ambient"
    assert ambient.family == "Electronic"
    assert ambient.eligible is True
    assert ambient.parents == ("electronic",)


def test_valid_genre_package_exposes_provenance() -> None:
    prov = GenreDatasetAdapter(GENRE_PKG).provenance()
    assert prov.source_id == "rym-sample"
    assert prov.license
    assert prov.origin_url.startswith("https://")
    assert prov.retrieved_at
    assert prov.dataset_version
    assert prov.records_file == "genres.jsonl"


def test_valid_critic_package_implements_critic_port(tmp_path: Path) -> None:
    adapter = CriticDatasetAdapter(CRITIC_PKG)
    album = AlbumCandidate(album_id="ambient-album-a", title="A", artist="X")
    rows = adapter.ratings_for(album)
    assert len(rows) == 1
    assert rows[0].rating == 4.0
    assert rows[0].rating_max == 5.0
    assert adapter.provenance().source_id == "example-source"


# --- precise malformed rejection ----------------------------------------------


def _write_genre_pkg(tmp_path: Path, records: list[str], meta: str | None = None) -> Path:
    pkg = tmp_path / "genres" / "bad"
    pkg.mkdir(parents=True)
    (pkg / "source.yaml").write_text(
        meta
        or """source_id: bad
display_name: Bad
license: CC0-1.0
origin_url: https://example.org
retrieved_at: 2026-08-20T00:00:00+00:00
dataset_version: v1
data_scope: test
records_file: genres.jsonl
""",
        encoding="utf-8",
    )
    (pkg / "genres.jsonl").write_text("\n".join(records) + "\n", encoding="utf-8")
    return pkg


def test_genre_unknown_field_rejected_at_line() -> None:
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        pkg = _write_genre_pkg(Path(d), [
            json.dumps(
                {
                    "genre_id": "g1",
                    "name": "G1",
                    "url": "https://e.org/g1",
                    "family": "Rock",
                    "parents": ["rock"],
                    "eligible": True,
                    "source": "bad",
                    "extra_field": 1,
                }
            )
        ])
        with pytest.raises(InvalidInputError) as exc:
            GenreDatasetAdapter(pkg).list_eligible_genres()
        assert "genres.jsonl:1" in str(exc.value)
        assert "extra_field" in str(exc.value)


def test_genre_missing_field_rejected_at_line() -> None:
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        pkg = _write_genre_pkg(Path(d), [
            json.dumps(
                {
                    "genre_id": "g1",
                    "name": "G1",
                    "family": "Rock",
                    "parents": ["rock"],
                    "eligible": True,
                    "source": "bad",
                }
            )
        ])
        with pytest.raises(InvalidInputError) as exc:
            GenreDatasetAdapter(pkg).list_eligible_genres()
        assert "genres.jsonl:1" in str(exc.value)
        assert "url" in str(exc.value)


def test_genre_bad_type_rejected() -> None:
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        pkg = _write_genre_pkg(Path(d), [
            json.dumps(
                {
                    "genre_id": "g1",
                    "name": "G1",
                    "url": "https://e.org/g1",
                    "family": "Rock",
                    "parents": "not-an-array",
                    "eligible": True,
                    "source": "bad",
                }
            )
        ])
        with pytest.raises(InvalidInputError) as exc:
            GenreDatasetAdapter(pkg).list_eligible_genres()
        assert "parents" in str(exc.value)


def test_genre_duplicate_identity_rejected() -> None:
    import tempfile

    record = json.dumps(
        {
            "genre_id": "g1",
            "name": "G1",
            "url": "https://e.org/g1",
            "family": "Rock",
            "parents": ["rock"],
            "eligible": True,
            "source": "bad",
        }
    )
    with tempfile.TemporaryDirectory() as d:
        pkg = _write_genre_pkg(Path(d), [record, record])
        with pytest.raises(InvalidInputError) as exc:
            GenreDatasetAdapter(pkg).list_eligible_genres()
        assert "duplicate genre_id" in str(exc.value)
        assert "genres.jsonl:2" in str(exc.value)


def test_genre_bad_url_rejected() -> None:
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        pkg = _write_genre_pkg(Path(d), [
            json.dumps(
                {
                    "genre_id": "g1",
                    "name": "G1",
                    "url": "ftp://bad",
                    "family": "Rock",
                    "parents": ["rock"],
                    "eligible": True,
                    "source": "bad",
                }
            )
        ])
        with pytest.raises(InvalidInputError) as exc:
            GenreDatasetAdapter(pkg).list_eligible_genres()
        assert "url" in str(exc.value)


def test_genre_source_missing_license_rejected() -> None:
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        pkg = _write_genre_pkg(
            Path(d),
            [
                json.dumps(
                    {
                        "genre_id": "g1",
                        "name": "G1",
                        "url": "https://e.org/g1",
                        "family": "Rock",
                        "parents": [],
                        "eligible": True,
                        "source": "bad",
                    }
                )
            ],
            meta="""source_id: bad
display_name: Bad
origin_url: https://example.org
retrieved_at: 2026-08-20T00:00:00+00:00
dataset_version: v1
data_scope: test
records_file: genres.jsonl
""",
        )
        with pytest.raises(InvalidInputError) as exc:
            GenreDatasetAdapter(pkg).list_eligible_genres()
        assert "license" in str(exc.value)


def test_genre_bad_retrieved_time_rejected() -> None:
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        pkg = _write_genre_pkg(
            Path(d),
            [
                json.dumps(
                    {
                        "genre_id": "g1",
                        "name": "G1",
                        "url": "https://e.org/g1",
                        "family": "Rock",
                        "parents": [],
                        "eligible": True,
                        "source": "bad",
                    }
                )
            ],
            meta="""source_id: bad
display_name: Bad
license: CC0-1.0
origin_url: https://example.org
retrieved_at: yesterday
dataset_version: v1
data_scope: test
records_file: genres.jsonl
""",
        )
        with pytest.raises(InvalidInputError) as exc:
            GenreDatasetAdapter(pkg).list_eligible_genres()
        assert "retrieved_at" in str(exc.value)


def test_genre_jsonl_syntax_error_pinpoints_line() -> None:
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        pkg = _write_genre_pkg(Path(d), ["{not json", "{\"genre_id\": \"g1\"}"])
        with pytest.raises(InvalidInputError) as exc:
            GenreDatasetAdapter(pkg).list_eligible_genres()
        assert "genres.jsonl:1" in str(exc.value)


def _write_critic_pkg(tmp_path: Path, rows: list[list[str]]) -> Path:
    pkg = tmp_path / "critics" / "bad"
    pkg.mkdir(parents=True)
    (pkg / "source.yaml").write_text(
        """source_id: bad
display_name: Bad
license: CC0-1.0
origin_url: https://example.org
scrape_date: 2026-08-20
rating_scale_min: 1
rating_scale_max: 5
""",
        encoding="utf-8",
    )
    (pkg / "ratings.csv").write_text(
        "source_id,album_id,rating,rating_max,review_url\n"
        + "\n".join(",".join(row) for row in rows)
        + "\n",
        encoding="utf-8",
    )
    return pkg


def test_critic_csv_row_error_pinpoints_line() -> None:
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        pkg = _write_critic_pkg(
            Path(d),
            [["bad", "album-1", "9", "5", ""]],  # rating 9 outside scale [1,5]
        )
        with pytest.raises(InvalidInputError) as exc:
            CriticDatasetAdapter(pkg).all_ratings()
        assert "ratings.csv:2" in str(exc.value)
        assert "outside declared scale" in str(exc.value)


def test_critic_source_yaml_rating_mismatch_rejected() -> None:
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        pkg = _write_critic_pkg(
            Path(d),
            [["other-source", "album-1", "4", "5", ""]],  # source_id mismatch
        )
        with pytest.raises(InvalidInputError) as exc:
            CriticDatasetAdapter(pkg).all_ratings()
        assert "does not match source.yaml" in str(exc.value)


def test_critic_duplicate_identity_rejected() -> None:
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        pkg = _write_critic_pkg(
            Path(d),
            [["bad", "album-1", "4", "5", ""], ["bad", "album-1", "3", "5", ""]],
        )
        with pytest.raises(InvalidInputError) as exc:
            CriticDatasetAdapter(pkg).all_ratings()
        assert "duplicate" in str(exc.value)


def test_critic_bad_header_rejected() -> None:
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        pkg = Path(d) / "critics" / "bad"
        pkg.mkdir(parents=True)
        (pkg / "source.yaml").write_text(
            """source_id: bad
display_name: Bad
license: CC0-1.0
origin_url: https://example.org
scrape_date: 2026-08-20
rating_scale_min: 1
rating_scale_max: 5
""",
            encoding="utf-8",
        )
        (pkg / "ratings.csv").write_text(
            "source_id,album_id,rating\nbad,album-1,4\n", encoding="utf-8"
        )
        with pytest.raises(InvalidInputError) as exc:
            CriticDatasetAdapter(pkg).all_ratings()
        assert "ratings.csv:1" in str(exc.value)
        assert "header" in str(exc.value)


def test_critic_bad_type_rejected() -> None:
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        pkg = _write_critic_pkg(Path(d), [["bad", "album-1", "high", "5", ""]])
        with pytest.raises(InvalidInputError) as exc:
            CriticDatasetAdapter(pkg).all_ratings()
        assert "ratings.csv:2" in str(exc.value)
        assert "rating" in str(exc.value)


def test_critic_missing_license_rejected() -> None:
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        pkg = Path(d) / "critics" / "bad"
        pkg.mkdir(parents=True)
        (pkg / "source.yaml").write_text(
            """source_id: bad
display_name: Bad
origin_url: https://example.org
scrape_date: 2026-08-20
rating_scale_min: 1
rating_scale_max: 5
""",
            encoding="utf-8",
        )
        (pkg / "ratings.csv").write_text(
            "source_id,album_id,rating,rating_max,review_url\nbad,album-1,4,5,\n",
            encoding="utf-8",
        )
        with pytest.raises(InvalidInputError) as exc:
            CriticDatasetAdapter(pkg).all_ratings()
        assert "license" in str(exc.value)


def test_critic_bad_scrape_date_rejected() -> None:
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        pkg = Path(d) / "critics" / "bad"
        pkg.mkdir(parents=True)
        (pkg / "source.yaml").write_text(
            """source_id: bad
display_name: Bad
license: CC0-1.0
origin_url: https://example.org
scrape_date: not-a-date
rating_scale_min: 1
rating_scale_max: 5
""",
            encoding="utf-8",
        )
        (pkg / "ratings.csv").write_text(
            "source_id,album_id,rating,rating_max,review_url\nbad,album-1,4,5,\n",
            encoding="utf-8",
        )
        with pytest.raises(InvalidInputError) as exc:
            CriticDatasetAdapter(pkg).all_ratings()
        assert "scrape_date" in str(exc.value)


def test_critic_missing_records_file_rejected() -> None:
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        pkg = Path(d) / "critics" / "bad"
        pkg.mkdir(parents=True)
        (pkg / "source.yaml").write_text(
            """source_id: bad
display_name: Bad
license: CC0-1.0
origin_url: https://example.org
scrape_date: 2026-08-20
rating_scale_min: 1
rating_scale_max: 5
""",
            encoding="utf-8",
        )
        with pytest.raises(InvalidInputError) as exc:
            CriticDatasetAdapter(pkg).all_ratings()
        assert "ratings.csv missing" in str(exc.value)


def test_adapter_implements_existing_ports_structural() -> None:
    # Structural check: the adapters satisfy the accepted Port protocols via
    # duck typing (callable methods with the expected signatures); Core never
    # depends on the concrete adapters.
    import inspect

    genre_adapter = GenreDatasetAdapter(GENRE_PKG)
    critic_adapter = CriticDatasetAdapter(CRITIC_PKG)
    assert callable(genre_adapter.list_eligible_genres)
    assert callable(critic_adapter.ratings_for)
    genre_sig = inspect.signature(genre_adapter.list_eligible_genres)
    assert list(genre_sig.parameters) == []
    critic_sig = inspect.signature(critic_adapter.ratings_for)
    assert list(critic_sig.parameters) == ["album"]
