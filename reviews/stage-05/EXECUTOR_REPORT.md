# OMDA G5 Release Audit — Executor Report (current)

> **This is the single current Executor report for the G5 release audit.** All
> earlier revisions of this file have been REMOVED, not appended to: every
> statement below describes the current repair candidate only. The superseded
> history (which commits made which claims) is listed in §8 so nothing is
> silently lost — but no stale number or claim from it remains in the body.
>
> Repair round: G5 final-audit re-review 1 (findings G5-R1-001 … G5-R1-003).
> Date: 2026-09-11.

## 1. Candidate identity

| Item | SHA |
|---|---|
| G5 base (accepted G4 merge) | `d9944aa27bede364daf3ef93256016d5954792f6` |
| Reviewer checkpoint under repair (this re-review) | `5138f458cc527c17388c35a9eed22867d68a2d9b` |
| Candidate rejected by this re-review | `6a6d309f2818ce8b4113f068017e608716eca72b` |
| Earlier rejected candidate | `69ccad929eb9092083ad0a098c12dd9b56d37f8d` |
| Prior Reviewer checkpoint | `98681dd1def88a563c9fff6cb8645c0058d2870e` |
| **Repair candidate** | tip of `exec/g5-release-audit` after this repair; reported to the Reviewer in the handoff message. `PROJECT_STATE.candidate_commit` is left `null` by Executor convention (the Reviewer records the reviewed SHA). |

Evidence-commit split (so the observation log can carry a real SHA): the repair
content is committed first, then the observation script is executed against that
exact revision and its verbatim JSON is committed as the immediately following
evidence commit. The evidence commit changes only evidence files, so the code
revision under test and the final candidate are identical; verify with
`git diff <repair>..<evidence> --stat`.

Branch: `exec/g5-release-audit`. Worktree clean at handoff.

## 2. Scope and first-round disposition

This round repairs **only** G5-R1-001, G5-R1-002 and G5-R1-003. The following
first-round findings were independently confirmed **RESOLVED** by the Reviewer
and are deliberately NOT touched: G5-001 (artifact installation), G5-002 (Album
exclusion), G5-003 (crash/restart matrix), G5-007 (operator/backup docs). No
accepted architecture, ADR or product semantic was changed.

## 3. G5-R1-001 (P1) — secret scan failed on the candidate and missed cookie shapes — **FIXED**

**Root cause.** `tests/unit/test_scan_secrets.py` contained a complete PushPlus
credential assignment and a complete PEM private-key header as literal text. The
hardened scanner correctly matched its own tracked fixture, so the mandatory
release gate returned exit 1 (2 hits) while all unit tests passed. The unit tests
exercised helper functions but never asserted the gate itself. The cookie rule
matched only `cookies*.json`.

**Repairs**

1. **Runtime-assembled synthetic credentials.** Every synthetic credential value
   is now built at test runtime from fragments
   (`"PUSHPLUS" + "_" + "TOKEN"`, `"-----BEGIN RSA " + "PRIVATE" + " KEY-----"`,
   `"sk" + "_" + "live" + "_" + "a" * 28`, …). The tracked source of the test file
   contains no complete credential shape, so the gate cannot self-match. **No
   test file or directory is exempted from scanning** — no allowlist, no
   `tests/` exclusion.
2. **Cookie path policy extended.** The path rule now refuses any basename that
   is a cookie-store name, with or without extension:
   `cookie|cookies|cookiejar|cookie[-_]?store|cookie[-_]?jar`. Covered shapes:
   `cookies.json`, `cookies.txt`, bare browser `Cookies`, `cookie_store.txt`,
   `cookiejar.txt`, `cookie-jar.json`, plus nested paths. Browser-profile and
   runtime-database checks are retained.
3. **Gate self-test added.** `tests/integration/test_g5_release_gate.py` asserts
   that `scan_tracked()` returns zero hits on the exact Git-tracked tree, that the
   informational count matches what was emitted, and that the documented CLI
   (`python tools/release_audit/scan_secrets.py`) **exits 0**. The full suite now
   fails if the release gate ever matches repository text again.
