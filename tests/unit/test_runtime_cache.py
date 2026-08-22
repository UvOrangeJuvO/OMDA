"""G3-007 Git-ignored runtime cache (ADR-0002 §8.6 / D2; G3-007-006).

The runtime cache is local, bounded, TTL/provenance aware and safe to delete;
an ordinary recommendation run NEVER writes tracked repository data. TTL must be
positive-finite, keys are collision-resistant, and eviction is insertion-order
FIFO (not filename order)."""

from __future__ import annotations

import math
import time

import pytest

from omda.adapters.curated import RuntimeCache


def test_cache_writes_only_under_ignored_root(tmp_path) -> None:
    cache = RuntimeCache(tmp_path / "var" / "cache")
    cache.put("k1", {"digest": "x" * 64})
    for child in cache.root.rglob("*"):
        assert tmp_path / "var" / "cache" in child.parents or child == cache.root
    assert cache.get("k1") == {"digest": "x" * 64}


def test_cache_ttl_expiry(tmp_path) -> None:
    cache = RuntimeCache(tmp_path / "cache", ttl_seconds=0.01)
    cache.put("k", {"v": 1})
    time.sleep(0.03)
    assert cache.get("k") is None


def test_cache_ttl_must_be_positive_finite(tmp_path) -> None:
    # G3-007-006: negative values expire immediately and NaN disables the
    # comparison — invalid configuration must fail at construction.
    for bad in (0, -1, math.nan, math.inf, "10", True):
        with pytest.raises(ValueError):
            RuntimeCache(tmp_path / "c", ttl_seconds=bad)


def test_cache_bounded_fifo_eviction_in_insertion_order(tmp_path) -> None:
    # G3-007-006: FIFO follows INSERTION order, not filename order. Inserting
    # "z", then "a", then "m" must evict "z" (inserted first), even though "a"
    # sorts before "z".
    cache = RuntimeCache(tmp_path / "cache", max_entries=2)
    cache.put("z", {"v": 1})
    cache.put("a", {"v": 2})
    cache.put("m", {"v": 3})  # evicts "z" (first inserted)
    assert cache.get("z") is None
    assert cache.get("a") == {"v": 2}
    assert cache.get("m") == {"v": 3}


def test_cache_keys_are_collision_resistant(tmp_path) -> None:
    # G3-007-006: distinct keys such as "a/b" and "a_b" must never collide on
    # the same cache file.
    cache = RuntimeCache(tmp_path / "cache")
    cache.put("a/b", {"v": 1})
    cache.put("a_b", {"v": 2})
    assert cache.get("a/b") == {"v": 1}
    assert cache.get("a_b") == {"v": 2}
    assert cache.get("a.b") is None


def test_cache_key_is_versioned_and_safe_to_delete(tmp_path) -> None:
    cache = RuntimeCache(tmp_path / "cache")
    cache.put("curated-omda|2026-08-22|v1|ambient", {"digest": "a"})
    cache.put("curated-omda|2026-08-22|v2|ambient", {"digest": "b"})
    assert cache.get("curated-omda|2026-08-22|v1|ambient") == {"digest": "a"}
    cache.delete("curated-omda|2026-08-22|v1|ambient")
    assert cache.get("curated-omda|2026-08-22|v1|ambient") is None
    assert cache.get("curated-omda|2026-08-22|v2|ambient") == {"digest": "b"}
    cache.clear()
    assert cache.get("curated-omda|2026-08-22|v2|ambient") is None


def test_ordinary_read_never_writes_tracked_data(tmp_path) -> None:
    cache = RuntimeCache(tmp_path / "cache")
    assert cache.get("nope") is None
    assert not cache.root.exists()
