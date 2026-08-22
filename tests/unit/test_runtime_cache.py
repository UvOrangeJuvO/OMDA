"""G3-007 Git-ignored runtime cache (ADR-0002 §8.6 / D2).

The runtime cache is local, bounded, TTL/provenance aware and safe to delete;
an ordinary recommendation run NEVER writes tracked repository data."""

from __future__ import annotations

from pathlib import Path

from omda.adapters.curated import RuntimeCache

CACHE_ROOT = Path("var/cache/album_sources")


def test_cache_writes_only_under_ignored_root(tmp_path: Path) -> None:
    cache = RuntimeCache(tmp_path / "var" / "cache")
    cache.put("k1", {"digest": "x" * 64})
    # Every file lives under the cache root (Git-ignored), never in tracked data.
    assert list(cache.root.rglob("*"))  # some file exists
    for child in cache.root.rglob("*"):
        assert tmp_path / "var" / "cache" in child.parents or child == cache.root
    assert cache.get("k1") == {"digest": "x" * 64}


def test_cache_ttl_expiry(tmp_path: Path) -> None:
    cache = RuntimeCache(tmp_path / "cache", ttl_seconds=0.01)
    cache.put("k", {"v": 1})
    import time

    time.sleep(0.03)
    assert cache.get("k") is None


def test_cache_bounded_fifo_eviction(tmp_path: Path) -> None:
    cache = RuntimeCache(tmp_path / "cache", max_entries=2)
    cache.put("a", {"v": 1})
    cache.put("b", {"v": 2})
    cache.put("c", {"v": 3})  # evicts oldest ("a")
    assert cache.get("a") is None
    assert cache.get("b") == {"v": 2}
    assert cache.get("c") == {"v": 3}


def test_cache_key_is_versioned_and_safe_to_delete(tmp_path: Path) -> None:
    cache = RuntimeCache(tmp_path / "cache")
    # Keys embed package/query-policy version: a policy change never serves
    # stale entries.
    cache.put("curated-omda|2026-08-22|v1|ambient", {"digest": "a"})
    cache.put("curated-omda|2026-08-22|v2|ambient", {"digest": "b"})
    assert cache.get("curated-omda|2026-08-22|v1|ambient") == {"digest": "a"}
    cache.clear()  # explicitly deletable
    assert cache.get("curated-omda|2026-08-22|v1|ambient") is None


def test_ordinary_read_never_writes_tracked_data(tmp_path: Path) -> None:
    # A pure read (get) must not create any cache file.
    cache = RuntimeCache(tmp_path / "cache")
    assert cache.get("nope") is None
    assert not cache.root.exists()
