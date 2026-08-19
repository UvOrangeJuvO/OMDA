"""T1.2 schema acceptance and precise malformed-record rejection tests (SPEC §7-1)."""

from __future__ import annotations

import pytest

from omda.schemas import (
    PRODUCT_SEMANTIC_FIELDS,
    RecordValidationError,
    SchemaError,
    get_schema,
    load_schemas,
    validate,
)

EXPECTED_SCHEMAS = [
    "genre",
    "album",
    "critic_source",
    "critic_rating",
    "plan",
    "run_journal",
    "genre_pick_history",
    "album_history",
    "delivery_receipt",
    "config",
]


def test_all_required_schemas_are_loaded_and_versioned() -> None:
    schemas = load_schemas()
    assert set(EXPECTED_SCHEMAS) <= set(schemas)
    for name, schema in schemas.items():
        assert schema["schema_name"] == name
        assert isinstance(schema["schema_version"], int) and schema["schema_version"] >= 1
        assert isinstance(schema["fields"], dict)


def test_product_semantic_fields_flagged() -> None:
    # SPEC §2: changing product semantics/defaults requires an ADR; the registry flags them.
    assert {
        "daily_genre_count",
        "albums_per_genre",
        "genre_cooldown_picks",
        "modern_album_year",
    } == PRODUCT_SEMANTIC_FIELDS


def test_unknown_extra_fields_are_rejected_with_full_path() -> None:
    # G1-003: misspelled top-level fields must fail with field path evidence.
    record = {
        "genre_id": "ambient",
        "name": "Ambient",
        "url": "https://rateyourmusic.com/genre/Ambient/",
        "family": "Electronic",
        "parents": ["electronic"],
        "eligible": True,
        "source": "rym",
        "famliy": "Electronic",  # typo of "family"
    }
    with pytest.raises(RecordValidationError) as exc:
        validate("genre", record, "fixtures/genres.csv:1")
    assert any("famliy" in e and "unknown field" in e for e in exc.value.errors)
    assert exc.value.location == "fixtures/genres.csv:1"


def test_album_misspelled_canonical_field_is_rejected() -> None:
    bad = dict(VALID_ALBUM, canoncial_id="mb-1")  # typo of "canonical_id"
    with pytest.raises(RecordValidationError) as exc:
        validate("album", bad, "a.csv:1")
    assert any("canoncial_id" in e and "unknown field" in e for e in exc.value.errors)


def test_config_misspelled_semantic_field_is_rejected() -> None:
    bad = {"genre_cooldown_pick": 999}  # typo of "genre_cooldown_picks"
    with pytest.raises(RecordValidationError) as exc:
        validate("config", bad, "config.yaml:1")
    assert any("genre_cooldown_pick" in e and "unknown field" in e for e in exc.value.errors)


def test_nested_misspelled_field_is_rejected_with_path() -> None:
    bad = dict(VALID_CONFIG)
    bad["delivery"] = {"chanel": "pushplus"}  # typo of "channel"
    with pytest.raises(RecordValidationError) as exc:
        validate("config", bad, "config.yaml:1")
    assert any("delivery.chanel" in e and "unknown field" in e for e in exc.value.errors)


def test_nested_plan_item_misspelled_field_is_rejected() -> None:
    bad = dict(VALID_PLAN)
    bad["genres"] = [{"genre_id": "ambient", "pick_index": 1, "family": "Electronic", "famly": "X"}]
    with pytest.raises(RecordValidationError) as exc:
        validate("plan", bad, "plans/run-1.json:1")
    assert any("genres[0].famly" in e and "unknown field" in e for e in exc.value.errors)


def test_opt_in_additional_fields_allow_passes_extension() -> None:
    # Explicit, documented forward-compatibility policy (G1-003).
    permissive = {
        "schema_name": "permissive",
        "schema_version": 1,
        "additional_fields": "allow",
        "fields": {"id": {"type": "string", "required": True}},
    }
    from omda.schemas.validator import validate_record

    validate_record(permissive, {"id": "x", "future_field": 1}, "ext.json:1")


def test_invalid_additional_fields_policy_is_schema_error() -> None:
    from omda.schemas.validator import SchemaError, validate_record

    bad_schema = {
        "schema_name": "bad",
        "schema_version": 1,
        "additional_fields": "maybe",
        "fields": {},
    }
    with pytest.raises(SchemaError) as exc:
        validate_record(bad_schema, {})
    assert "bad.additional_fields" in str(exc.value)
    assert "'reject' or 'allow'" in str(exc.value)


def test_nested_one_level_invalid_policy_is_schema_error() -> None:
    from omda.schemas.validator import SchemaError, validate_record

    schema = {
        "schema_name": "nested1",
        "schema_version": 1,
        "fields": {
            "delivery": {
                "type": "object",
                "additional_fields": "typo",
                "fields": {"channel": {"type": "string", "required": True}},
            }
        },
    }
    with pytest.raises(SchemaError) as exc:
        validate_record(schema, {"delivery": {"channel": "markdown"}})
    assert "nested1.fields.delivery.additional_fields" in str(exc.value)
    assert "'reject' or 'allow'" in str(exc.value)