4. **Redacted evidence committed.** `reviews/stage-05/SECRET_SCAN_RESULT.txt`
   contains the direct run's output: **exit 0, `0 secret hits`, 9 informational
   placeholder references** (files that reference the codebase's own
   `@example.com` / `.invalid` rejection markers — including this report, which
   cites them). No credential value appears in the output or in this report.

**Tests**: `tests/unit/test_scan_secrets.py` — 13 cases (cookie shapes
parametrized, nested cookie path, ordinary files not flagged, binary safety,
redaction, force-added tracked artifacts incl. the new cookie forms);
`tests/integration/test_g5_release_gate.py` — 2 cases (tracked scan clean,
CLI exit 0).

## 4. G5-R1-002 (P1) — dependency/license inventory incomplete — **FIXED**

**Root cause.** The inventory was hand-written, omitted `pyproject_hooks`,
listed `typing_extensions` (not resolved for Python 3.12), and recorded versions
and roles without any license/SPDX column.

**Repairs**

1. **Generated, not written.** New tool
   `tools/release_audit/dependency_inventory.py` inspects the distributions
   actually resolved in ONE clean environment and emits package, exact version,
   dependency role, license/SPDX (PEP 639 `License-Expression`, else
   `Classifier: License ::`, else `License`), the metadata field the license was
   read from, and the authoritative source. Transitive roles are derived from the
   installed requirements (evidence-based), not asserted.
2. **One clean Python 3.12 environment.** Created fresh, installed
   `build setuptools wheel pytest ruff`, then ran the tool:
   **Python 3.12.14, 11 resolved distributions** — build 1.6.1, iniconfig 2.3.0,
   packaging 26.3, pip 26.2.1 (environment tooling, not a dependency), pluggy
   1.6.0, Pygments 2.21.0, pyproject_hooks 1.2.0, pytest 9.1.1, ruff 0.16.7,
   setuptools 84.0.0, wheel 0.48.0.
3. **`pyproject_hooks` included** with role "build tooling (transitive of
   build)" and license MIT.
