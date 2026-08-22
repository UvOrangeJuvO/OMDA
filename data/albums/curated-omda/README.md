# curated-omda Album package

Non-demo, human-reviewed curated Album candidates for OMDA v0.1 (G3-007),
sufficient for one real 3x3 recommendation run (4 candidates per Genre).

- **Content**: 20 real Album records (title/artist/release year are public
  factual information) across Ambient / Bebop / Krautrock / Tuareg Music / IDM.
- **License (data)**: curated factual metadata — CC0-1.0. The data license is
  separate from any code license (ADR-0002 D1 licensing layers).
- **Canonical MBIDs**: intentionally empty; the run-time MusicBrainz enricher
  (G3 T3.3) fills them by strong title+artist match under MusicBrainz's own
  data terms. No MBID in this package is invented.
- **Provenance**: origin_url, retrieved_at, dataset_version in `source.yaml`;
  reviewed in `data/sources/registry.jsonl`.
- **demo**: false — production-eligible, never sample/demo data.
