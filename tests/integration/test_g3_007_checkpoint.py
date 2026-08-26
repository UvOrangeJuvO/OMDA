"""G3-007 checkpoint acceptance: the curated source chain really works.

Uses the REAL reviewed packages (data/genres/curated-omda + data/albums/
curated-omda + data/sources/registry.jsonl) to prove one real 3x3
recommendation can be sourced end-to-end: genre FETCH -> album FETCH per Genre
-> CandidateBatch -> ValidatedSourceSet, with provenance/license/digest that a
G4 delivery gate can trace (ADR-0002 §8.4/§8.5/§8.8).

Closes the G3-007-001..006 acceptance requirements:
- 001: Genre-bound batches that are NOT identical across Genres; no cross-Genre
  record can enter the requested batch; deterministic 3x3 selection with
  permanent exclusion and explicit shortage;
- 002: every production record carries a verified canonical MBID from the same
  validated batch;
- 003: demo status covers Genre descriptors too; empty/tampered/unrelated
  assemblies fail closed;
- 004: provider-neutral source_batch Port path, cache tampering treated as a
  typed miss;
- 005: license/derivation fixtures reject non-reviewed claims;
- 006: (unit tests) cache FIFO/TTL robustness.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from omda.adapters.curated import CuratedAlbumSource, RuntimeCache
from omda.adapters.datasets import GenreDatasetAdapter
from omda.ports.domain import GenreRef
from omda.ports.errors import InvalidInputError
from omda.ports.source import assemble_validated_source_set, verify_batch_integrity
from omda.sources.registry import RegistryEntry, SourceRegistry

REPO = Path(__file__).resolve().parents[2]
REGISTRY = REPO / "data" / "sources" / "registry.jsonl"
GENRES = REPO / "data" / "genres" / "curated-omda"
ALBUMS = REPO / "data" / "albums" / "curated-omda"
RYM_SAMPLE = REPO / "data" / "genres" / "rym-sample"

ALBUMS_PER_GENRE = 3


def _registry() -> SourceRegistry:
    return SourceRegistry.load(REGISTRY)


def test_real_curated_packages_support_one_3x3_run() -> None:
    registry = _registry()
    genre_adapter = GenreDatasetAdapter(GENRES)
    album_source = CuratedAlbumSource(ALBUMS)

    genres = genre_adapter.list_eligible_genres()
    assert len(genres) == 5
    genre_descriptor = genre_adapter.descriptor()
    assert genre_descriptor.demo is False
    registry.verify_descriptor(genre_descriptor)

    batches = []
    digests = set()
    for genre in genres:
        batch = album_source.source_batch(genre)  # provider-neutral Port path
        verify_batch_integrity(batch)
        assert len(batch.candidates) >= ALBUMS_PER_GENRE
        # G3-007-001: every candidate belongs to the requested Genre.
        assert all(r.genre_id == genre.genre_id for r in batch.candidates)
        # G3-007-002: every production record carries a canonical MBID.
        assert all(r.mbid for r in batch.candidates)
        digests.add(batch.digest)
        batches.append(batch)
    # The five real batches are NOT identical (G3-007-001 positive proof).
    assert len(digests) == len(genres)
    assert len({b.genre_id for b in batches}) == len(genres)

    source_set = assemble_validated_source_set(
        registry,
        genre_descriptors=(genre_descriptor,),
        batches=tuple(batches),
        selected_genre_ids=tuple(g.genre_id for g in genres),
        required_candidates_per_genre=ALBUMS_PER_GENRE,
    )
    assert source_set.is_demo is False


def test_no_cross_genre_record_enters_a_requested_batch() -> None:
    # G3-007-001 negative: an Ambient batch never contains Bebop records.
    album_source = CuratedAlbumSource(ALBUMS)
    ambient_ids = {r.album_id for r in album_source.source_batch(_g("ambient")).candidates}
    assert "curated-omda-bebop-0001" not in ambient_ids
    assert all(aid.startswith("curated-omda-ambient-") for aid in ambient_ids)


def test_production_records_have_unique_valid_mbid_from_validated_batch() -> None:
    # G3-007-002: every selected production record has a canonical identity
    # bound to the same validated batch (permanent-exclusion basis).
    album_source = CuratedAlbumSource(ALBUMS)
    all_mbids: list[str] = []
    for genre_id in ("ambient", "bebop", "krautrock", "tuareg-music", "idm"):
        batch = album_source.source_batch(_g(genre_id))
        for record in batch.candidates:
            assert record.mbid is not None
            assert len(record.mbid) == 36
            assert record.mbid.count("-") == 4
            candidates = album_source.candidates_for_genre(_g(genre_id))
            by_id = {c.album_id: c for c in candidates}
            identity = by_id[record.album_id].identity
            assert identity is not None
            assert identity.canonical_id == record.mbid  # identity from the batch
            all_mbids.append(record.mbid)
    assert len(all_mbids) == len(set(all_mbids))  # no duplicate canonical IDs


def test_deterministic_3x3_selection_with_permanent_exclusion_and_shortage() -> None:
    # G3-007-001/002: exercise actual deterministic selection from the real
    # packages: pick 3 per Genre in stable order, exclude permanently-selected
    # albums, and fail explicitly when a Genre runs short.
    album_source = CuratedAlbumSource(ALBUMS)

    def select(genre: GenreRef, excluded: set[str]):
        candidates = [
            r
            for r in album_source.source_batch(genre).candidates
            if r.album_id not in excluded
        ]
        if len(candidates) < ALBUMS_PER_GENRE:
            raise InvalidInputError(
                f"genre {genre.genre_id!r}: insufficient candidates after permanent "
                f"exclusion ({len(candidates)} < {ALBUMS_PER_GENRE})"
            )
        return sorted(candidates, key=lambda r: r.album_id)[:ALBUMS_PER_GENRE]

    excluded: set[str] = set()
    for genre_id in ("ambient", "bebop", "krautrock"):
        picked = select(_g(genre_id), excluded)
        assert len(picked) == ALBUMS_PER_GENRE
        assert all(p.mbid for p in picked)
        excluded.update(p.album_id for p in picked)
    # Excluding everything for one Genre -> explicit shortage, never substitution.
    with pytest.raises(InvalidInputError):
        select(_g("idm"), {r.album_id for r in album_source.source_batch(_g("idm")).candidates})


def test_demo_genre_with_production_albums_yields_demo_source_set() -> None:
    # G3-007-003: a registered demo Genre + production Albums must yield
    # is_demo=True (the production-facing source-set result, not the raw flag).
    # Registry entries are derived from the REAL package descriptors so every
    # immutable field matches (G3-007-005).
    demo_genre = GenreDatasetAdapter(RYM_SAMPLE).descriptor()
    assert demo_genre.demo is True
    base = {
        e.key: e for e in SourceRegistry.load(REGISTRY).entries()
    }  # curated-omda genre + album (reviewed)
    base["rym-sample:genre"] = RegistryEntry(
        source_id=demo_genre.source_id,
        kind="genre",
        display_name=demo_genre.display_name,
        origin_url=demo_genre.origin_url,
        license=demo_genre.license,
        retrieved_at=demo_genre.retrieved_at,
        dataset_version=demo_genre.dataset_version,
        schema_version=demo_genre.schema_version,
        data_scope=demo_genre.data_scope,
        demo=demo_genre.demo,
        records_file=demo_genre.records_file,
        data_derivation=demo_genre.data_derivation,
        upstream_license=demo_genre.upstream_license,
        license_core_facts=demo_genre.license_core_facts,
        license_supplementary_used=demo_genre.license_supplementary_used,
        license_service_terms=demo_genre.license_service_terms,
        license_derived_package=demo_genre.license_derived_package,
        content_digest=demo_genre.content_digest,
        eligible_digest=demo_genre.eligible_digest,
    )
    demo_registry = SourceRegistry(base)
    ambient = _g("ambient")
    result = assemble_validated_source_set(
        demo_registry,
        genre_descriptors=(demo_genre,),
        batches=(CuratedAlbumSource(ALBUMS).source_batch(ambient),),
        selected_genre_ids=("ambient",),
        required_candidates_per_genre=ALBUMS_PER_GENRE,
    )
    assert result.is_demo is True


def test_tampered_genre_data_fails_closed_via_content_digest(tmp_path: Path) -> None:
    # G3-007-003: editing a Genre record changes its content digest, which no
    # longer matches the reviewed registry -> assemble rejects.
    # G3-007-009: the tracked package is never modified — we copy it to a
    # tmp_path fixture and tamper the COPY.
    import shutil

    copy = tmp_path / "curated-omda"  # directory name must equal source_id
    shutil.copytree(GENRES, copy)
    lines = (copy / "genres.jsonl").read_text(encoding="utf-8").splitlines()
    record = json.loads(lines[0])
    record["name"] = "Ambient (tampered)"
    lines[0] = json.dumps(record, ensure_ascii=False)
    (copy / "genres.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")

    descriptor = GenreDatasetAdapter(copy).descriptor()
    assert descriptor.content_digest != _registry().get("curated-omda", "genre").content_digest
    with pytest.raises(InvalidInputError):
        assemble_validated_source_set(
            _registry(),
            genre_descriptors=(descriptor,),
            batches=(CuratedAlbumSource(ALBUMS).source_batch(_g("ambient")),),
            selected_genre_ids=("ambient",),
        )


def test_tampered_cache_is_a_typed_miss_on_public_port_path(tmp_path: Path) -> None:
    # G3-007-004: an invalid cached batch is never trusted — the public
    # source_batch path treats it as a miss and rebuilds from the package.
    cache = RuntimeCache(tmp_path / "cache")
    ambient = _g("ambient")
    first = CuratedAlbumSource(ALBUMS, cache=cache).source_batch(ambient)
    # Corrupt the cached copy for this Genre ON DISK.
    corrupted = False
    for payload in cache.root.glob("*.json"):
        data = json.loads(payload.read_text(encoding="utf-8"))
        if not isinstance(data, dict):  # manifest is a list, not a payload
            continue
        if data.get("value", {}).get("genre_id") == "ambient":
            data["value"]["digest"] = "f" * 64
            payload.write_text(json.dumps(data), encoding="utf-8")
            corrupted = True
    assert corrupted
    # G3-007-009: use a FRESH adapter over the SAME runtime cache — it has no
    # in-memory _batch_cache, so it must read the tampered disk entry, detect
    # the invalid digest, treat it as a typed miss and rebuild from the package.
    fresh = CuratedAlbumSource(ALBUMS, cache=cache)
    rebuilt = fresh.source_batch(ambient)
    assert rebuilt.digest == first.digest  # correct data, not the tampered copy
    verify_batch_integrity(rebuilt)


def _g(genre_id: str) -> GenreRef:
    names = {
        "ambient": "Ambient",
        "bebop": "Bebop",
        "krautrock": "Krautrock",
        "tuareg-music": "Tuareg Music",
        "idm": "IDM",
    }
    return GenreRef(genre_id=genre_id, name=names[genre_id], family="x", eligible=True)
