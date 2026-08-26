# OMDA v0.1 License & Provenance Inventory

> G5 T5.3 (SPEC §7-14, MP §7): dependency and data license inventory.
> Audit date: 2026-08-26. This file is an audit artifact; it does not itself
> grant or change any license. The Owner retains final license authority.

## 1. Code license

- `pyproject.toml` declares `license = "UNLICENSED"` — a deliberate pre-release
  placeholder. **Open finding for the release audit**: the Owner must choose a
  code license before an RC tag. No blanket code license is asserted here.
- The repository contains no vendored third-party source code.

## 2. Runtime dependencies

- **None.** `omda` runs on the Python standard library only
  (`dependencies = []` in `pyproject.toml`). No third-party runtime package is
  imported by `src/omda/**`.

## 3. Development / test dependencies (declared under `[project.optional-dependencies] dev`)

| Package | Role | License (SPDX) |
|---|---|---|
| pytest | test runner | MIT |
| ruff | linter/formatter | MIT |

These are installed only in dev/test environments; they are not shipped.

## 4. Curated data packages (Git source of truth)

Per ADR-0002 D1 the four license/provenance layers are kept separate; no
package is blanket-licensed as CC0.

### 4.1 `data/genres/curated-omda` (production, non-demo)

| Layer | Statement |
|---|---|
| Core facts | Genre names/taxonomy as public factual information — CC0-1.0 |
| Supplementary used | none incorporated |
| Upstream reference | Wikipedia articles referenced for verification only; no article text copied (CC BY-SA 4.0 text NOT incorporated) |
| Derived package | This curation — CC0-1.0 (see package README) |

### 4.2 `data/albums/curated-omda` (production, non-demo)

| Layer | Statement |
|---|---|
| Core facts | MusicBrainz release-group facts (MBID/title/artist/year) — CC0-1.0 |
| Supplementary used | none incorporated (MusicBrainz search index/tag associations are CC BY-NC-SA 3.0 supplementary and NOT part of this package) |
| Service terms | MusicBrainz web service free for non-commercial use; commercial use requires a commercial plan |
| Derived package | This curation — CC0-1.0 (see package README) |

### 4.3 `data/genres/rym-sample` (DEMO only — never an external-delivery source)

- Illustrative demo subset of RYM taxonomy. **Not registered in the reviewed
  SourceRegistry and rejected by the production gate** (ADR-0002 D6/§8-2).
  Local/history-neutral dry-run only.

## 5. External services

- **PushPlus** (`https://www.pushplus.plus/send`): external delivery channel;
  token supplied at runtime via environment variable, never committed. No
  documented no-side-effect category exists for non-200 responses, so all such
  responses are treated as ambiguous (ADR-0001 §9).
- **MusicBrainz** web service: used only by the one-time data-preparation tool
  (`tools/curate_mbids.py`, owner-supplied User-Agent) and by the (not yet
  enabled) ODP-1 live-search path. Runtime `--deliver` makes no MusicBrainz
  calls.
- **No other external service** is called at runtime.

## 6. Attestations

- No credentials, cookies, browser profiles, personal data or generated local
  databases are committed (see `tools/release_audit/scan_secrets.py` — 0 hits).
- Runtime state (SQLite) lives under Git-ignored `var/` and is never a
  community source of truth (SPEC §3.3).
