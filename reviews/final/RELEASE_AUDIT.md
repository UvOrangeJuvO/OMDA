# OMDA v0.1.0-rc1 Final Release Audit — Re-review 1

## 1. Review identity

- Reviewer: GPT-5.6 Sol / Codex (independent Reviewer role)
- Audit date: 2026-09-01
- Architecture baseline: `8a2e82072afca8fe7217c9fc79288d99a94e01ce`
- G5 base: `d9944aa27bede364daf3ef93256016d5954792f6`
- Prior rejected candidate: `69ccad929eb9092083ad0a098c12dd9b56d37f8d`
- Prior Reviewer checkpoint: `98681dd1def88a563c9fff6cb8645c0058d2870e`
- Re-review candidate: `6a6d309f2818ce8b4113f068017e608716eca72b`
- Candidate branch at review time: `exec/g5-release-audit`
- Scope: Handbook Prompt 10, Implementation Plan T5.1–T5.5, and the eight
  findings from the prior final audit

This review evaluates the exact candidate above. It authorizes no tag, push,
publication, deployment, scheduler, or live external delivery.

## 2. Executive conclusion

The candidate directly follows the prior Reviewer checkpoint and preserves the
accepted G0–G4/ADR chain. Most of the first-round release blockers are genuinely
fixed: the wheel now runs outside the checkout; the Album-exclusion and
crash/restart tests reach the intended paths; Apache-2.0 metadata and an
independently authored demo replace the unresolved code/RYM licensing state;
the backup rehearsal and seven public dry-runs are reproducible.

The candidate is nevertheless not releasable because its mandatory repository
secret scan returns exit code 1 on the exact candidate, contrary to the
Executor report and the T5.3 zero-hit acceptance rule. The dependency/license
inventory and committed evidence reports also remain internally incomplete.
The remaining work is a narrow G5 evidence/tooling repair; accepted product
semantics and the completed G5-001/G5-002/G5-003/G5-007 implementation work
must not be reopened.

## 3. Re-review findings

### G5-R1-001 — P1 — The mandatory secret scan fails on the release candidate and still misses common cookie artifacts

**Evidence**

Running the documented command on exact candidate
`6a6d309f2818ce8b4113f068017e608716eca72b` produced:

```text
SECRET_SCAN: 2 FAILING hit(s):
  FAIL[token-pushplus-token]: tests/unit/test_scan_secrets.py:21
  FAIL[token-private-key-block]: tests/unit/test_scan_secrets.py:22
EXIT_CODE=1
```

The literal synthetic PushPlus assignment and private-key header added to
`tests/unit/test_scan_secrets.py` are tracked repository text, so the hardened
scanner correctly matches them. The unit tests exercise helper functions but
never assert that the final `scan_tracked()`/CLI gate returns zero on the
candidate itself. Consequently all 767 tests pass while the actual release
gate fails.

The tracked-path rule at `tools/release_audit/scan_secrets.py:44` only catches
cookie names ending in `.json`. Independent safe fixtures showed that empty
`cookies.txt`, bare `Cookies`, and `cookie_store.txt` paths produce no hit,
despite the scanner and risk register claiming the cookie-jar class is covered.

This also invalidates:

- `reviews/stage-05/EXECUTOR_REPORT.md:154,169`, which claim repository scan
  zero;
- `governance/RISK_REGISTER.md:12`, which closes P0 risk R-002 on that claim;
- the user handoff's `Secret scan: 0` statement.

No real credential was exposed by this review; this finding is about a failing
and incomplete release gate.

**Required repair / acceptance evidence**

1. Construct synthetic token/private-key values at test runtime from fragments
   so the tracked source itself does not contain a complete credential shape.
   Do not broadly exempt test files from scanning.
2. Extend the path policy and fixtures to cover common cookie-jar forms,
   including `cookies.txt`, bare browser `Cookies`, and equivalent cookie-store
   names, while keeping database/profile checks.
3. Add an integration assertion that the exact tracked repository scan returns
   zero and exits 0; the full suite must fail if the release gate self-matches.
4. Re-run the scanner directly and commit its redacted output/count as evidence.
   Any real/synthetic secret value must remain absent from output.

### G5-R1-002 — P1 — The claimed complete dependency/license inventory is not complete or reproducible

**Evidence**

The Reviewer created a fresh Python 3.12 environment with the versions claimed
in `LICENSES.md` and installed the G5 build/test tools. The resolved environment
contains:

```text
build==1.6.0
pyproject_hooks==1.2.0
packaging==26.3
setuptools==84.0.0
wheel==0.48.0
pytest==9.1.1
iniconfig==2.3.0
pluggy==1.6.0
Pygments==2.21.0
ruff==0.16.3
```