def test_multi_level_invalid_policy_is_schema_error() -> None:
    from omda.schemas.validator import SchemaError, validate_record

    schema = {
        "schema_name": "nested2",
        "schema_version": 1,
        "fields": {
            "outer": {
                "type": "object",
                "fields": {
                    "inner": {
                        "type": "object",
                        "additional_fields": "permissive",
                        "fields": {"x": {"type": "integer", "required": True}},
                    }
                },
            }
        },
    }
    with pytest.raises(SchemaError) as exc:
        validate_record(schema, {"outer": {"inner": {"x": 1}}})
    assert "nested2.fields.outer.fields.inner.additional_fields" in str(exc.value)


def test_nested_reject_rejects_unknown_fields() -> None:
    from omda.schemas.validator import RecordValidationError, validate_record

    schema = {
        "schema_name": "nest_reject",
        "schema_version": 1,
        "fields": {
            "delivery": {
                "type": "object",
                "fields": {"channel": {"type": "string", "required": True}},
            }
        },
    }
    with pytest.raises(RecordValidationError) as exc:
        validate_record(schema, {"delivery": {"channel": "markdown", "chanel": "x"}})
    assert any("delivery.chanel" in e and "unknown field" in e for e in exc.value.errors)


def test_nested_allow_accepts_unknown_fields() -> None:
    from omda.schemas.validator import validate_record

    schema = {
        "schema_name": "nest_allow",
        "schema_version": 1,
        "fields": {
            "delivery": {
                "type": "object",
                "additional_fields": "allow",
                "fields": {"channel": {"type": "string", "required": True}},
            }
        },
    }
    validate_record(schema, {"delivery": {"channel": "markdown", "future": 1}}, "x.json:1")


def test_schema_error_on_missing_schema_name() -> None:
    from omda.schemas.validator import validate_record

    with pytest.raises(SchemaError):
        validate_record({"schema_version": 1, "fields": {}}, {})


# --- genre ---

VALID_GENRE = {
    "genre_id": "ambient",
    "name": "Ambient",
    "url": "https://rateyourmusic.com/genre/Ambient/",
    "family": "Electronic",
    "parents": ["electronic"],
    "eligible": True,
    "source": "rym",
}


def test_genre_valid() -> None:
    validate("genre", VALID_GENRE, "data/genres/sample.jsonl:1")


def test_genre_missing_required_field() -> None:
    with pytest.raises(RecordValidationError) as exc:
        validate("genre", {k: v for k, v in VALID_GENRE.items() if k != "eligible"}, "g.csv:1")
    assert any("eligible" in e and "missing required" in e for e in exc.value.errors)
    assert exc.value.location == "g.csv:1"


def test_genre_bad_type_and_pattern() -> None:
    bad = dict(VALID_GENRE)
    bad["eligible"] = "yes"
    with pytest.raises(RecordValidationError) as exc:
        validate("genre", bad, "g.csv:1")
    assert any("eligible" in e and "expected boolean" in e for e in exc.value.errors)

    bad2 = dict(VALID_GENRE)
    bad2["genre_id"] = "UPPER CASE"
    with pytest.raises(RecordValidationError) as exc2:
        validate("genre", bad2, "g.csv:1")
    assert any("genre_id" in e and "pattern" in e for e in exc2.value.errors)


# --- album ---

VALID_ALBUM = {
    "album_id": "alb-0001",
    "title": "Selected Ambient Works",
    "artist": "Aphex Twin",
    "year": 1994,
    "url": "https://example.org/a/1",
    "genres": ["ambient"],
}


def test_album_valid_and_year_bounds() -> None:
    validate("album", VALID_ALBUM, "a.csv:1")
    bad = dict(VALID_ALBUM, year=1800)
    with pytest.raises(RecordValidationError) as exc:
        validate("album", bad, "a.csv:1")
    assert any("year" in e and "less than min" in e for e in exc.value.errors)


def test_album_identity_enum() -> None:
    bad = dict(VALID_ALBUM, identity_confidence="guess")
    with pytest.raises(RecordValidationError) as exc:
        validate("album", bad, "a.csv:1")
    assert any("identity_confidence" in e and "not in enum" in e for e in exc.value.errors)


# --- critic_source / critic_rating ---

VALID_CRITIC_SOURCE = {
    "source_id": "pitchfork",
    "display_name": "Pitchfork",
    "license": "CC-BY-NC-4.0",
    "origin_url": "https://pitchfork.com/",
    "scrape_date": "2026-08-01",
    "rating_scale_min": 0.0,
    "rating_scale_max": 10.0,
}


