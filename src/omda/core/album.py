"""Album identity filtering, permanent exclusion and run-level deduplication
(T2.4; repaired G2-003).

Rules (SPEC §2.4, Master Plan §3.2):
- every selected Album is distinct within a run;
- every successfully recommended Album is permanently excluded, preferring a
  stable canonical identity (e.g. MusicBrainz release-group);
- the same canonical release deduplicates even under different names; two
  different releases must NOT be merged by name alone;
- string fallback is deterministic, reviewable and confidence-aware; ambiguous
  identities are NEVER the basis for a destructive permanent exclusion.

G2-003 repairs:
- exact ``album_id`` matching is independent of a nested identity object;
- canonical identity is namespaced by ``(canonical_source, canonical_id)`` and
  never matched when the source namespace is missing on either side;
- destructive canonical matching requires trustworthy (non-ambiguous)
  confidence on BOTH sides;
- normalization is Unicode-aware (NFD + combining-mark removal + casefold) and
  preserves non-Latin scripts instead of ASCII-collapsing them.

Core purity: this module never reads SQLite, HistoryPort or files — the
Orchestrator passes an immutable ``frozenset[AlbumIdentity]`` exclusion input.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Sequence

from omda.ports.domain import AlbumCandidate, AlbumIdentity

# Punctuation/separators removed during normalization (kept minimal; script
# characters — including CJK and non-Latin letters — are always preserved).
_SEPARATORS = frozenset(" \t\n\r.,;:!?()[]{}<>'\"`~@#$%^&*_-+=|/\\，。！？、；：（）《》【】")


def normalized_text(text: str) -> str:
    """Deterministic Unicode-aware normalization.

    - NFD decompose, then drop combining marks ONLY on Latin base characters
      (café -> cafe); combining marks on non-Latin bases (e.g. Japanese
      dakuten/handakuten, スピッツ) are preserved so scripts never corrupt;
    - strip whitespace and punctuation;
    - casefold (locale-independent).
    Distinct scripts never collapse onto each other.
    """
    decomposed = unicodedata.normalize("NFD", text)
    kept: list[str] = []
    for ch in decomposed:
        if ch in _SEPARATORS:
            continue
        if unicodedata.combining(ch):
            if kept and "LATIN" in unicodedata.name(kept[-1], ""):
                continue  # strip accent only from Latin base letters
            kept.append(ch)  # preserve combining marks of other scripts
            continue
        kept.append(ch)
    return "".join(kept).casefold()


def _canonical_matches(candidate_id: AlbumIdentity, exclusion: AlbumIdentity) -> bool:
    """Namespaced canonical equality (G2-003).

    Both sides must carry a canonical_id AND the same canonical_source; a missing
    source on either side makes the namespace unprovable -> no destructive match.
    """
    if not candidate_id.canonical_id or not exclusion.canonical_id:
        return False
    if not candidate_id.canonical_source or not exclusion.canonical_source:
        return False
    return (candidate_id.canonical_source, candidate_id.canonical_id) == (
        exclusion.canonical_source,
        exclusion.canonical_id,
    )


def is_permanently_excluded(
    candidate: AlbumCandidate,
    exclusions: frozenset[AlbumIdentity],
) -> bool:
    """Whether a candidate is permanently excluded.

    - exact ``album_id`` match is always authoritative (independent of a nested
      identity object);
    - canonical match requires the namespaced identity AND non-ambiguous
      confidence on both sides.
    """
    identity = candidate.identity
    for exclusion in exclusions:
        if exclusion.identity_confidence == "ambiguous":
            continue
        if candidate.album_id == exclusion.album_id:
            return True
        if (
            identity is not None
            and identity.identity_confidence != "ambiguous"
            and _canonical_matches(identity, exclusion)
        ):
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

    Namespaced canonical release-group ID wins when present; otherwise a
    normalized artist/title/year composite (Unicode-aware) is the string
    fallback.
    """
    identity = candidate.identity
    if identity is not None and identity.canonical_id and identity.canonical_source:
        return ("canonical", identity.canonical_source, identity.canonical_id)
    if identity is not None and identity.canonical_id:
        return ("canonical-unproven", identity.canonical_id)
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
