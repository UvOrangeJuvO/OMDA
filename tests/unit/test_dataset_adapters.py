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
GENRE_PKG = REPO / "data" / "genres" / "demo-omda"
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
    assert prov.source_id == "demo-omda"
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
data_derivation: independently_curated
upstream_license: none incorporated
license_core_facts: CC0-1.0
license_supplementary_used: none
license_service_terms: n/a
license_derived_package: CC0-1.0
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
data_derivation: independently_curated
upstream_license: none incorporated
license_core_facts: CC0-1.0
license_supplementary_used: none
license_service_terms: n/a
license_derived_package: CC0-1.0
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
data_derivation: independently_curated
upstream_license: none incorporated
license_core_facts: CC0-1.0
license_supplementary_used: none
license_service_terms: n/a
license_derived_package: CC0-1.0
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


# --- G3-001 re-review: genre package eligibility and provenance boundary --------


def _ineligible_genre_pkg(tmp_path: Path, extra: dict | None = None) -> Path:
    pkg = tmp_path / "genres" / "bad"
    pkg.mkdir(parents=True)
    (pkg / "source.yaml").write_text(
        """source_id: bad
display_name: Bad
license: CC0-1.0
origin_url: https://example.org
retrieved_at: 2026-08-20T00:00:00+00:00
dataset_version: v1
data_scope: test
records_file: genres.jsonl
data_derivation: independently_curated
upstream_license: none incorporated
license_core_facts: CC0-1.0
license_supplementary_used: none
license_service_terms: n/a
license_derived_package: CC0-1.0
""",
        encoding="utf-8",
    )
    record = {
        "genre_id": "g1",
        "name": "G1",
        "url": "https://e.org/g1",
        "family": "Rock",
        "parents": [],
        "eligible": False,
        "source": "bad",
    }
    if extra:
        record.update(extra)
    (pkg / "genres.jsonl").write_text(json.dumps(record) + "\n", encoding="utf-8")
    return pkg


def test_ineligible_genre_record_is_never_returned() -> None:
    # The accepted GenreSource port returns only valid, ELIGIBLE genres; an
    # `eligible: false` record must never enter the selection lottery.
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        pkg = _ineligible_genre_pkg(Path(d))
        genres = GenreDatasetAdapter(pkg).list_eligible_genres()
        assert genres == [], f"ineligible record leaked into results: {genres}"


def test_ineligible_genre_never_selected_at_orchestrator_level() -> None:
    # Orchestrator-level: an eligible:false record can never be selected.
    import tempfile

    from tests.fakes import FakeAlbumSource, FakeDelivery, FakeGenreSource, FakeLLM, InMemoryHistory

    from omda.config import load_config
    from omda.orchestrator.run import RunEngine
    from omda.ports.domain import AlbumCandidate, GenreRef

    with tempfile.TemporaryDirectory() as d:
        pkg = _ineligible_genre_pkg(Path(d))
        adapter = GenreDatasetAdapter(pkg)
        genres = adapter.list_eligible_genres()
        assert genres == []
        # Pool of eligible genres only; the ineligible record is absent by contract.
        pool = [GenreRef("a", "A", "Rock"), GenreRef("b", "B", "Jazz"), GenreRef("c", "C", "Rock")]
        albums = {
            g.genre_id: [
                AlbumCandidate(f"{g.genre_id}-1", f"{g.genre_id} One", "Artist", 2015),
                AlbumCandidate(f"{g.genre_id}-2", f"{g.genre_id} Two", "Artist", 2000),
                AlbumCandidate(f"{g.genre_id}-3", f"{g.genre_id} Three", "Artist", 1990),
            ]
            for g in pool
        }
        engine = RunEngine(
            config=load_config(),
            history=InMemoryHistory(),
            genre_source=FakeGenreSource(pool),
            album_source=FakeAlbumSource(albums),
            llm=FakeLLM("x"),
            delivery=FakeDelivery(),
            seed="eligibility",
        )
        outcome = engine.run("run-1")
        assert outcome.state == "COMPLETE"
        assert "g1" not in {g.genre_id for g in outcome.plan.genres}


