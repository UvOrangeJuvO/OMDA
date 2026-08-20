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
    DeliveryConfig,
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


# --- G2-011 re-review: EVERY Config construction path is immutable -------------


def test_direct_config_default_is_immutable() -> None:
    cfg = Config()
    with pytest.raises(TypeError):
        cfg.genre_parent_limits["p"] = 2  # MappingProxyType is read-only


def test_direct_config_with_caller_dict_is_immutable_and_detached() -> None:
    caller_dict = {"electronic": 1}
    cfg = Config(genre_parent_limits=caller_dict)
    # Mutating the caller-owned dict must NOT change Config.
    caller_dict["electronic"] = 9
    assert cfg.genre_parent_limits["electronic"] == 1
    # Mutating the exposed mapping must be impossible.
    with pytest.raises(TypeError):
        cfg.genre_parent_limits["electronic"] = 5


def test_direct_config_runengine_fingerprint_matches_selection_rules() -> None:
    from tests.fakes import FakeAlbumSource, FakeDelivery, FakeGenreSource, FakeLLM, InMemoryHistory

    from omda.orchestrator.run import RunEngine, _config_fingerprint
    from omda.ports.domain import GenreRef

    caller_dict = {"electronic": 1}
    cfg = Config(genre_parent_limits=caller_dict)
    # Caller mutates AFTER engine construction: effective rules must not change.
    caller_dict["electronic"] = 9
    genres = [GenreRef("g1", "G1", "Electronic", parents=("electronic",))]
    engine = RunEngine(
        config=cfg,
        history=InMemoryHistory(),
        genre_source=FakeGenreSource(genres),
        album_source=FakeAlbumSource({}),
        llm=FakeLLM("x"),
        delivery=FakeDelivery(),
        seed="direct-config",
    )
    assert cfg.genre_parent_limits["electronic"] == 1  # snapshot frozen
    assert engine._config_version == _config_fingerprint(cfg)


# --- G2-011 re-review 4: direct Config invalid values are rejected ------------


@pytest.mark.parametrize(
    "bad_value",
    [
        "one",        # string
        True,         # bool is not an integer
        1.5,          # float
        0,            # zero would permanently starve a parent
        -1,           # negative
        11,           # above the documented safe range (max 10)
    ],
    ids=["string", "bool", "float", "zero", "negative", "out-of-range"],
)
def test_direct_config_rejects_invalid_parent_values(bad_value) -> None:
    # Direct Config(...) must reject invalid parent limits with a CONTROLLED
    # ValueError (not an uncaught built-in later in a run), with a precise path.
    with pytest.raises(ValueError) as exc:
        Config(genre_parent_limits={"electronic": bad_value})
    assert "genre_parent_limits" in str(exc.value)


def test_invalid_direct_config_never_reaches_planned() -> None:
    # An engine built from an invalid direct Config must fail BEFORE any run
    # journal is written (no PLANNED entry, no uncaught TypeError).

    with pytest.raises(ValueError):
        Config(genre_parent_limits={"electronic": "one"})
    # The invalid value cannot construct a Config at all, so no engine exists.


# --- G2-011 re-review 5: complete Config validation boundary -------------------


@pytest.mark.parametrize(
    "kwargs",
    [
        {"daily_genre_count": "three"},  # string for integer
        {"daily_genre_count": True},     # bool-as-int
        {"albums_per_genre": 0},         # below min
        {"albums_per_genre": 11},        # above max
        {"genre_cooldown_picks": False},  # bool-as-int
        {"modern_album_year": "new"},    # string for integer
        {"modern_album_year": 1800},     # below min
        {"seed": ""},                    # below min_length
    ],
    ids=[
        "daily-count-string",
        "daily-count-bool",
        "albums-zero",
        "albums-over-max",
        "cooldown-bool",
        "year-string",
        "year-below-min",
        "seed-empty",
    ],
)
def test_direct_config_rejects_invalid_schema_fields(kwargs) -> None:
    # EVERY direct Config(...) field must cross the committed config schema
    # boundary: controlled rejection before any run journal (G2-011).
    with pytest.raises(ValueError) as exc:
        Config(**kwargs)
    assert "config" in str(exc.value)  # RecordValidationError message carries schema name


def test_direct_config_rejects_invalid_delivery_channel() -> None:
    with pytest.raises(ValueError):
        Config(delivery=DeliveryConfig(channel="bogus"))


def test_direct_delivery_config_rejects_invalid_channel() -> None:
    from omda.config import DeliveryConfig

    with pytest.raises(ValueError):
        DeliveryConfig(channel="bogus")


def test_direct_config_valid_round_trip() -> None:
    cfg = Config(
        daily_genre_count=4,
        albums_per_genre=5,
        genre_cooldown_picks=40,
        modern_album_year=2015,
        seed="s",
        genre_parent_limits={"electronic": 2},
        delivery=DeliveryConfig(channel="pushplus", pushplus_token_env="PUSHPLUS_TOKEN"),
    )
    mapping = config_to_dict(cfg)
    assert mapping["daily_genre_count"] == 4
    assert mapping["delivery"]["channel"] == "pushplus"
    # A direct valid Config reproduces exactly through the factory.
    assert load_config(overrides=mapping) == cfg


# --- G2-011 re-review 6: exact null and nested-type validation -----------------


@pytest.mark.parametrize(
    "field",
    ["daily_genre_count", "albums_per_genre", "genre_cooldown_picks", "modern_album_year"],
    ids=["daily", "albums", "cooldown", "year"],
)
def test_direct_config_rejects_none_for_non_nullable_fields(field) -> None:
    # A direct None for a NON-nullable semantic field must be rejected with a
    # controlled validation error (not silently dropped by a generic normalise).
    with pytest.raises(ValueError) as exc:
        Config(**{field: None})
    assert "config" in str(exc.value)  # controlled RecordValidationError


def test_direct_config_rejects_none_parent_limits_controlled() -> None:
    with pytest.raises(ValueError) as exc:
        Config(genre_parent_limits=None)
    assert "genre_parent_limits" in str(exc.value)  # ValueError, never TypeError


def test_direct_config_rejects_dict_delivery_controlled() -> None:
    # A raw dict in place of DeliveryConfig must fail controlled, not AttributeError.
    with pytest.raises(ValueError) as exc:
        Config(delivery={"channel": "markdown"})
    assert "delivery" in str(exc.value)


def test_direct_config_rejects_none_delivery() -> None:
    with pytest.raises(ValueError):
        Config(delivery=None)


def test_direct_delivery_config_rejects_non_string_env_type() -> None:
    # Invalid TYPE for pushplus_token_env: controlled ValueError, never regex TypeError.
    with pytest.raises(ValueError) as exc:
        DeliveryConfig(pushplus_token_env=123)
    assert "pushplus_token_env" in str(exc.value)


def test_direct_config_valid_unset_optionals_round_trip() -> None:
    # seed and pushplus_token_env may be omitted/unset; everything else defaults.
    cfg = Config(seed=None, delivery=DeliveryConfig(pushplus_token_env=None))
    assert cfg.seed is None
    assert cfg.delivery.pushplus_token_env is None
    assert load_config(overrides=config_to_dict(cfg)) == cfg