def test_critic_source_valid_and_date_format() -> None:
    validate("critic_source", VALID_CRITIC_SOURCE, "critics/pitchfork/source.yaml:1")
    bad = dict(VALID_CRITIC_SOURCE, scrape_date="01-08-2026")
    with pytest.raises(RecordValidationError) as exc:
        validate("critic_source", bad, "critics/pitchfork/source.yaml:1")
    assert any("scrape_date" in e and "iso8601-date" in e for e in exc.value.errors)


def test_critic_rating_valid_and_number_type() -> None:
    validate("critic_rating", {"source_id": "pitchfork", "album_id": "alb-0001", "rating": 8.5})
    with pytest.raises(RecordValidationError) as exc:
        validate(
            "critic_rating",
            {"source_id": "pitchfork", "album_id": "alb-0001", "rating": "8.5"},
        )
    assert any("rating" in e and "expected number" in e for e in exc.value.errors)


# --- plan (nested object arrays) ---

VALID_PLAN = {
    "plan_id": "plan-001",
    "run_id": "run-20260819-0001",
    "created_at": "2026-08-19T09:00:00+00:00",
    "seed": "abc123",
    "input_data_version": "genre-catalog-2026-08-19",
    "genres": [{"genre_id": "ambient", "pick_index": 1, "family": "Electronic"}],
    "albums": [
        {
            "album_id": "alb-0001",
            "genre_id": "ambient",
            "title": "Selected Ambient Works",
            "artist": "Aphex Twin",
            "year": 1994,
        }
    ],
}


def test_plan_valid_and_nested_required_field() -> None:
    validate("plan", VALID_PLAN, "plans/run-1.json:1")
    bad = dict(VALID_PLAN)
    bad["genres"] = [{"genre_id": "ambient", "family": "Electronic"}]  # missing pick_index
    with pytest.raises(RecordValidationError) as exc:
        validate("plan", bad, "plans/run-1.json:1")
    assert any("pick_index" in e and "missing required" in e for e in exc.value.errors)


# --- run_journal ---

def test_run_journal_transition_enum() -> None:
    base = {"run_id": "run-1", "at": "2026-08-19T09:00:00+00:00"}
    validate("run_journal", {"journal_id": 1, "transition": "PLANNED", **base}, "journal.jsonl:1")
    with pytest.raises(RecordValidationError) as exc:
        validate(
            "run_journal",
            {"journal_id": 1, "transition": "STARTED", **base},
            "journal.jsonl:1",
        )
    assert any("transition" in e and "not in enum" in e for e in exc.value.errors)


# --- history records ---

def test_pick_history_index_bounds() -> None:
    base = {"run_id": "run-1", "genre_id": "ambient", "committed_at": "2026-08-19T09:00:00+00:00"}
    validate("genre_pick_history", {"pick_index": 31, **base})
    with pytest.raises(RecordValidationError) as exc:
        validate("genre_pick_history", {"pick_index": 0, **base})
    assert any("pick_index" in e and "less than min" in e for e in exc.value.errors)


def test_album_history_datetime_format() -> None:
    with pytest.raises(RecordValidationError) as exc:
        validate(
            "album_history",
            {"album_id": "alb-1", "run_id": "run-1", "recommended_at": "2026-08-19"},
            "history.jsonl:1",
        )
    assert any("recommended_at" in e and "iso8601-datetime" in e for e in exc.value.errors)


# --- delivery_receipt ---

def test_delivery_receipt_enum_and_required() -> None:
    validate(
        "delivery_receipt",
        {
            "run_id": "run-1",
            "idempotency_key": "run-1/markdown",
            "delivered_at": "2026-08-19T09:00:00+00:00",
            "channel": "markdown",
            "status": "ok",
        },
        "receipts/run-1.json:1",
    )
    with pytest.raises(RecordValidationError) as exc:
        validate(
            "delivery_receipt",
            {
                "run_id": "run-1",
                "idempotency_key": "run-1/markdown",
                "delivered_at": "2026-08-19T09:00:00+00:00",
                "channel": "email",
                "status": "ok",
            },
            "receipts/run-1.json:1",
        )
    assert any("channel" in e and "not in enum" in e for e in exc.value.errors)


# --- config ---

VALID_CONFIG = {
    "daily_genre_count": 3,
    "albums_per_genre": 3,
    "genre_cooldown_picks": 30,
    "modern_album_year": 2010,
    "seed": "deterministic-seed",
    "delivery": {"channel": "markdown", "pushplus_token_env": "PUSHPLUS_TOKEN"},
}


def test_config_valid_and_nested_enum() -> None:
    validate("config", VALID_CONFIG, "config.yaml:1")
    bad = dict(VALID_CONFIG)
    bad["delivery"] = {"channel": "email"}
    with pytest.raises(RecordValidationError) as exc:
        validate("config", bad, "config.yaml:1")
    assert any("channel" in e and "not in enum" in e for e in exc.value.errors)


def test_get_schema_unknown_raises_key_error() -> None:
    with pytest.raises(KeyError):
        get_schema("does_not_exist")
