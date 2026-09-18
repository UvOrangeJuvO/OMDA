# Contributing to OMDA

OMDA is a local-first, auditable daily music discovery agent. Community data is
**Git-reviewable text** (SPEC §3.3): Genre, Album-candidate and critic data
live under `data/` as `source.yaml` + records, validated against versioned
schemas. This guide covers the only two ways to add data and how to run the
verification gates.

## How to add a Genre or critic data package

1. Create `data/genres/<source_id>/source.yaml` (or
   `data/critics/<source_id>/`) with the required manifest fields, including
   the four license/provenance layers (ADR-0002 D1 — never blanket-license a
   package as CC0 without a valid basis).
2. Add records (`genres.jsonl` / `ratings.csv`) matching the schema for that
   package (`data/schemas/genre_source.schema.json` / `critic_source.schema.json`).
3. Validate locally:
   ```bash
   python -m pytest -q -p no:cacheprovider tests/unit/test_dataset_adapters.py tests/unit/test_schemas.py
   ```
4. Commit and open a review; a human review plus an explicit commit is what
   promotes a package into tracked data.

## How to contribute curated Album candidates (G3-007 flow)

Production Album candidates must be reviewed, non-demo records with canonical
MusicBrainz release-group MBIDs (G3-007). The **only** path that creates a
reviewable Git package is the explicit export/import contribution workflow:

```bash
# 1. Build a CandidateBatch for one Genre (see src/omda/adapters/curated.py).
# 2. Export it to an explicit target directory (never data/ by default):
python - <<'PY'
from pathlib import Path
from omda.adapters.contribution import export_curated_package
from omda.adapters.curated import CuratedAlbumSource
from omda.ports.domain import GenreRef

batch = CuratedAlbumSource(Path("data/albums/curated-omda")).source_batch(
    GenreRef("ambient", "Ambient", "Electronic", eligible=True)
)
export_curated_package(batch, target_dir=Path("out/curated-omda"), review_acknowledged=False)
PY
# 3. Review the exported source.yaml + albums.jsonl (license, origin, MBIDs).
# 4. Register the package in data/sources/registry.jsonl and commit explicitly.
```

A normal recommendation run **never** writes tracked data; runtime state and
caches live under the Git-ignored `var/` boundary.

## Before you open a pull request

- Run the full verification set:
  ```bash
  python -m pytest -q -p no:cacheprovider
  python -m ruff check src tests tools browser_companion
  git diff --check
  python tools/release_audit/scan_secrets.py
  ```
- No credentials, cookies, browser profiles, personal data or generated local
  databases may enter the repository (SPEC §7-14).
- Do not weaken, delete or broadly skip existing tests; disclose every skip in
  the review package.
- Gate protocol: each Gate uses a dedicated branch from the last accepted SHA;
  only the independent Reviewer may mark a Gate `ACCEPTED`; reports and test
  evidence are committed with the candidate.
