# OMDA v0.1 License & Provenance Inventory

> G5 T5.3 (SPEC §7-14, MP §7): dependency and data license inventory.
> Audit date: 2026-08-26; updated 2026-08-29 (G5-005: Owner license decision,
> demo package re-authored); **updated 2026-09-11 (G5-R1-002: dependency
> inventory regenerated from one clean Python 3.12 release-audit environment,
> per-package license/SPDX and authoritative source added, `pyproject_hooks`
> included, `typing_extensions` correction recorded)**.
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

## 3. Build / development / test dependencies — RESOLVED INVENTORY

> G5-R1-002: this section is GENERATED from one clean Python 3.12 release-audit
> environment, not hand-written. Reproduce with:
>
> ```bash
> python3.12 -m venv /tmp/g5-r1-audit-venv
> /tmp/g5-r1-audit-venv/bin/python -m pip install --upgrade pip
> /tmp/g5-r1-audit-venv/bin/python -m pip install build setuptools wheel pytest ruff
> /tmp/g5-r1-audit-venv/bin/python tools/release_audit/dependency_inventory.py
> ```
>
> Raw `pip freeze` and the verbatim tool output are committed as
> `reviews/stage-05/DEPENDENCY_INVENTORY.txt`.
> Environment: **Python 3.12.14**. Generated 2026-09-11.

### 3.1 Every distribution actually resolved (with license and source)

License/SPDX is read from the installed distribution metadata (PEP 639
`License-Expression` first, then the `Classifier: License ::` entries); the
"Source" column is the authoritative project/metadata location for that exact
version.

| Package | Version | Dependency role | License / SPDX | License read from | Source |
|---|---|---|---|---|---|
| build | 1.6.1 | build (PEP 517 frontend, release check) | MIT | License-Expression (PEP 639) | https://build.pypa.io |
| iniconfig | 2.3.0 | test tooling (transitive of pytest) | MIT | License-Expression (PEP 639) | https://github.com/pytest-dev/iniconfig |
| packaging | 26.3 | build tooling (transitive of build/wheel/pytest) | Apache-2.0 OR BSD-2-Clause | License-Expression (PEP 639) | https://github.com/pypa/packaging |
| pip | 26.2.1 | environment tooling — **NOT a dependency of OMDA** | MIT | License-Expression (PEP 639) | https://pip.pypa.io/ |
| pluggy | 1.6.0 | test tooling (transitive of pytest) | MIT | Classifier: License :: OSI Approved :: MIT License | pluggy-1.6.0.dist-info (metadata) |
| Pygments | 2.21.0 | test tooling (transitive of pytest) | BSD-2-Clause | License-Expression (PEP 639) | https://pygments.org |
| pyproject_hooks | 1.2.0 | build tooling (transitive of build) | MIT | Classifier: License :: OSI Approved :: MIT License | https://github.com/pypa/pyproject-hooks |
| pytest | 9.1.1 | test runner (`dev` extra) | MIT | License-Expression (PEP 639) | https://docs.pytest.org/en/latest/ |
| ruff | 0.16.7 | linter/formatter (`dev` extra) | MIT | License-Expression (PEP 639) | https://github.com/astral-sh/ruff |
| setuptools | 84.0.0 | build (PEP 517 build backend) | MIT | License-Expression (PEP 639) | https://github.com/pypa/setuptools |
| wheel | 0.48.0 | build (wheel builder) | MIT | License-Expression (PEP 639) | https://github.com/pypa/wheel |

Transitive roles are evidence-based: `pip install`-resolved requirements of the
base install are `pyproject_hooks` (required by build), `packaging` (required by
build/wheel/pytest), `pluggy`, `iniconfig`, `Pygments` (required by pytest).

### 3.2 Declared constraints vs resolved versions

`pyproject.toml` declares minimum ranges for the dev extra and the build
backend; the table above records what a clean environment resolves today.

| Package | Declared in `pyproject.toml` | Resolved 2026-09-11 |
|---|---|---|
| setuptools | `>=68` (build-system requires) | 84.0.0 |
| pytest | `>=8` (`dev` extra) | 9.1.1 |
| ruff | `>=0.6` (`dev` extra) | 0.16.7 |
| wheel / build / pyproject_hooks / packaging / pluggy / iniconfig / Pygments | not declared (build tooling / transitive) | see 3.1 |

### 3.3 Interpreter/platform-conditional requirements NOT resolved here

These are declared by resolved packages but do not apply to CPython 3.12 on
POSIX, so they are absent from the environment — documented rather than dropped:

- `build` → `colorama; os_name == "nt"`
- `build` → `importlib-metadata >= 4.6; python_full_version < "3.10.2"`
- `build` → `tomli >= 1.1.0; python_version < "3.11"`
- `pytest` → `colorama>=0.4; sys_platform == "win32"`
- `pytest` → `exceptiongroup>=1; python_version < "3.11"`
- `pytest` → `tomli>=1; python_version < "3.11"`

Optional `extra == "..."` groups (e.g. setuptools' own test/doc/type extras) are
opt-in and are NOT installed; their counts are recorded in
`reviews/stage-05/DEPENDENCY_INVENTORY.txt`.

### 3.4 Correction: `typing_extensions` is NOT a dependency of this project

The previous revision of this file listed `typing_extensions==4.15.0` as a
"pytest transitive". That was wrong and has been removed: in the clean Python
3.12 release-audit environment **nothing requires `typing_extensions`** (verified
against every installed distribution's metadata). It was present only because the
Executor's shared Python 3.13 development environment contains unrelated
third-party packages that require it — `python-docx (typing_extensions>=4.9.0)`,
`beautifulsoup4 (typing-extensions>=4.0.0)`, `pyee (typing_extensions)`. It is a
leftover of that shared environment, not a dependency of OMDA's build, dev, test
or runtime set.

These packages are installed only in build/dev/test environments; they are not
shipped in the wheel and are never imported at runtime.

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
