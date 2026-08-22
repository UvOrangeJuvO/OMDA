# curated-omda Album package

Non-demo, human-reviewed curated Album candidates for OMDA v0.1 (G3-007),
sufficient for one real 3x3 recommendation run (4 candidates per Genre).

## Content and canonical identity

- 20 real Album records across Ambient / Bebop / Krautrock / Tuareg Music / IDM.
- Every record carries a **verified MusicBrainz release-group MBID** obtained
  via the official search API for this curation (`tools/curate_mbids.py`,
  contactable User-Agent, ~1 req/s pacing); each MBID was accepted only for a
  primary-type Album with strong title/artist match and year corroboration
  (score >= 90), then reviewed before commit. No MBID is invented.
- `year` follows the MusicBrainz `first-release-date` year for consistency.

## License / provenance layers (ADR-0002 D1)

- **Core facts** (MBID/title/artist/year): CC0-1.0 (MusicBrainz database core).
- **Supplementary (tags/search index)**: NOT incorporated — MusicBrainz
  search-index/tag associations are CC BY-NC-SA 3.0 supplementary data and are
  not part of this package.
- **Service terms**: MusicBrainz web service is free for non-commercial use;
  commercial use requires a commercial plan.
- **Derived package**: CC0-1.0 for this independent curation (Album selection
  and Genre membership are curated here; they were not copied from any
  tag/search-derived list).

## Registry

The reviewed source registry (`data/sources/registry.jsonl`) binds source_id to
origin/license/schema/demo/derivation; the G3-007 boundary fails closed on any
mismatch. `demo: false` — production-eligible.