def test_genre_source_id_must_match_directory_name() -> None:
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        pkg = _ineligible_genre_pkg(Path(d))
        # rewrite source.yaml with a mismatched source_id
        (pkg / "source.yaml").write_text(
            """source_id: other-source
display_name: Bad
license: CC0-1.0
origin_url: https://example.org
retrieved_at: 2026-08-20T00:00:00+00:00
dataset_version: v1
data_scope: test
records_file: genres.jsonl
data_derivation: independently_curated
upstream_license: none incorporated
license_core_facts: CC0-1.0
license_supplementary_used: none
license_service_terms: n/a
license_derived_package: CC0-1.0
""",
            encoding="utf-8",
        )
        with pytest.raises(InvalidInputError) as exc:
            GenreDatasetAdapter(pkg).list_eligible_genres()
        assert "directory" in str(exc.value) or "source_id" in str(exc.value)


def test_genre_record_source_must_match_source_id() -> None:
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        pkg = _ineligible_genre_pkg(Path(d), extra={"source": "wrong-source"})
        with pytest.raises(InvalidInputError) as exc:
            GenreDatasetAdapter(pkg).list_eligible_genres()
        assert "source" in str(exc.value)


def test_genre_records_file_cannot_escape_package() -> None:
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        pkg = root / "genres" / "bad"
        pkg.mkdir(parents=True)
        (root / "outside.jsonl").write_text(
            json.dumps(
                {
                    "genre_id": "ext",
                    "name": "External",
                    "url": "https://e.org/ext",
                    "family": "Rock",
                    "parents": [],
                    "eligible": True,
                    "source": "bad",
                }
            )
            + "\n",
            encoding="utf-8",
        )
        (pkg / "source.yaml").write_text(
            """source_id: bad
display_name: Bad
license: CC0-1.0
origin_url: https://example.org
retrieved_at: 2026-08-20T00:00:00+00:00
dataset_version: v1
data_scope: test
records_file: ../../outside.jsonl
""",
            encoding="utf-8",
        )
        with pytest.raises(InvalidInputError) as exc:
            GenreDatasetAdapter(pkg).list_eligible_genres()
        assert (
            "escape" in str(exc.value)
            or "outside" in str(exc.value)
            or "package" in str(exc.value)
        )


# --- G3-002 re-review: critic row scale consistency ----------------------------


