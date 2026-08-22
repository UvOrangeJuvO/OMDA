"""Reviewed source registry — the trust anchor for curated community data.

G3-007 / ADR-0002 §8.5: a content digest proves INTEGRITY, not authenticity.
Trust comes from an EXPLICITLY INSTALLED and REVIEWED source registry which
binds each ``source_id`` (per kind) to the expected origin URL, license, schema
version, records file and demo policy. A descriptor/batch that disagrees with
the registry fails closed — a self-asserted "production" label is not
provenance.

The registry ships as reviewable Git text ``data/sources/registry.jsonl``
(one JSON record per line, validated against ``source_registry`` schema). Only
human review + explicit commit may change it; runtime code never writes it.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from omda.adapters._miniyaml import load_flat_yaml  # noqa: F401  (re-exported for parity)
from omda.ports.errors import InvalidInputError
from omda.ports.source import SourceDescriptor
from omda.schemas import validate

_KNOWN_KINDS = frozenset({"genre", "album"})


@dataclass(frozen=True)
class RegistryEntry:
    """One reviewed registry entry (trust anchor for one source package)."""

    source_id: str
    kind: str  # "genre" | "album"
    origin_url: str
    license: str
    schema_version: str
    demo: bool
    records_file: str

    @property
    def key(self) -> str:
        return f"{self.source_id}:{self.kind}"


def _entry_from_record(record: dict) -> RegistryEntry:
    try:
        return RegistryEntry(
            source_id=record["source_id"],
            kind=record["kind"],
            origin_url=record["origin_url"],
            license=record["license"],
            schema_version=record["schema_version"],
            demo=bool(record["demo"]),
            records_file=record["records_file"],
        )
    except KeyError as exc:
        raise InvalidInputError(f"source registry record missing {exc.args[0]!r}") from exc


class SourceRegistry:
    """Loaded, validated registry of reviewed curated sources.

    ``entries`` maps ``"<source_id>:<kind>"`` -> :class:`RegistryEntry`.
    """

    def __init__(self, entries: dict[str, RegistryEntry]) -> None:
        self._entries = dict(entries)

    @classmethod
    def load(cls, path: Path) -> SourceRegistry:
        """Parse ``registry.jsonl``: one validated JSON record per line."""
        path = Path(path)
        if not path.exists():
            raise InvalidInputError(f"{path}: source registry file missing")
        entries: dict[str, RegistryEntry] = {}
        for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                record = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise InvalidInputError(f"{path}:{line_no}: invalid JSON: {exc}") from exc
            if not isinstance(record, dict):
                raise InvalidInputError(f"{path}:{line_no}: entry must be a JSON object")
            validate("source_registry", record, f"{path}:{line_no}")
            entry = _entry_from_record(record)
            if entry.kind not in _KNOWN_KINDS:
                raise InvalidInputError(
                    f"{path}:{line_no}: kind must be one of {sorted(_KNOWN_KINDS)}, "
                    f"got {entry.kind!r}"
                )
            if entry.key in entries:
                raise InvalidInputError(f"{path}:{line_no}: duplicate registry key {entry.key!r}")
            entries[entry.key] = entry
        if not entries:
            raise InvalidInputError(f"{path}: no registry entries found")
        return cls(entries)

    def get(self, source_id: str, kind: str) -> RegistryEntry:
        entry = self._entries.get(f"{source_id}:{kind}")
        if entry is None:
            raise InvalidInputError(
                f"source {source_id!r} (kind {kind!r}) is not registered in the "
                "reviewed source registry"
            )
        return entry

    def demo_policy(self, source_id: str, kind: str) -> bool:
        return self.get(source_id, kind).demo

    def verify_descriptor(self, descriptor: SourceDescriptor) -> None:
        """Fail closed when the descriptor disagrees with the reviewed entry.

        Every digest-relevant field must equal the registry expectation; a
        self-asserted ``demo`` flag or origin/license/schema that differs from
        the reviewed entry is rejected (ADR-0002 §8.5).
        """
        entry = self.get(descriptor.source_id, descriptor.kind)
        mismatches: list[str] = []
        checks = (
            ("origin_url", descriptor.origin_url, entry.origin_url),
            ("license", descriptor.license, entry.license),
            ("schema_version", descriptor.schema_version, entry.schema_version),
            ("records_file", descriptor.records_file, entry.records_file),
            ("demo", descriptor.demo, entry.demo),
        )
        for field, actual, expected in checks:
            if actual != expected:
                mismatches.append(f"{field}: descriptor {actual!r} != registry {expected!r}")
        if mismatches:
            raise InvalidInputError(
                f"source {descriptor.source_id!r} ({descriptor.kind}) failed registry "
                f"verification: {'; '.join(mismatches)}"
            )

    def entries(self) -> list[RegistryEntry]:
        return sorted(self._entries.values(), key=lambda e: e.key)


__all__ = ["RegistryEntry", "SourceRegistry"]
