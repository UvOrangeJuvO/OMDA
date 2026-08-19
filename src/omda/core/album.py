"""Album identity filtering, permanent exclusion and run-level deduplication (T2.4).

Rules (SPEC §2.4, Master Plan §3.2):
- every selected Album is distinct within a run;
- every successfully recommended Album is permanently excluded, preferring a
  stable canonical identity (e.g. MusicBrainz release-group);
- the same canonical release deduplicates even under different names; two
  different releases must NOT be merged by name alone;
- string fallback is deterministic, reviewable and confidence-aware; ambiguous
  identities are NEVER the basis for a destructive permanent exclusion.

Core purity: this module never reads SQLite, HistoryPort or files — the
Orchestrator passes an immutable ``frozenset[AlbumIdentity]`` exclusion input.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from omda.ports.domain import AlbumCandidate, AlbumIdentity

_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def normalized_text(text: str) -> str:
    """Deterministic normalization for string-fallback identity matching."""
    return _NON_ALNUM.sub("", text.lower())


def is_permanently_excluded(
    candidate: AlbumCandidate,
    exclusions: frozenset[AlbumIdentity],
) -> bool:
    """Whether a candidate is permanently excluded.

    Only reviewable, exact identities drive permanent exclusion:
    - matching canonical_id (when both sides carry one);
    - matching album_id.
    Ambiguous exclusions are ignored for permanent exclusion (SPEC §2.4).
    """
    identity = candidate.identity
    for exclusion in exclusions:
        if exclusion.identity_confidence == "ambiguous":
            continue
        if (
            identity is not None
            and exclusion.canonical_id
            and identity.canonical_id
            and identity.canonical_id == exclusion.canonical_id
        ):
            return True
        if identity is not None and exclusion.album_id == identity.album_id:
            return True
    return False


def filter_candidates(
    candidates: Sequence[AlbumCandidate],
    exclusions: frozenset[AlbumIdentity],
) -> list[AlbumCandidate]:
    """Return candidates not permanently excluded (input never mutated)."""
    return [c for c in candidates if not is_permanently_excluded(c, exclusions)]


def dedup_key(candidate: AlbumCandidate) -> tuple[str, ...]:
    """Stable within-run identity key.

    Canonical release-group ID wins when present; otherwise a normalized
    artist/title/year composite is used as the string fallback (confidence is
    recorded on the identity when one exists).
    """
    identity = candidate.identity
    if identity is not None and identity.canonical_id:
        return ("canonical", identity.canonical_id)
    return (
        "norm",
        normalized_text(candidate.artist),
        normalized_text(candidate.title),
        str(candidate.year),
    )


def dedupe_candidates(
    candidates: Sequence[AlbumCandidate],
    already_selected: Sequence[AlbumCandidate] = (),
) -> list[AlbumCandidate]:
    """Drop candidates whose identity key already appears in ``already_selected``
    or earlier in the list (within-run deduplication)."""
    seen = {dedup_key(c) for c in already_selected}
    result: list[AlbumCandidate] = []
    for candidate in candidates:
        key = dedup_key(candidate)
        if key in seen:
            continue
        seen.add(key)
        result.append(candidate)
    return result


__all__ = [
    "dedup_key",
    "dedupe_candidates",
    "filter_candidates",
    "is_permanently_excluded",
    "normalized_text",
]