4. **`typing_extensions` removed with an accurate explanation.** In the clean
   Python 3.12 environment **nothing requires `typing_extensions`** (verified
   across every installed distribution's metadata). It appeared only because the
   Executor's shared Python 3.13 development environment contains unrelated
   packages that require it — `python-docx`, `beautifulsoup4`, `pyee`. It is a
   leftover of that shared environment, not a dependency of this candidate.
5. **Platform-conditional dependencies documented separately** (not silently
   dropped): `build → colorama; os_name == "nt"`,
   `build → importlib-metadata >= 4.6; python_full_version < "3.10.2"`,
   `build → tomli >= 1.1.0; python_version < "3.11"`,
   `pytest → colorama>=0.4; sys_platform == "win32"`,
   `pytest → exceptiongroup>=1; python_version < "3.11"`,
   `pytest → tomli>=1; python_version < "3.11"`. Optional `extra == "…"` groups
   are opt-in and excluded, with counts recorded.
6. `LICENSES.md` §3 now carries the generated table, the declared-vs-resolved
   constraints, the conditional list and the `typing_extensions` correction;
   raw `pip freeze` and verbatim tool output are committed as
   `reviews/stage-05/DEPENDENCY_INVENTORY.txt`.

## 5. G5-R1-003 (P2) — stale/contradictory evidence files — **FIXED**

1. **This report** is now a single current-candidate document: the earlier body
   (761 tests, editable install, `UNLICENSED`, invalid first-round observation
   behaviour, zero production-file changes, six placeholders) is **deleted**, and
   §8 records only the commit history of those superseded claims.
2. **Corrected facts** in this report: **777 passed / 0 failed / 0 skipped**;
   **wheel** installed into a brand-new Python 3.12 venv from outside the
   checkout (not an editable install); code license **Apache-2.0** (not
   `UNLICENSED`); the Reviewer checkpoint is labelled a checkpoint, not a
   candidate; the scanner reports **9 informational placeholder references and 0
   secret hits** (exit 0).
3. **Observation log** now stores the script's verbatim JSON for all eight
   observations, including `timestamp`, `candidate_sha`, `command`,
   `data_version`, `preview_digest_sha256` and `official_history_before/after`
   (see `reviews/stage-05/OBSERVATION_LOG.md`).
4. **Risk register** reconciled against the real post-repair results: R-002
   (credentials/cookies in Git) and R-006 (external-data licensing) are re-argued
   from the actual gate exit 0 and the generated inventory, not from the earlier
   disproved claims.

## 6. Verification (this candidate)

| Command | Result |
|---|---|
| `python tools/release_audit/scan_secrets.py` (direct, tracked tree) | **exit 0 — 0 secret hits, 9 informational placeholder references** |
| `pytest -q -p no:cacheprovider` | **777 passed, 0 failed, 0 skipped** (767 → 777: +13 rewritten/expanded scanner cases and +2 new gate cases, −5 superseded cases) |
| `pytest -v` → `reviews/stage-05/TEST_RESULTS.txt` | 777 passed |
| `ruff check src tests tools browser_companion` | All checks passed |
| `git diff --check` | clean |
| `tools/release_audit/clean_env_check.sh` (wheel + sdist, fresh Python 3.12, outside checkout) | PASS — built wheel and sdist, installed the wheel, `import`/config/public `--dry-run` COMPLETE |
| `tools/release_audit/backup_restore.py` | PASS — consistent backup, corruption rejected, damaged copy preserved, atomic restore, logical verification |
| `tools/release_audit/observation_run.py` | 8/8 observations pass (7 public dry-runs, zero live calls, official history absent before/after; observation 8 = Album-exclusion evidence) |
| `tools/release_audit/dependency_inventory.py` (clean py3.12 env) | 11 distributions with version, role, license/SPDX and source |

## 7. Declarations

- Only G5-R1-001 … G5-R1-003 were repaired; G5-001/002/003/007 were not
  reopened; no accepted architecture, ADR or product semantic changed.
- No `ACCEPTED` / `RELEASE_CANDIDATE_ACCEPTED` written; no merge to `main`, no
  tag, no push, no publication, no scheduler, no post-G5 phase.
- No real credential was exposed; no live PushPlus/LLM/RYM call was made.
- `PROJECT_STATE.json` is set to **G5 / READY_FOR_REVIEW**.

## 8. Superseded history (no longer part of this report)

| Commit | Role | Claims it carried that are now superseded |
|---|---|---|
| `69ccad9` | first G5 audit candidate (rejected) | — |
| `98681dd` | Reviewer checkpoint (rejected `69ccad9`, opened G5-001…G5-008) | — |
| `6a6d309` | repair candidate (rejected by this re-review) | report body claiming 761 tests, editable install, `UNLICENSED`, six placeholder references, zero production-file changes; observation log without the promised JSON fields; risk register closing R-002/R-006 on evidence later disproved or found incomplete |
| `5138f45` | Reviewer checkpoint (rejected `6a6d309`, opened G5-R1-001…G5-R1-003) | — |

## 9. Residual risks (honest disclosure)

1. Curated data remains intentionally small (5 Genres × 4 Albums) and eventually
   exhausts with an explicit, tested failure.
2. v0.1 is deterministic/no-LLM by design (ADR-0002 D8).
3. ODP-1 (live MusicBrainz search) remains undecided and unimplemented.
4. PushPlus non-200 outcomes remain conservatively ambiguous (ADR-0001 §9).
5. Wheel runtime data uses the documented `<sys.prefix>/omda/data` data-files
   layout; the tested venv installation contract works.
6. Build/dev tools are declared as minimum ranges (`>=`), so resolved patch
   versions drift over time (this round: build 1.6.1, ruff 0.16.7);
   `reviews/stage-05/DEPENDENCY_INVENTORY.txt` records the versions and date of
   generation.
