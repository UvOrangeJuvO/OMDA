"""Layered application configuration (T1.3).

Layers, lowest to highest precedence: built-in defaults < user file < runtime overrides.
The final merged mapping is validated against the versioned ``config`` schema before
being frozen into a ``Config``.

Product-semantic defaults (SPEC §2) are configurable, but changing product semantics
or defaults requires an ADR; ``semantic_overrides()`` exposes which of those fields
were changed so governance/tests can enforce the ADR rule.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Any

from omda.schemas import get_schema, validate_record

# SPEC §2 product constants (semantics-sensitive defaults).
DEFAULT_DAILY_GENRE_COUNT = 3
DEFAULT_ALBUMS_PER_GENRE = 3
DEFAULT_GENRE_COOLDOWN_PICKS = 30
DEFAULT_MODERN_ALBUM_YEAR = 2010

_SEMANTIC_FIELDS = frozenset(
    {
        "daily_genre_count",
        "albums_per_genre",
        "genre_cooldown_picks",
        "modern_album_year",
    }
)

# Mirrors data/schemas/config.schema.json delivery constraints (single source of
# truth is the schema; these mirrors keep a directly constructed DeliveryConfig
# from ever carrying a value the schema would reject).
_CHANNELS = ("markdown", "pushplus")
_ENV_PATTERN = re.compile(r"^[A-Z_][A-Z0-9_]*$")


@dataclass(frozen=True)
class DeliveryConfig:
    channel: str = "markdown"  # "markdown" | "pushplus" (schema enum)
    pushplus_token_env: str | None = None

    def __post_init__(self) -> None:
        # G2-011: validate direct DeliveryConfig(...) values with a CONTROLLED
        # error (no raw TypeError/AttributeError from regex/attribute access).
        if not isinstance(self.channel, str):
            raise ValueError(
                f"delivery.channel: must be a string, got {type(self.channel).__name__}"
            )
        if self.channel not in _CHANNELS:
            raise ValueError(
                f"delivery.channel: must be one of {list(_CHANNELS)}, got {self.channel!r}"
            )
        if self.pushplus_token_env is not None:
            if not isinstance(self.pushplus_token_env, str):
                raise ValueError(
                    "delivery.pushplus_token_env: must be a string, got "
                    f"{type(self.pushplus_token_env).__name__}"
                )
            if not _ENV_PATTERN.fullmatch(self.pushplus_token_env):
                raise ValueError(
                    f"delivery.pushplus_token_env: invalid pattern {self.pushplus_token_env!r}"
                )


@dataclass(frozen=True)
class Config:
    daily_genre_count: int = DEFAULT_DAILY_GENRE_COUNT
    albums_per_genre: int = DEFAULT_ALBUMS_PER_GENRE
    genre_cooldown_picks: int = DEFAULT_GENRE_COOLDOWN_PICKS
    modern_album_year: int = DEFAULT_MODERN_ALBUM_YEAR
    seed: str | None = None
    # G2-010/G2-011: per-parent per-run set limits (parent -> max selections).
    # The value is ALWAYS frozen defensively in __post_init__, so every supported
    # construction path (including direct Config(...)) yields an immutable
    # snapshot; a caller-owned mapping never stays attached to Config.
    genre_parent_limits: Mapping[str, int] = field(default_factory=dict)
    delivery: DeliveryConfig = field(default_factory=DeliveryConfig)

    def __post_init__(self) -> None:
        # G2-011: ONE complete validation boundary for EVERY construction path
        # (including direct Config(...)). Only `seed` and `pushplus_token_env`
        # may be unset (None) — every other field must keep its declared type,
        # and malformed container/nested types are turned into controlled
        # ValueError BEFORE any snapshot rendering (no raw TypeError/AttributeError
        # can leak out of this boundary).
        if self.delivery is not None and not isinstance(self.delivery, DeliveryConfig):
            raise ValueError(
                f"delivery: must be a DeliveryConfig, got {type(self.delivery).__name__}"
            )
        if self.genre_parent_limits is not None and not isinstance(
            self.genre_parent_limits, Mapping
        ):
            raise ValueError(
                "genre_parent_limits: must be a mapping of parent -> integer limit, got "
                f"{type(self.genre_parent_limits).__name__}"
            )
        # Render the exact effective snapshot. None is NOT generically dropped:
        # only the explicitly optional fields (seed, pushplus_token_env) may be
        # omitted; a None in any non-nullable field reaches the schema and is
        # rejected there.
        snapshot = config_to_dict(self)
        if snapshot.get("seed") is None:
            snapshot.pop("seed", None)
        delivery_snapshot = snapshot.get("delivery")
        if (
            isinstance(delivery_snapshot, dict)
            and delivery_snapshot.get("pushplus_token_env") is None
        ):
            delivery_snapshot.pop("pushplus_token_env", None)
        validate_record(get_schema("config"), snapshot)
        raw = dict(self.genre_parent_limits)
        for parent in raw:
            # The schema validates values but not object keys; empty keys would
            # silently become inert constraints, so they are rejected here.
            if not isinstance(parent, str) or not parent:
                raise ValueError(
                    f"genre_parent_limits: parent key {parent!r} must be a non-empty string"
                )
        object.__setattr__(
            self,
            "genre_parent_limits",
            MappingProxyType(raw),
        )


def config_to_dict(config: Config) -> dict[str, Any]:
    """Render a Config as the plain mapping used for schema validation.

    Defensive: malformed field types are carried through untouched (so the
    schema rejects them) instead of raising raw TypeError/AttributeError; only
    valid containers are expanded.
    """
    parent_limits = config.genre_parent_limits
    if parent_limits is None or not isinstance(parent_limits, Mapping):
        parent_value: Any = parent_limits  # None/non-mapping -> schema rejects
    else:
        parent_value = dict(parent_limits)
    delivery = config.delivery
    if delivery is None or not isinstance(delivery, DeliveryConfig):
        delivery_value: Any = delivery  # None/non-DeliveryConfig -> schema rejects
    else:
        delivery_value = {
            "channel": delivery.channel,
            "pushplus_token_env": delivery.pushplus_token_env,
        }
    return {
        "daily_genre_count": config.daily_genre_count,
        "albums_per_genre": config.albums_per_genre,
        "genre_cooldown_picks": config.genre_cooldown_picks,
        "modern_album_year": config.modern_album_year,
        "seed": config.seed,
        "genre_parent_limits": parent_value,
        "delivery": delivery_value,
    }


def _deep_merge(base: dict[str, Any], update: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge ``update`` into a copy of ``base``."""
    out = dict(base)
    for key, value in update.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def _normalise(d: dict[str, Any]) -> dict[str, Any]:
    """Drop None values and empty child dicts so schema defaults apply cleanly."""
    out: dict[str, Any] = {}
    for key, value in d.items():
        if value is None:
            continue
        if isinstance(value, dict):
            nested = _normalise(value)
            if nested:
                out[key] = nested
        else:
            out[key] = value
    return out


