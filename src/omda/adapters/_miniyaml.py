"""Minimal flat-YAML parser for source metadata (G3).

The project keeps a zero runtime dependency policy (G1 accepted). ``source.yaml``
files under ``data/`` are intentionally flat mappings of scalar values, so a
small, deterministic parser is enough — no general-purpose YAML engine is
introduced. Unsupported structure is rejected with a precise location instead of
being silently misparsed.
"""

from __future__ import annotations

import re
from pathlib import Path

from omda.ports.errors import InvalidInputError

_KEY_RE = re.compile(r"^[a-z_][a-z0-9_]*$")


def _parse_scalar(raw: str, where: str):
    value = raw.strip()
    if value.startswith('"') and value.endswith('"'):
        return value[1:-1]
    if value.startswith("'") and value.endswith("'"):
        return value[1:-1]
    lowered = value.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    if lowered in ("null", "~"):
        return None
    if re.fullmatch(r"-?\d+", value):
        return int(value)
    if re.fullmatch(r"-?\d+\.\d+", value):
        return float(value)
    if value == "":
        raise InvalidInputError(f"{where}: empty scalar value")
    return value


def parse_flat_yaml(text: str, path: str) -> dict:
    """Parse a flat mapping (one ``key: value`` per line) from source.yaml.

    Lines may carry trailing comments after `` # ``; comment-only lines and blank
    lines are skipped. Nested mappings/sequences are rejected explicitly.
    """
    result: dict = {}
    for line_no, line in enumerate(text.splitlines(), start=1):
        content = line.split(" # ", 1)[0].strip()
        if not content or content.startswith("#"):
            continue
        if ":" not in content:
            raise InvalidInputError(
                f"{path}:{line_no}: expected 'key: value', got {line.strip()!r}"
            )
        key, _, raw_value = content.partition(":")
        key = key.strip()
        if not _KEY_RE.fullmatch(key):
            raise InvalidInputError(
                f"{path}:{line_no}: invalid key {key!r} (expected [a-z_][a-z0-9_]*)"
            )
        if key in result:
            raise InvalidInputError(f"{path}:{line_no}: duplicate key {key!r}")
        where = f"{path}:{line_no}"
        value = raw_value.strip()
        if value in ("{", "[") or value.startswith(("{", "[")):
            raise InvalidInputError(
                f"{where}: nested mappings/sequences are not supported in source.yaml"
            )
        result[key] = _parse_scalar(value, where)
    return result


def load_flat_yaml(path: Path) -> dict:
    """Read and parse a flat source.yaml; errors carry the file location."""
    return parse_flat_yaml(path.read_text(encoding="utf-8"), str(path))


__all__ = ["load_flat_yaml", "parse_flat_yaml"]
