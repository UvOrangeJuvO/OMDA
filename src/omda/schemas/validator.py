"""Dependency-free validator for versioned record schemas.

Schemas are declarative JSON documents stored in ``data/schemas/*.schema.json``
(the Git-reviewable community source of truth). This module contains no third-party
imports and validates records field-by-field so errors identify the offending record
and field (SPEC §3.3).
"""

from __future__ import annotations

import json
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any

# src/omda/schemas/validator.py -> parents[0]=schemas, [1]=omda, [2]=src, [3]=repo root
DEFAULT_SCHEMA_DIR = Path(__file__).resolve().parents[3] / "data" / "schemas"

_SUPPORTED_TYPES = frozenset({"string", "integer", "number", "boolean", "array", "object", "null"})
_SUPPORTED_FORMATS = frozenset({"iso8601-date", "iso8601-datetime"})

# Core product semantics defaults (SPEC §2). Config may override values, but changing
# product semantics/defaults requires an ADR — flagged here for reference/tests.
PRODUCT_SEMANTIC_FIELDS = frozenset(
    {"daily_genre_count", "albums_per_genre", "genre_cooldown_picks", "modern_album_year"}
)


class SchemaError(ValueError):
    """A schema document itself is malformed (missing name/version/bad constraints)."""


class RecordValidationError(ValueError):
    """A record failed validation against a schema.

    ``errors`` is a list of human-readable, field-precise messages. ``location``
    identifies the offending record (e.g. file path + row).
    """

    def __init__(self, schema_name: str, location: str, errors: list[str]) -> None:
        self.schema_name = schema_name
        self.location = location
        self.errors = errors
        super().__init__(f"{schema_name}@{location}: " + "; ".join(errors))


def _type_matches(value: Any, type_name: str) -> bool:
    if type_name == "string":
        return isinstance(value, str)
    if type_name == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if type_name == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if type_name == "boolean":
        return isinstance(value, bool)
    if type_name == "array":
        return isinstance(value, list)
    if type_name == "object":
        return isinstance(value, dict)
    if type_name == "null":
        return value is None
    return False


def _check_format(value: str, fmt: str) -> bool:
    if fmt == "iso8601-date":
        try:
            date.fromisoformat(value)
            return True
        except ValueError:
            return False
    if fmt == "iso8601-datetime":
        # Python 3.11+ fromisoformat also accepts date-only strings; an ISO 8601
        # datetime must carry a time-of-day component separated by 'T'.
        if "T" not in value:
            return False
        try:
            datetime.fromisoformat(value.replace("Z", "+00:00"))
            return True
        except ValueError:
            return False
    raise SchemaError(f"unsupported format {fmt!r}")


def _validate_policy(policy: Any, schema_path: str) -> None:
    """Validate an ``additional_fields`` policy value at any object scope (G1-003).

    Raises ``SchemaError`` with the full schema path so a schema-author typo can
    never silently disable strict validation for a nested object.
    """
    if policy not in ("reject", "allow"):
        raise SchemaError(
            f"{schema_path}: additional_fields must be 'reject' or 'allow', got {policy!r}"
        )


def _validate_value(
    path: str,
    value: Any,
    spec: dict[str, Any],
    errors: list[str],
    schema_path: str = "",
) -> None:
    type_name = spec.get("type", "string")
    if type_name not in _SUPPORTED_TYPES:
        raise SchemaError(f"{schema_path or path}: unsupported type {type_name!r}")

    if not _type_matches(value, type_name):
        errors.append(f"{path}: expected {type_name}, got {type(value).__name__}")
        return

    if type_name == "string":
        assert isinstance(value, str)
        if "pattern" in spec and re.search(spec["pattern"], value) is None:
            errors.append(f"{path}: does not match pattern {spec['pattern']!r}")
        if "enum" in spec and value not in spec["enum"]:
            errors.append(f"{path}: value {value!r} not in enum {spec['enum']!r}")
        if "format" in spec and not _check_format(value, spec["format"]):
            errors.append(f"{path}: invalid {spec['format']} format")
        if "min_length" in spec and len(value) < spec["min_length"]:
            errors.append(f"{path}: shorter than min_length {spec['min_length']}")
        if "max_length" in spec and len(value) > spec["max_length"]:
            errors.append(f"{path}: longer than max_length {spec['max_length']}")

    elif type_name in ("integer", "number"):
        if "min" in spec and value < spec["min"]:
            errors.append(f"{path}: less than min {spec['min']}")
        if "max" in spec and value > spec["max"]:
            errors.append(f"{path}: greater than max {spec['max']}")

    elif type_name == "array":
        items = spec.get("items")
        if items is not None:
            for idx, item in enumerate(value):
                _validate_value(
                    f"{path}[{idx}]", item, items, errors, schema_path=f"{schema_path}.items"
                )

    elif type_name == "object":
        fields = spec.get("fields")
        if "additional_fields" in spec or fields is not None:
            nested_policy = spec.get("additional_fields", "reject")
            _validate_policy(nested_policy, f"{schema_path}.additional_fields")
        if fields is not None:
            _validate_fields(
                value,
                fields,
                path,
                errors,
                additional_fields=spec.get("additional_fields", "reject"),
                schema_path=f"{schema_path}.fields",
            )