def _from_dict(merged: dict[str, Any]) -> Config:
    delivery = merged.get("delivery") or {}
    return Config(
        daily_genre_count=merged.get("daily_genre_count", DEFAULT_DAILY_GENRE_COUNT),
        albums_per_genre=merged.get("albums_per_genre", DEFAULT_ALBUMS_PER_GENRE),
        genre_cooldown_picks=merged.get("genre_cooldown_picks", DEFAULT_GENRE_COOLDOWN_PICKS),
        modern_album_year=merged.get("modern_album_year", DEFAULT_MODERN_ALBUM_YEAR),
        seed=merged.get("seed"),
        genre_parent_limits=MappingProxyType(dict(merged.get("genre_parent_limits") or {})),
        delivery=DeliveryConfig(
            channel=delivery.get("channel", "markdown"),
            pushplus_token_env=delivery.get("pushplus_token_env"),
        ),
    )


def load_config(
    config_path: Path | None = None,
    overrides: dict[str, Any] | None = None,
    schema_dir: Path | None = None,
) -> Config:
    """Load configuration: defaults < user JSON/YAML file < runtime overrides.

    ``config_path`` may be a JSON file (`.json`); YAML support is intentionally not
    added at G1 to keep the runtime dependency-free (an accepted reversible choice).
    Missing file is not an error — defaults apply.
    """
    merged: dict[str, Any] = {}
    if config_path is not None and config_path.exists():
        raw = config_path.read_text(encoding="utf-8")
        try:
            file_data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{config_path}: invalid JSON: {exc}") from exc
        if not isinstance(file_data, dict):
            raise ValueError(f"{config_path}: config root must be a JSON object")
        merged = _deep_merge(merged, file_data)
    if overrides:
        merged = _deep_merge(merged, overrides)

    merged = _normalise(merged)
    validate_record(get_schema("config", schema_dir), merged, str(config_path or "<defaults>"))
    return _from_dict(merged)


def semantic_overrides(config: Config) -> list[str]:
    """Fields whose value differs from the SPEC §2 defaults (ADR required to change)."""
    changed: list[str] = []
    if config.daily_genre_count != DEFAULT_DAILY_GENRE_COUNT:
        changed.append("daily_genre_count")
    if config.albums_per_genre != DEFAULT_ALBUMS_PER_GENRE:
        changed.append("albums_per_genre")
    if config.genre_cooldown_picks != DEFAULT_GENRE_COOLDOWN_PICKS:
        changed.append("genre_cooldown_picks")
    if config.modern_album_year != DEFAULT_MODERN_ALBUM_YEAR:
        changed.append("modern_album_year")
    return changed
