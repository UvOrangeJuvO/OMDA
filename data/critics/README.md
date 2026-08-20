# Critic contribution packages

A critic source is contributed purely as text — no Recommendation Core code is
touched (SPEC §2.6; MP §3.3). A package lives under `data/critics/<source_id>/`
and contains exactly two files:

```
data/critics/<source_id>/
├── source.yaml          # source metadata (critic_source schema)
└── ratings.csv          # rating rows (critic_rating schema)
```

## `source.yaml`

A flat mapping (one `key: value` per line; trailing ` # comment` allowed):

| key | required | meaning |
|---|---|---|
| `source_id` | yes | lowercase `[a-z0-9-]+`, must match the directory name and every CSV row |
| `display_name` | yes | human-readable source name |
| `license` | yes | data license / attribution statement |
| `origin_url` | yes | where the ratings were collected from (`https://...`) |
| `scrape_date` | yes | ISO 8601 date when the ratings were retrieved |
| `rating_scale_min` | yes | declared minimum rating (number) |
| `rating_scale_max` | yes | declared maximum rating (number) |

Example:

```yaml
source_id: pitchfork-sample
display_name: Pitchfork (sample)
license: CC-BY-NC-4.0 (sample subset)
origin_url: https://pitchfork.com/reviews/albums/
scrape_date: 2026-08-20
rating_scale_min: 0
rating_scale_max: 10
```

## `ratings.csv`

Header must be exactly:

```
source_id,album_id,rating,rating_max,review_url
```

- `source_id` must equal the `source_id` in `source.yaml` on every row.
- `album_id` is the stable album identity the ratings attach to
  (`[a-z0-9][a-z0-9-]*`).
- `rating` must be within the declared `[rating_scale_min, rating_scale_max]`.
- `rating_max` and `review_url` are optional (empty cells are fine).
- Every `(source_id, album_id)` pair must be unique.

## Adding a new source (no code required)

1. Create `data/critics/<source_id>/` and add the two files above.
2. Run the dataset validation tests / validator; every error pinpoints the file
   and line/field, e.g. `data/critics/<source>/ratings.csv:12: rating 11 outside
   declared scale [0, 10]`.
3. The existing `CriticDatasetAdapter` (which implements the `CriticRatingSource`
   port) picks the package up; the Recommendation Core is never modified.

The repository ships `data/critics/example-source/` as a working example that
passes all validation.

## Genre datasets

Genre packages live under `data/genres/<source_id>/` with `source.yaml`
(`genre_source` schema) and `genres.jsonl` (one `genre` record per line). The
`GenreDatasetAdapter` implements the `GenreSource` port and exposes dataset
provenance. See `data/genres/README.md`.