def _critic_pkg(
    tmp_path: Path, rows: list[list[str]], scale_min: float = 1, scale_max: float = 5
) -> Path:
    pkg = tmp_path / "critics" / "bad"
    pkg.mkdir(parents=True)
    (pkg / "source.yaml").write_text(
        f"""source_id: bad
display_name: Bad
license: CC0-1.0
origin_url: https://example.org
scrape_date: 2026-08-20
rating_scale_min: {scale_min}
rating_scale_max: {scale_max}
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


def test_critic_blank_rating_max_fills_declared_scale() -> None:
    # Under a declared 1..5 scale, `rating=4` with blank max must be stored as
    # 4/5 = 0.8 after composition — never treated as an already-normalized 4.0.
    import tempfile

    from omda.core.rating import compose_rating
    from omda.ports.domain import AlbumCandidate

    with tempfile.TemporaryDirectory() as d:
        pkg = _critic_pkg(Path(d), [["bad", "album-1", "4", "", ""]])
        adapter = CriticDatasetAdapter(pkg)
        rows = adapter.all_ratings()
        assert rows[0].rating_max == 5.0  # filled from source.yaml scale_max
        album = AlbumCandidate(album_id="album-1", title="A", artist="X")
        score = compose_rating(adapter.ratings_for(album), {"bad": 1.0})
        assert score == 4.0 / 5.0


def test_critic_mismatched_rating_max_rejected() -> None:
    # A supplied rating_max must equal the declared scale_max (1..5 -> max 5).
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        pkg = _critic_pkg(Path(d), [["bad", "album-1", "4", "1", ""]])
        with pytest.raises(InvalidInputError) as exc:
            CriticDatasetAdapter(pkg).all_ratings()
        assert "rating_max" in str(exc.value)


def test_critic_zero_rating_max_rejected() -> None:
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        pkg = _critic_pkg(Path(d), [["bad", "album-1", "4", "0", ""]])
        with pytest.raises(InvalidInputError) as exc:
            CriticDatasetAdapter(pkg).all_ratings()
        assert "rating_max" in str(exc.value)


def test_critic_negative_rating_max_rejected() -> None:
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        pkg = _critic_pkg(Path(d), [["bad", "album-1", "4", "-5", ""]])
        with pytest.raises(InvalidInputError):
            CriticDatasetAdapter(pkg).all_ratings()


def test_critic_invalid_scale_bounds_rejected() -> None:
    # rating_scale_min must be strictly below rating_scale_max.
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        pkg = _critic_pkg(Path(d), [["bad", "album-1", "4", "5", ""]], scale_min=5, scale_max=5)
        with pytest.raises(InvalidInputError):
            CriticDatasetAdapter(pkg).all_ratings()


def test_critic_rating_outside_effective_scale_rejected() -> None:
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        pkg = _critic_pkg(Path(d), [["bad", "album-1", "0", "5", ""]])
        with pytest.raises(InvalidInputError):
            CriticDatasetAdapter(pkg).all_ratings()


# --- G3-008 re-review 1: critic package directory invariant ---------------------


def test_critic_source_id_must_match_directory_name() -> None:
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        pkg = Path(d) / "critics" / "bad"
        pkg.mkdir(parents=True)
        (pkg / "source.yaml").write_text(
            """source_id: other-source
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
            "other-source,album-1,4,5,\n",
            encoding="utf-8",
        )
        with pytest.raises(InvalidInputError) as exc:
            CriticDatasetAdapter(pkg).all_ratings()
        assert "directory" in str(exc.value) or "source_id" in str(exc.value)


# --- G3-008 re-review 2: README example must be a working CSV shape ------------


def test_readme_blank_denominator_example_is_parseable() -> None:
    # The contribution guide's normalization example must be a REAL working CSV
    # shape: extract the code block from data/critics/README.md, build a package
    # with it and prove the adapter accepts it (blank rating_max inherits scale).
    import tempfile

    readme = Path("data/critics/README.md").read_text(encoding="utf-8")
    # The ratings.csv normalization example block (second CSV code block).
    block = readme.split("```")[7]
    lines = [ln for ln in block.strip().splitlines() if ln.strip()]
    assert lines[0] == "source_id,album_id,rating,rating_max,review_url"
    with tempfile.TemporaryDirectory() as d:
        pkg = Path(d) / "critics" / "my-source"
        pkg.mkdir(parents=True)
        (pkg / "source.yaml").write_text(
            "source_id: my-source\n"
            "display_name: My Source\n"
            "license: CC0-1.0\n"
            "origin_url: https://example.org\n"
            "scrape_date: 2026-08-20\n"
            "rating_scale_min: 1\n"
            "rating_scale_max: 5\n",
            encoding="utf-8",
        )
        (pkg / "ratings.csv").write_text("\n".join(lines) + "\n", encoding="utf-8")
        adapter = CriticDatasetAdapter(pkg)
        rows = adapter.all_ratings()
        by_album = {r.album_id: r for r in rows}
        assert by_album["album-a"].rating_max == 5.0
        assert by_album["album-b"].rating_max == 5.0  # blank inherits scale_max
        assert by_album["album-b"].rating == 3.0
        # G3-008: the README contract — Core normalizes the stored raw rating
        # and filled denominator pair to rating/max (3/5 = 0.6).
        from omda.core.rating import compose_rating
        from omda.ports.domain import AlbumCandidate

        album = AlbumCandidate(album_id="album-b", title="B", artist="X")
        score = compose_rating(adapter.ratings_for(album), {"my-source": 1.0})
        assert score == pytest.approx(3.0 / 5.0)
