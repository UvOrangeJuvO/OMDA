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
    """One reviewed registry entry (trust anchor for one source package).

    Binds source_id to expected origin/license/schema/demo/records_file AND to
    the derivation basis, upstream license and (for Genre packages) the
    reviewed content digest (G3-007-003/005).
    """

    source_id: str
    kind: str  # "genre" | "album"
    display_name: str
    origin_url: str
    license: str
    retrieved_at: str
    dataset_version: str
    schema_version: str
    data_scope: str
    records_file: str
    demo: bool
    data_derivation: str = "independently_curated"
    upstream_license: str = ""
    license_core_facts: str = ""
    license_supplementary_used: str = ""
    license_service_terms: str = ""
    license_derived_package: str = ""
    content_digest: str | None = None  # required for Genre packages
    eligible_digest: str | None = None  # required for Genre packages (G3-007-003)

    @property
    def key(self) -> str:
        return f"{self.source_id}:{self.kind}"


def _entry_from_record(record: dict) -> RegistryEntry:
    try:
        return RegistryEntry(
            source_id=record["source_id"],
            kind=record["kind"],
            display_name=record["display_name"],
            origin_url=record["origin_url"],
            license=record["license"],
            retrieved_at=record["retrieved_at"],
            dataset_version=record["dataset_version"],
            schema_version=record["schema_version"],
            data_scope=record["data_scope"],
            records_file=record["records_file"],
            demo=bool(record["demo"]),
            data_derivation=record["data_derivation"],
            upstream_license=record["upstream_license"],
            license_core_facts=record["license_core_facts"],
            license_supplementary_used=record["license_supplementary_used"],
            license_service_terms=record["license_service_terms"],
            license_derived_package=record["license_derived_package"],
            content_digest=record.get("content_digest"),
            eligible_digest=record.get("eligible_digest"),
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
            ("display_name", descriptor.display_name, entry.display_name),
            ("origin_url", descriptor.origin_url, entry.origin_url),
            ("license", descriptor.license, entry.license),
            ("retrieved_at", descriptor.retrieved_at, entry.retrieved_at),
            ("dataset_version", descriptor.dataset_version, entry.dataset_version),
            ("schema_version", descriptor.schema_version, entry.schema_version),
            ("data_scope", descriptor.data_scope, entry.data_scope),
            ("records_file", descriptor.records_file, entry.records_file),
            ("demo", descriptor.demo, entry.demo),
            ("data_derivation", descriptor.data_derivation, entry.data_derivation),
            ("upstream_license", descriptor.upstream_license, entry.upstream_license),
            ("license_core_facts", descriptor.license_core_facts, entry.license_core_facts),
            (
                "license_supplementary_used",
                descriptor.license_supplementary_used,
                entry.license_supplementary_used,
            ),
            (
                "license_service_terms",
                descriptor.license_service_terms,
                entry.license_service_terms,
            ),
            (
                "license_derived_package",
                descriptor.license_derived_package,
                entry.license_derived_package,
            ),
        )
        for field, actual, expected in checks:
            if actual != expected:
                mismatches.append(f"{field}: descriptor {actual!r} != registry {expected!r}")
        if descriptor.kind == "genre":
            # Genre packages are additionally bound to the reviewed content
            # digest AND the eligible-ID digest (G3-007-003): a tampered Genre
            # file or a forged eligible-ID set fails closed here.
            expected_digest = entry.content_digest
            actual_digest = getattr(descriptor, "content_digest", "")
            if not expected_digest or actual_digest != expected_digest:
                mismatches.append(
                    f"content_digest: descriptor {actual_digest!r} != registry "
                    f"{expected_digest!r}"
                )
            expected_eligible = entry.eligible_digest
            actual_eligible = getattr(descriptor, "eligible_digest", "")
            if not expected_eligible or actual_eligible != expected_eligible:
                mismatches.append(
                    f"eligible_digest: descriptor {actual_eligible!r} != registry "
                    f"{expected_eligible!r}"
                )
        if mismatches:
            raise InvalidInputError(
                f"source {descriptor.source_id!r} ({descriptor.kind}) failed registry "
                f"verification: {'; '.join(mismatches)}"
            )

    def entries(self) -> list[RegistryEntry]:
        return sorted(self._entries.values(), key=lambda e: e.key)


__all__ = ["RegistryEntry", "SourceRegistry"]