`build==1.6.0` declares `pyproject_hooks` as a dependency, but
`LICENSES.md:41-58` omits it. Conversely that table lists
`typing_extensions==4.15.0` as a pytest transitive dependency although it was
not resolved in the clean Python 3.12 environment. The transitive table records
versions and roles but no license/SPDX field, so it does not fulfill its own
claim of a complete dependency **and license** inventory.

This makes G5-005 only partially resolved and invalidates the R-006 “complete
build/dev/transitive versioned list” rationale in
`governance/RISK_REGISTER.md:17`. The Owner's Apache-2.0 decision, LICENSE file,
wheel metadata, independently authored demo package, and MusicBrainz
provenance remain accepted by this re-review.

**Required repair / acceptance evidence**

Generate the inventory from one clean, documented release-audit environment.
For every actually resolved build/dev/test/transitive package, record package,
exact version, dependency role, license/SPDX result, and the authoritative
metadata/source used. Include `pyproject_hooks`; remove or correctly explain
packages not resolved for Python 3.12 and document platform markers separately.
Reconcile R-006 only after the generated/resolved list and license table agree.

### G5-R1-003 — P2 — Committed G5 evidence files contain stale and contradictory claims

**Evidence**

- `reviews/stage-05/OBSERVATION_LOG.md:16` labels its records “raw JSON,” and
  lines 29–31 say full output was captured verbatim. The committed records omit
  the promised timestamps, candidate SHA, data version, command, and preview
  digests. Independent execution did produce these fields and all eight
  observations passed, but that exact evidence was not captured in the file.
- The main body of `EXECUTOR_REPORT.md` still says 761 tests, editable install,
  `UNLICENSED`, invalid first-round observation behavior, zero production-file
  changes, and six placeholder references. A later appendix contradicts those
  statements instead of marking/replacing the superseded material. The current
  scanner reports eight informational placeholder references before its two
  failures.
- The repair heading calls Reviewer checkpoint `98681dd…` a “candidate,” while
  the actual candidate is `6a6d309…`.
- R-002 and R-006 are marked CLOSED using the false/incomplete evidence in
  G5-R1-001 and G5-R1-002, so G5-008 is not yet fully reconciled.

**Required repair / acceptance evidence**

Make the stage report a single unambiguous current-candidate report or clearly
mark the old body as superseded. Commit the full observation JSON lines exactly
as emitted (including SHA/timestamps/digests), correct all counts and identities,
and make the risk register reflect the real post-repair scan and inventory.

## 4. First-round finding disposition

| Prior finding | Re-review status | Evidence |
|---|---|---|
| G5-001 artifact installation | **RESOLVED** | Wheel/sdist built; wheel installed in a fresh Python 3.12 venv; import, config and public dry-run passed outside checkout; wheel from extracted sdist also built successfully. |
| G5-002 Album exclusion | **RESOLVED** | Targeted 40-Genre fixtures enter Album selection, reject committed canonical identity, select nine new Albums, and prove explicit exclusion-caused shortage. |
| G5-003 crash/restart | **RESOLVED** | Nine-window matrix uses a real SQLite file, closes the old connection, creates a new store/engine, and asserts exact state/calls/history/receipt outcomes. |
| G5-004 secret gate | **OPEN** | G5-R1-001: candidate scan exits 1 and cookie-path coverage is incomplete. |
| G5-005 license/provenance | **PARTIAL** | Apache-2.0/code/demo/data provenance resolved; dependency/license inventory remains incomplete (G5-R1-002). |
| G5-006 observations | **FUNCTION PASSED / EVIDENCE REPAIR** | Independent run: seven public dry-runs + targeted Album observation passed; committed log is not the claimed verbatim output (G5-R1-003). |
| G5-007 operator/backup docs | **RESOLVED** | README covers installation/config/delivery/backup/recovery/troubleshooting; strict backup rehearsal passed corruption rejection, preservation, atomic restore and logical verification. |
| G5-008 risk governance | **OPEN** | R-002/R-006 were closed using evidence disproved or incomplete in this audit. |

## 5. Independent verification summary

- Worktree clean before and after read-only validation.
- Candidate direct parent equals Reviewer checkpoint `98681dd…`; merge-base
  equals accepted G4 merge `d9944aa…`.
- Accepted G0–G4 candidates, accepted G3-007 checkpoint, and both Accepted ADRs
  are in the candidate history.
