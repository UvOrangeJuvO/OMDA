# Genre source data

Community text is the Git source of truth (SPEC §3.3). A Genre package lives
under `data/genres/<source_id>/` and contains exactly two files:

```
data/genres/<source_id>/
├── source.yaml      # source metadata (genre_source schema)
└── genres.jsonl     # one genre record per line (genre schema)
```

## `source.yaml`

Flat mapping (one `key: value` per line; trailing ` # comment` allowed):

| key | required | meaning |
|---|---|---|
| `source_id` | yes | lowercase `[a-z0-9-]+`, must match the directory name |
| `display_name` | yes | human-readable source name |
| `license` | yes | data license / attribution statement |
| `origin_url` | yes | where the taxonomy comes from (`https://...`) |
| `retrieved_at` | yes | ISO 8601 datetime of retrieval |
| `dataset_version` | yes | version string of this dataset |
| `data_scope` | yes | what this dataset does (and does not) contain |
| `records_file` | yes | the records filename (`genres.jsonl`) |

## `genres.jsonl`

Each line is a record validated against the `genre` schema with fields
`genre_id`, `name`, `url`, `family`, `parents`, `eligible`, `source`.

- `genre_id` must be unique.
- `eligible` reflects objective data validity only — never popularity or
  perceived quality (SPEC §2.1). A genre whose data is missing/unknown is marked
  `eligible: false` so it is never selected.

The `GenreDatasetAdapter` (implements the `GenreSource` port) parses and
validates the package and exposes its provenance. Errors pinpoint the file,
line and field.

The repository ships `data/genres/demo-omda/` as a working example: an
independently authored 4-record demo fixture for the local, history-neutral
dry-run path (never an external-delivery source).
