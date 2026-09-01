# OMDA v0.1 License & Provenance Inventory

> G5 T5.3 (SPEC §7-14, MP §7): dependency and data license inventory.
> Audit date: 2026-08-26; updated 2026-08-29 (G5-005: Owner license decision,
> complete versioned dependency inventory, demo package re-authored).
> This file is an audit artifact; it does not itself grant or change any
> license. The Owner retains final license authority.

## 1. Code license

- **Owner decision (2026-08-29, OD-8): Apache-2.0.**
- `LICENSE` (Apache License 2.0, full text) is shipped in the repository and
  inside the built wheel (`omda-0.1.0.dist-info/licenses/LICENSE`).
- `pyproject.toml` declares `license = "Apache-2.0"` (SPDX expression); the
  built METADATA records `License-Expression: Apache-2.0`.
- The repository contains no vendored third-party source code.

## 2. Runtime dependencies

- **None.** `omda` runs on the Python standard library only
  (`dependencies = []` in `pyproject.toml`). No third-party runtime package is
  imported by `src/omda/**`.

## 3. Build / development / test dependencies

### 3.1 Build dependencies (required to build wheel/sdist from source)

| Package | Role | License (SPDX) |
|---|---|---|
| setuptools | build backend | MIT |
| wheel | wheel builder | MIT |
| build | PEP 517 frontend (release check only) | MIT |

### 3.2 Development / test dependencies (`[project.optional-dependencies] dev`)

| Package | Role | License (SPDX) |
|---|---|---|
| pytest | test runner | MIT |
| ruff | linter/formatter | MIT |

### 3.3 Resolved version snapshot (release-audit run, 2026-08-29)

Resolved versions recorded from the G5 clean-env rehearsal and the dev venv —
the versioned inventory required by G5-005:

| Package | Resolved version | Role |
|---|---|---|
| setuptools | 84.0.0 | build |
| wheel | 0.48.0 | build |
| build | 1.6.0 | build (release check) |
| pip | 26.2.1 (build env) / 25.0.1 (clean env) | tooling |
| pytest | 9.1.1 | dev/test |
| ruff | 0.16.3 | dev/lint |
| pluggy | 1.6.0 | transitive (pytest) |
| iniconfig | 2.3.0 | transitive (pytest) |
| packaging | 26.3 | transitive (pytest/setuptools) |
| Pygments | 2.21.0 | transitive (pytest) |
| typing_extensions | 4.15.0 | transitive (pytest) |

These are installed only in build/dev/test environments; they are not shipped
in the wheel or at runtime.

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

### 4.3 `data/genres/demo-omda` (DEMO only — never an external-delivery source)

- **G5-005**: the former `rym-sample` package was RE-AUTHORED as
  `demo-omda` — an independently authored 4-record demo fixture (original
  records, generic public genre names, illustrative `example.com` URLs). It no
  longer claims derivation from any upstream taxonomy, so no upstream relicensing
  obligation is asserted. **Not registered in the reviewed SourceRegistry and
  rejected by the production gate** (ADR-0002 D6/§8-2). Local/history-neutral
  dry-run only.

### 4.4 `data/critics/example-source` (illustrative demo only)

- Independently authored example critic source (one rating row) used by tests;
  no external material incorporated. Demo only.

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
  databases are committed. The hardened scanner
  (`tools/release_audit/scan_secrets.py`, G5-004) enforces a tracked-path
  denylist (cookie jars, browser profiles, runtime databases, .env, keys,
  netrc, credential files) plus content patterns over text files, prints only
  redacted kind/path/line output, and reports **0 failing hits** on this
  repository.
- Runtime state (SQLite) lives under Git-ignored `var/` and is never a
  community source of truth (SPEC §3.3).
