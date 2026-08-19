"""Family/parent diversity constraints (T2.3).

Diversity is a SET constraint, never a scoring device and never a popularity
filter (SPEC §2.3). It may reject a combination but must not mutate the base
Genre pool or permanently starve a family. Limited families (regional /
traditional) default to at most one selection per run.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence

from omda.ports.domain import GenreRef

# "A configured regional/traditional family limit SHOULD default to at most one
# selection per run when the source taxonomy supports it" (SPEC §2.3).
DEFAULT_FAMILY_LIMITS: Mapping[str, int] = {"Regional": 1, "Traditional": 1}


def family_ok(
    chosen: Sequence[GenreRef],
    limits: Mapping[str, int] | None = None,
) -> bool:
    """Whether ``chosen`` respects per-family per-run limits (set constraint)."""
    limits = DEFAULT_FAMILY_LIMITS if limits is None else limits
    if not limits:
        return True
    counts = Counter(genre.family for genre in chosen)
    return all(counts.get(family, 0) <= limit for family, limit in limits.items())


__all__ = ["DEFAULT_FAMILY_LIMITS", "family_ok"]
