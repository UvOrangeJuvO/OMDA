# OMDA pre-release privacy audit

Date: 2026-09-19

Scope: every file in the current `main` tree, the complete patch history of all
local branches and stage tags intended to remain usable, commit/tag identities,
tracked path classes, and the exact `0.1.0-beta.3` Skill ZIP.

## Initial finding

The first public `main` push contained review evidence with absolute workstation
paths. Those paths disclosed a local macOS account name, checkout layout,
Executor interpreter path, and one local attachment identifier. No password,
token, cookie, private key, private email, phone number, IP address, personal
Profile, listening history, or runtime database was found.

Old test revisions also contained contiguous synthetic credential fixtures.
They were not real secrets, but were included in the scrub to avoid misleading
secret-scanner alerts. A plausible-looking test-only contact address was
replaced with the public OMDA repository URL in the current test.

## Authorized remediation

With explicit Owner approval, every local branch and stage tag was rewritten to
replace workstation-specific values with `<REPO_ROOT>`,
`<WORKBUDDY_PYTHON>`, `<OWNER_PREFACE_SOURCE>`, or `<USER_HOME>`. The public
`main` update is restricted to `--force-with-lease` against the exact previously
verified remote commit. Local ignored recovery bundles are not release assets
and must never be pushed or distributed.

## Verification after remediation

- Current tracked-tree secret scan: **0 failing hits**.
- Current tracked-tree private marker scan: **0 hits**.
- Reachable branch/tag patch-history private marker scan: **0 hits**.
- Reachable branch/tag patch-history credential-pattern scan: **0 hits**.
- Forbidden tracked artifact classes: **0**.
- Reachable commit identities: only
  `UvOrangeJuvO <68496891+UvOrangeJuvO@users.noreply.github.com>`.
- Full repository test suite: **777 passed**, 0 failed, 0 skipped.
- Production lint scope (`src`, `tests`, `tools`): **PASS**.
- Skill tests: **69/69 passed** on Python 3.9.6 and Python 3.12.14.
- `git diff --check`: **PASS**.

## Beta ZIP boundary

- File: `omda-daily-discovery-0.1.0-beta.3.zip`.
- SHA-256:
  `2db790e444db2e6835d4593d930ef763b9c5b4deeb5973dc2b10d3cd630366e9`.
- Exact package file count: **15**.
- Package secret-pattern hits: **0**.
- Package private marker hits: **0**.
- The package contains no Profile, `history.json`, cookie, browser data,
  database, local absolute path, private contact address, or recovery bundle.
- The bundled 205-album source has no ratings; its Note column contains only
  original list sequence numbers. Its curator label is the non-identifying
  `OMDA 项目发起人`.

## Intentional public identifiers and content

The repository intentionally publishes the GitHub handle `UvOrangeJuvO`, its
GitHub-provided noreply address, the Owner-approved bilingual project preface,
and the Owner-approved album list. These are project attribution and project
content, not accidentally collected local data.

## Verdict

**PASS — ELIGIBLE FOR BETA PRE-RELEASE AFTER THE PROTECTED MAIN UPDATE**

No real credential or undisclosed personal contact information was found. The
Beta archive is within the documented local-first distribution boundary.
