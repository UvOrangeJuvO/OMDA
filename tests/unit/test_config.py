"""T1.3 layered configuration tests (defaults, precedence, validation, semantics)."""

from __future__ import annotations

import json

import pytest

from omda.config import (
    DEFAULT_ALBUMS_PER_GENRE,
    DEFAULT_DAILY_GENRE_COUNT,
    DEFAULT_GENRE_COOLDOWN_PICKS,
    DEFAULT_MODERN_ALBUM_YEAR,
    Config,
    config_to_dict,
    load_config,
    semantic_overrides,
)
from omda.schemas import RecordValidationError


def test_defaults_match_spec_constants() -> None:
    cfg = load_config()
    assert cfg.daily_genre_count == DEFAULT_DAILY_GENRE_COUNT == 3
    assert cfg.albums_per_genre == DEFAULT_ALBUMS_PER_GENRE == 3
    assert cfg.genre_cooldown_picks == DEFAULT_GENRE_COOLDOWN_PICKS == 30
    assert cfg.modern_album_year == DEFAULT_MODERN_ALBUM_YEAR == 2010
    assert cfg.delivery.channel == "markdown"
    assert semantic_overrides(cfg) == []


def test_file_then_overrides_precedence(tmp_path) -> None:
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"daily_genre_count": 5, "delivery": {"channel": "pushplus"}}))
    cfg = load_config(config_path=path, overrides={"albums_per_genre": 2})
    assert cfg.daily_genre_count == 5  # from file
    assert cfg.albums_per_genre == 2  # override beats file
    assert cfg.delivery.channel == "pushplus"
    assert cfg.delivery.pushplus_token_env is None


def test_missing_config_file_is_not_an_error() -> None:
    cfg = load_config(config_path=None)
    assert cfg == Config()


def test_invalid_json_reports_path(tmp_path) -> None:
    path = tmp_path / "config.json"
    path.write_text("{not json")
    with pytest.raises(ValueError, match="invalid JSON"):
        load_config(config_path=path)


def test_schema_rejects_invalid_values(tmp_path) -> None:
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"genre_cooldown_picks": 0}))
    with pytest.raises(RecordValidationError) as exc:
        load_config(config_path=path)
    assert any("genre_cooldown_picks" in e for e in exc.value.errors)


def test_semantic_overrides_flag_product_changes() -> None:
    cfg = load_config(overrides={"modern_album_year": 2015, "albums_per_genre": 4})
    assert semantic_overrides(cfg) == ["albums_per_genre", "modern_album_year"]


def test_config_round_trip_through_mapping() -> None:
    cfg = load_config(
        overrides={
            "seed": "fixed-seed",
            "delivery": {"channel": "pushplus", "pushplus_token_env": "PUSHPLUS_TOKEN"},
        }
    )
    mapping = config_to_dict(cfg)
    assert mapping["seed"] == "fixed-seed"
    assert mapping["delivery"] == {"channel": "pushplus", "pushplus_token_env": "PUSHPLUS_TOKEN"}
    assert load_config(overrides=mapping) == cfg


# --- G2-011: genre_parent_limits are value-validated and immutable ------------


@pytest.mark.parametrize(
    "bad_value",
    [
        "one",        # string
        -1,           # negative
        0,            # zero would permanently starve a parent
        1.5,          # float
        True,         # bool is not an integer
        {"nested": 1},  # nested object
    ],
    ids=["string", "negative", "zero", "float", "bool", "nested-object"],
)
def test_invalid_parent_limit_rejected_at_exact_path(bad_value) -> None:
    with pytest.raises(RecordValidationError) as exc:
        load_config(overrides={"genre_parent_limits": {"electronic": bad_value}})
    assert any(
        "genre_parent_limits.electronic" in e for e in exc.value.errors
    ), exc.value.errors


def test_valid_parent_limits_load_and_round_trip() -> None:
    cfg = load_config(overrides={"genre_parent_limits": {"electronic": 1, "jazz": 2}})
    assert cfg.genre_parent_limits["electronic"] == 1
    assert cfg.genre_parent_limits["jazz"] == 2
    assert load_config(overrides=config_to_dict(cfg)) == cfg


def test_original_overrides_mutation_cannot_alter_config() -> None:
    overrides = {"genre_parent_limits": {"electronic": 1}}
    cfg = load_config(overrides=overrides)
    overrides["genre_parent_limits"]["electronic"] = 9
    assert cfg.genre_parent_limits["electronic"] == 1


def test_config_parent_limits_are_immutable() -> None:
    cfg = load_config(overrides={"genre_parent_limits": {"electronic": 1}})
    with pytest.raises(TypeError):
        cfg.genre_parent_limits["electronic"] = 5  # MappingProxyType is read-only


def test_fingerprint_matches_exact_config_snapshot_used_for_selection() -> None:
    # The journaled config fingerprint is derived from the immutable snapshot,
    # so it always equals the constraints actually applied (G2-011).
    from tests.fakes import FakeAlbumSource, FakeDelivery, FakeGenreSource, FakeLLM, InMemoryHistory

    from omda.orchestrator.run import RunEngine, _config_fingerprint
    from omda.ports.domain import GenreRef

    genres = [GenreRef("g1", "G1", "Electronic", parents=("electronic",))]
    cfg = load_config(overrides={"genre_parent_limits": {"electronic": 1}})
    engine = RunEngine(
        config=cfg,
        history=InMemoryHistory(),
        genre_source=FakeGenreSource(genres),
        album_source=FakeAlbumSource({}),
        llm=FakeLLM("x"),
        delivery=FakeDelivery(),
        seed="fp-check",
    )
    assert engine._config_version == _config_fingerprint(cfg)