def _validate_fields(
    record: dict[str, Any],
    fields: dict[str, Any],
    base_path: str,
    errors: list[str],
    additional_fields: str = "reject",
    schema_path: str = "",
) -> None:
    if additional_fields == "reject":
        declared = set(fields)
        for key in sorted(set(record) - declared):
            path = f"{base_path}.{key}" if base_path else key
            errors.append(f"{path}: unknown field (additional_fields=reject)")
    for field_name, spec in fields.items():
        path = f"{base_path}.{field_name}" if base_path else field_name
        if field_name not in record:
            if spec.get("required", False):
                errors.append(f"{path}: missing required field")
            continue
        _validate_value(
            path,
            record[field_name],
            spec,
            errors,
            schema_path=f"{schema_path}.{field_name}",
        )


def validate_record(
    schema: dict[str, Any],
    record: dict[str, Any],
    location: str = "<record>",
) -> None:
    """Validate ``record`` against ``schema``; raise ``RecordValidationError`` on failure.

    Unknown-field policy is explicit (G1-003): by default unknown top-level and
    nested fields are REJECTED with a full field path, so misspelled keys cannot
    silently pass. A schema may opt in to forward compatibility per scope via
    ``"additional_fields": "allow"`` (top level and/or nested object specs).
    """
    schema_name = schema.get("schema_name")
    if not isinstance(schema_name, str) or not schema_name:
        raise SchemaError("schema document missing 'schema_name'")
    if not isinstance(schema.get("schema_version"), int):
        raise SchemaError(f"{schema_name}: schema_version must be an integer")
    fields = schema.get("fields")
    if not isinstance(fields, dict):
        raise SchemaError(f"{schema_name}: 'fields' must be an object")
    additional = schema.get("additional_fields", "reject")
    _validate_policy(additional, f"{schema_name}.additional_fields")

    errors: list[str] = []
    _validate_fields(
        record,
        fields,
        "",
        errors,
        additional_fields=additional,
        schema_path=f"{schema_name}.fields",
    )
    if errors:
        raise RecordValidationError(schema_name, location, errors)


def load_schemas(schema_dir: Path | None = None) -> dict[str, dict[str, Any]]:
    """Load every ``*.schema.json`` under ``schema_dir`` keyed by ``schema_name``."""
    directory = Path(schema_dir) if schema_dir is not None else DEFAULT_SCHEMA_DIR
    schemas: dict[str, dict[str, Any]] = {}
    for path in sorted(directory.glob("*.schema.json")):
        raw = json.loads(path.read_text(encoding="utf-8"))
        name = raw.get("schema_name")
        if not isinstance(name, str) or not name:
            raise SchemaError(f"{path}: missing schema_name")
        if name in schemas:
            raise SchemaError(f"{path}: duplicate schema_name {name!r}")
        schemas[name] = raw
    return schemas


def get_schema(name: str, schema_dir: Path | None = None) -> dict[str, Any]:
    """Return one schema by name, raising ``KeyError`` if absent."""
    schemas = load_schemas(schema_dir)
    try:
        return schemas[name]
    except KeyError:
        raise KeyError(f"unknown schema {name!r}; known: {sorted(schemas)}") from None


def validate(
    schema_name: str,
    record: dict[str, Any],
    location: str = "<record>",
    schema_dir: Path | None = None,
) -> None:
    """Convenience: load schema by name and validate a record against it."""
    validate_record(get_schema(schema_name, schema_dir), record, location)