- Full isolated suite: **767 passed, 0 failed, 0 skipped**.
- Ruff: **All checks passed**; candidate `git diff --check`: clean.
- Wheel and sdist built successfully. The wheel contains runtime schemas,
  registry, curated/demo data and Apache LICENSE metadata.
- Fresh Python 3.12 wheel install outside checkout: import/config/public dry-run
  **COMPLETE**; preview SHA-256 independently recorded.
- A wheel rebuilt from the extracted sdist completed successfully.
- Targeted Album exclusion and real-SQLite crash matrix passed within the full
  suite.
- Backup/recovery rehearsal: **PASS**.
- Observation script: **8/8 PASS**, exact candidate SHA emitted, seven dry-runs
  reported zero live calls and absent-before/after official history.
- Browser Companion human-action/no-bypass contracts remain green in the full
  suite.
- Mandatory tracked repository secret scan: **FAIL, exit 1, two hits**.

## 6. Known non-blocking limitations

- Curated data remains intentionally small and eventually exhausts with an
  explicit, tested failure.
- v0.1 is deterministic/no-LLM per accepted ADR-0002 D8.
- ODP-1 live MusicBrainz search remains unimplemented and disabled.
- PushPlus non-200 outcomes remain conservatively ambiguous per ADR-0001.
- Wheel runtime data uses the documented `<sys.prefix>/omda/data` data-files
  layout; the tested venv installation contract works.

## 7. Repair and rollback instructions

1. Keep `6a6d309f2818ce8b4113f068017e608716eca72b` immutable and retain this
   Reviewer checkpoint in the repair branch history.
2. Repair only G5-R1-001 through G5-R1-003; do not reopen the resolved findings
   or accepted architecture/product rules.
3. Re-run the direct repository scanner first, then the full suite, Ruff,
   artifact build/install, backup rehearsal, and observations.
4. Return a new complete candidate with `G5 / READY_FOR_REVIEW` only. Do not
   write acceptance, merge main, create a tag, push, publish, schedule, or enter
   another Gate.
5. If repair regresses behavior, revert only the new repair commit(s) to this
   Reviewer checkpoint; do not rewrite accepted history or touch user SQLite
   data.

## 8. Unique verdict

**CHANGES_REQUESTED**

`6a6d309f2818ce8b4113f068017e608716eca72b` is not accepted as
`v0.1.0-rc1`. No release tag or post-G5 action is authorized.

---

# Final Re-review 2 — candidate `3aa76ea5bb35e219550cf65328549de47c98269b`

## 9. Review identity and scope

- Reviewer: GPT-5.6 Sol / Codex (independent Reviewer role)
- Review date: 2026-09-18
- G5 base (accepted G4 merge):
  `d9944aa27bede364daf3ef93256016d5954792f6`
- Rejected candidate under repair:
  `6a6d309f2818ce8b4113f068017e608716eca72b`
- Reviewer checkpoint:
  `5138f458cc527c17388c35a9eed22867d68a2d9b`
- Repair implementation:
  `781d52b54693cf81258949c3e14b08195a978bdc`
- Final evidence candidate:
  `3aa76ea5bb35e219550cf65328549de47c98269b`
- Candidate branch observed: `exec/g5-release-audit`

The candidate chain is linear: the repair implementation directly follows the
Reviewer checkpoint and the final candidate directly follows the repair. The
last commit changes only `reviews/stage-05/OBSERVATION_LOG.md`; therefore the
code tested at `781d52b` and the code in the final candidate are identical.
The merge-base with the supplied G5 base is the exact accepted G4 merge.

This re-review first verifies closure of G5-R1-001 through G5-R1-003, then
performs the release-level regression checks required by Handbook Prompt 10.
It does not authorize a push, publication, deployment, scheduler, external
delivery, or final `v0.1.0` release.

## 10. Blocking-finding closure

| Finding | Final status | Independent evidence |
|---|---|---|
| G5-R1-001 — mandatory secret gate | **CLOSED** | The exact tracked candidate scan exits 0 with 0 failing hits and 9 informational placeholder references. Cookie-jar coverage now includes JSON/text/bare-browser/store/jar forms. The full suite includes helper, forced-index and real tracked-tree/CLI gate tests; no test-tree exemption was introduced. |
| G5-R1-002 — dependency/license inventory | **CLOSED** | `LICENSES.md` and `DEPENDENCY_INVENTORY.txt` record every distribution resolved in the documented clean Python 3.12 audit environment with exact version, role, license/SPDX evidence and source. `pyproject_hooks` is included. `typing_extensions` is correctly removed from the OMDA inventory and explained as unrelated shared-environment residue. Platform-conditional requirements are listed separately. |
| G5-R1-003 — stale/contradictory evidence | **CLOSED** | The Executor report is a single current-candidate report; counts, identities and risk closures agree. The observation log contains the actual eight JSON records with timestamps, candidate SHA, command/config/data version, live-call count, preview digests and official-history before/after evidence. R-002 and R-006 are reconciled against the repaired gates. |

