# curated-omda Genre package

Non-demo, human-reviewed curated Genre taxonomy for OMDA v0.1 (G3-007).

- **Content**: 5 real Genre records (Ambient, Bebop, Krautrock, Tuareg Music,
  IDM). Genre membership of Albums is bound by `genre_id` on each record and
  reviewed here — no record is ever relabelled to another Genre.
- **License (data)**: independently curated factual taxonomy, CC0-1.0. Wikipedia
  articles are referenced for verification only; no article text is copied
  (their text is CC BY-SA 4.0). Data license is separate from any code license
  (ADR-0002 D1).
- **Provenance**: origin_url, retrieved_at, dataset_version in `source.yaml`;
  the reviewed source registry (`data/sources/registry.jsonl`) binds
  origin/license/schema/demo/derivation AND the **content digest** of the Genre
  records — a tampered Genre package fails closed at the source-set boundary.
- **demo**: false — production-eligible, not a sample.
