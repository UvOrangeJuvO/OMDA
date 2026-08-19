"""Deterministic randomness tooling (SPEC §6, T1.6).

Selection logic accepts an injectable randomness source; tests reproduce a
selection from input version + configuration + seed. The seed used by a run is
recorded in the run journal (SPEC §6). Production may use unpredictable seeds.
"""

from __future__ import annotations

import random
import secrets


def make_rng(seed: str | None = None) -> random.Random:
    """Return a deterministic ``random.Random`` derived from ``seed``.

    ``seed`` is hashed so arbitrary strings (e.g. ``"run-2026-08-19"``) yield a
    stable, well-distributed stream. With ``seed=None`` a fresh unpredictable
    generator is returned (caller must record the seed in the journal).
    """
    if seed is None:
        return random.Random()
    return random.Random(seed)


def new_seed() -> str:
    """Generate an unpredictable seed to record in the run journal."""
    return secrets.token_hex(16)


def reseed_rng(rng: random.Random, seed: str) -> random.Random:
    """Create a fresh deterministic RNG from a seed, for test reproduction."""
    return make_rng(seed)


__all__ = ["make_rng", "new_seed", "reseed_rng"]