No new P0 or P1 finding was discovered. No accepted architecture or product
semantic was changed by the repair.

## 11. Independent verification

All checks below were run against an isolated local clone checked out at exact
candidate `3aa76ea5bb35e219550cf65328549de47c98269b`, using Python 3.12.14 where
applicable:

- Commit ancestry, parent chain, accepted G0–G4/ADR history and exact merge-base:
  **PASS**.
- Mandatory tracked repository secret scan: **exit 0; 0 failing hits; 9
  informational placeholder references**.
- Complete test suite: **777 passed, 0 failed, 0 skipped**.
- Ruff over `src`, `tests`, `tools` and `browser_companion`: **All checks
  passed**.
- `git diff --check` over accepted G4 base through candidate: **PASS**.
- Wheel and sdist build plus clean Python 3.12 wheel installation outside the
  checkout: **PASS**; import, config/data resolution and public dry-run all
  completed.
- Backup/corruption/atomic-restore rehearsal: **PASS**; damaged copy preserved
  and schema/history/identity/receipt/journal state verified after restore.
- Controlled observation script: **8/8 PASS**; seven public dry-runs made zero
  live calls and left official history absent, while the eighth run rejected a
  previously committed canonical Album identity and selected nine unique new
  Albums.
- The complete suite continues to cover the Prompt 10 failure matrix, history
  atomicity, cooldown/repeat boundaries and Browser Companion human-action /
  no-bypass contracts.
- Source worktree was clean before the verdict update. No live PushPlus, LLM,
  RYM or MusicBrainz request was made during review.

The first local validation attempt lacked permission to write the synthetic
cookie fixture and Git index in the source checkout. That sandbox-only failure
was not treated as product evidence. Repeating the exact suite in a writable
isolated clone produced the authoritative 777/777 result above.

## 12. Release acceptance matrix

| G5 criterion | Status | Evidence |
|---|---|---|
| T5.1 clean installation and executable dry-run | **PASS** | wheel/sdist build and fresh wheel install outside checkout |
| T5.2 E2E and seven-class failure matrix | **PASS** | complete 777-test suite and previously accepted G5 matrix evidence |
| T5.3 secrets, code/dependency/data licensing | **PASS** | zero-hit mandatory scan; Apache-2.0 artifacts; generated dependency inventory and provenance table |
| T5.4 backup/restore and contributor/operator documentation | **PASS** | strict rehearsal plus README/CONTRIBUTING contracts |
| T5.5 at least seven history-neutral observations | **PASS** | seven public dry-runs plus targeted Album-exclusion observation |
| Open P0/P1 findings | **NONE** | G5-R1-001 through G5-R1-003 closed |

## 13. Known non-blocking limitations

1. The curated v0.1 package is intentionally small (5 Genres × 4 Albums) and
   eventually fails explicitly when exhausted.
2. v0.1 uses deterministic narrative rather than an LLM, per accepted ADR-0002
   D8.
3. ODP-1 live MusicBrainz search remains unimplemented and disabled.
4. PushPlus non-200 outcomes remain conservatively ambiguous per ADR-0001.
5. Wheel runtime data uses the documented `<sys.prefix>/omda/data` data-files
   layout.
6. Build/dev tools use minimum-version ranges, so later clean environments may
   resolve newer patch versions; the committed inventory remains the dated
   evidence for the audited environment.

## 14. Rollback and next-step boundary

- The accepted content SHA is
  `3aa76ea5bb35e219550cf65328549de47c98269b`; the later Reviewer verdict commit
  is governance evidence, not a new release-content candidate.
- If final packaging requires any content or release-metadata file change, that
  new commit must return for final audit before a tag is created.
- Prompt 11 may now prepare local release packaging and the proposed
  `v0.1.0-rc1` tag. This verdict itself does not create the tag and does not
  authorize pushing or publishing it.
- For regression, preserve current evidence and use a history-preserving revert;
  never rewrite accepted history or delete user SQLite data.

## 15. Unique final verdict

**RELEASE_CANDIDATE_ACCEPTED**

OMDA candidate `3aa76ea5bb35e219550cf65328549de47c98269b` is accepted as the content for
`v0.1.0-rc1`, subject to the Prompt 11 boundary above. No tag, push,
publication, deployment, scheduler or live external delivery was performed by
this review.
