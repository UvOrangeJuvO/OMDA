# OMDA v0.1.0-rc1 Final Release Audit

## 1. Review identity

- Reviewer: GPT-5.6 Sol / Codex (independent Reviewer role)
- Audit date: 2026-08-26
- Architecture baseline: `8a2e82072afca8fe7217c9fc79288d99a94e01ce`
- G5 base: `d9944aa27bede364daf3ef93256016d5954792f6`
- Candidate: `69ccad929eb9092083ad0a098c12dd9b56d37f8d`
- Candidate branch at review time: `exec/g5-release-audit`
- Scope: Handbook Prompt 10 and `governance/IMPLEMENTATION_PLAN.md` T5.1–T5.5

This audit evaluates the exact candidate above. It does not authorize a tag,
push, publication, deployment, scheduler, or live external delivery.

## 2. Executive conclusion

The accepted G0–G4 architecture chain is intact, the candidate worktree was
clean, the full source-checkout regression suite passed, and the existing
Browser Companion contract remains within the approved human-intervention
boundary. However, the G5 release evidence is not yet sufficient for an RC:
the built wheel cannot execute from a clean installation, two required failure
scenarios are false-positive tests, the secret scanner can miss forbidden
tracked artifacts, release licensing is unresolved, and the operating/backup
documentation is incomplete.

These findings are repairable inside G5 and do not reopen accepted product
semantics. OD-8 is an Owner decision and must not be guessed by the Executor.

## 3. Findings

### G5-001 — P1 — The built release artifact cannot run outside the checkout

**Evidence**

- `tools/release_audit/clean_env_check.sh:25` installs the repository with
  `pip install -e`, so imports and root-level `data/` resolve from the source
  checkout. This does not test the distributable artifact.
- `pyproject.toml:17-18` discovers Python packages under `src` but defines no
  package-data layout for the root `data/` tree.
- `src/omda/production.py:73-78` derives the default data directory by walking
  above the installed module and expecting a sibling `data/` directory.
- The Reviewer built `omda-0.1.0-py3-none-any.whl` from an archive of the exact
  candidate, installed it into a fresh Python 3.12 venv, changed to a directory
  outside the repository, and ran the public dry-run. The wheel contained no
  `data/` files and failed with:

  ```text
  omda: run failed: .../lib/python3.12/data/genres/rym-sample: missing source.yaml
  ```

**Required repair / acceptance evidence**

1. Put required schemas and curated/demo runtime data in an explicit installed
   resource layout (for example, package data accessed through
   `importlib.resources`) or define another complete, documented installation
   contract.
2. Build both wheel and sdist from the exact repair candidate.
3. Install the wheel into a brand-new Python 3.12 environment from outside the
   checkout and run import, config validation, and public dry-run successfully.
4. Make the release check install the built artifact, not an editable checkout,
   and record resolved tool/dependency versions.

### G5-002 — P1 — Required “already recommended Album among 9” evidence does not exercise Album exclusion

**Evidence**

- `tests/integration/test_g5_e2e_matrix.py:206-225` runs the same small curated
  set twice and accepts any second-run `FAILED` state as “pool exhausted.”
- Independent journal inspection shows that the second run fails during Genre
  planning because the 30-pick Genre cooldown leaves too few eligible Genres;
  it never fetches or selects the nine Album candidates. Therefore the test can
  pass even if permanent Album exclusion is broken.
- `tools/release_audit/observation_run.py:96-120` repeats the same construction
  and labels the same Genre-planning failure as a permanent-exclusion
  observation.

**Required repair / acceptance evidence**

Use a controlled fixture that keeps Genre eligibility/cooldown satisfiable,
places one or more already committed canonical Album identities in the current
nine-candidate path, and asserts the exact Album-level result: committed
identities are rejected, no identity repeats, and either nine new real Albums
are selected or the explicit shortage is proven to be caused by Album
exclusion. An unrelated `FAILED` state must fail the test.

### G5-003 — P1 — Crash/restart matrix is not a durable fresh-process simulation

**Evidence**

- `CrashPointHistory` in
  `tests/integration/test_g5_e2e_matrix.py:302-325` subclasses
  `InMemoryHistory` and delegates only journal append and history commit.
  Inherited operation/attempt/receipt methods write to the wrapper's separate
  in-memory dictionaries, not the `inner` object later presented as the
  “durable store.”
- `test_g5_class7...` at lines 336-358 accepts any of `COMPLETE`, `FAILED`, or
  `RECOVERING` for every crash window and only asserts broad 0-or-final counts.
  That permits loss of recovery evidence and does not prove the documented
  state transition for each window.
- In an independent trace, crashes after `DELIVERING` and `DELIVERED` both
  recovered only to `RECOVERING`; the fresh engine could not see the wrapper's
  operation/receipt evidence. That is a property of the fake, not proof of the
  SQLite restart contract.

**Required repair / acceptance evidence**

Run the matrix against a real temporary SQLite file, close the old connection,
construct a new `SqliteHistory` and engine, then assert the exact expected
state, external-call count, receipt/operation evidence, journal tail, and 0-or-3
/ 0-or-9 official-history result for each crash point. In particular, finalized
delivered evidence must complete without a second push; genuinely ambiguous
claim windows may require human resolution as ADR-0001 specifies.

### G5-004 — P1 — Secret/cookie/profile release gate has false negatives and can disclose matched secrets

**Evidence**

- `tools/release_audit/scan_secrets.py:47` skips `.sqlite3` and `.db` content.
- The scanner checks file contents but has no tracked-path denylist for cookie
  jars, browser profiles, runtime databases, `.env`, or credential artifacts.
- The Reviewer force-added empty synthetic `cookies-live.json` and
  `leaked-state.sqlite3` files in an isolated copy. The scanner still returned
  `SECRET_SCAN: 0 secret hits`.
- Lines 68-84 print the matched text snippet, which can copy a real secret into
  CI/review logs.

The current candidate did not independently reveal an actual credential, but a
scanner that misses the required artifact classes cannot serve as T5.3 release
evidence.

**Required repair / acceptance evidence**

Add a tracked-path policy for forbidden secret/cookie/profile/database
artifacts, scan text with robust credential patterns, handle binary files
safely, and print only redacted type/path/line information. Add automated
positive and negative fixtures proving forbidden filenames, database/profile
paths, representative synthetic tokens, and output redaction. Never emit the
matched secret.

### G5-005 — P1 / OWNER_DECISION_REQUIRED — Open-source and data licensing is unresolved

**Evidence**

- `pyproject.toml:10` declares `UNLICENSED`; there is no code `LICENSE` granting
  reuse rights. `LICENSES.md:7-12` acknowledges that an Owner choice is still
  required. `governance/IMPLEMENTATION_PLAN.md:584` classifies OD-8 as an Owner
  product decision.
- `data/genres/rym-sample/source.yaml:1-19` says the sample is derived from the
  RateYourMusic taxonomy while asserting CC0 for the sample/derived package,
  but the repository supplies no upstream permission or license evidence for
  that relicensing. Being demo-only does not remove distribution obligations.
- `governance/RISK_REGISTER.md:15` still marks the external-data licensing risk
  R-006 OPEN.
- `LICENSES.md` lists only the direct pytest and Ruff development requirements;
  it omits the build dependency (`setuptools`) and the transitive packages
  actually resolved during the audit, so it is not a complete dependency and
  license inventory.

The MusicBrainz statements were independently consistent with the official
[MusicBrainz data license](https://musicbrainz.org/doc/About/Data_License) and
[web-service terms](https://musicbrainz.org/doc/MusicBrainz_API). This does not
resolve the OMDA code license or the RYM-derived sample.

**Required repair / acceptance evidence**

1. Owner explicitly selects the OMDA code license; Executor then adds the
   correct `LICENSE` and SPDX-compatible project metadata. Reviewer must check
   the resulting terms.
2. Remove/re-author the RYM sample as independently authored fixture data, or
   provide verifiable upstream rights and accurate provenance/license terms.
   Do not infer CC0 merely because the records are factual or illustrative.
3. Generate or document a complete, versioned inventory covering build,
   development, transitive, runtime, and distributed data components.

### G5-006 — P1 — The required seven-observation acceptance evidence is not established

**Evidence**

- `tools/release_audit/observation_run.py:72-94` creates seven unrelated
  in-memory databases and performs one fake delivery per run. These are neither
  seven invocations of the public `--dry-run` path (which must make zero
  delivery calls) nor a consecutive manual-operation history.
- Isolation makes official-history pollution impossible by construction rather
  than measuring before/after invariants on the relevant store.
- Observation 8 is invalid for permanent Album exclusion for the reason in
  G5-002, although `OBSERVATION_LOG.md` reports all invariants satisfied.

**Required repair / acceptance evidence**

Record at least seven honest public dry-runs or controlled manual runs with
timestamps, candidate SHA/config/data versions, command/mode, zero live calls
for dry-run, output digest, and before/after official-history checks. If runs
are intentionally same-day and automated, label them that way; do not present
them as elapsed operational stability. Replace observation 8 with the targeted
Album-exclusion evidence from G5-002.

### G5-007 — P2 — Operator documentation and backup/restore rehearsal are incomplete

**Evidence**

- `README.md:10` still says the project is at G0 and lines 19-21 only describe
  the original WorkBuddy G0 operation. It has no installation, public dry-run,
  explicit delivery, configuration, troubleshooting, history location, or
  recovery guide required by T5.1.
- No user-facing backup/restore procedure exists outside the audit script and
  reports, despite T5.4 requiring textual steps.
- `tools/release_audit/backup_restore.py:79-85` prints a warning if the corrupt
  store opens successfully but still proceeds to PASS. Lines 87-89 overwrite
  the live file directly and do not document process shutdown, preservation of
  the damaged copy, atomic replacement, permissions, or post-restore checks.

**Required repair / acceptance evidence**

Update README/operator documentation for a new user, add safe backup/restore
and forward-fix guidance, and make the rehearsal fail nonzero if corruption is
not rejected. Rehearse consistent backup, stopped-writer restore, preservation
of the damaged store, atomic replacement, and logical integrity verification.

### G5-008 — P2 — Risk and final-status governance are stale

**Evidence**

`governance/RISK_REGISTER.md` still describes its last update as G1 and leaves
every P0/P1 risk OPEN, while its own line 34 says an unmitigated P0/P1 blocks the
corresponding Gate. Several risks have accepted evidence from G2–G4; others map
directly to current G5 findings. The release record therefore does not state
which risks are closed, mitigated, accepted as limitations, or still blocking.

**Required repair / acceptance evidence**

Reconcile each risk against an exact test/report/ADR reference and use an
honest status. Any remaining P0/P1 must be resolved or explicitly escalated;
known non-blocking limitations belong in the next release-audit candidate.

## 4. Evidence that passed

- Exact candidate and clean worktree were verified before review.
- Candidate merge-base equals the G4 accepted merge
  `d9944aa27bede364daf3ef93256016d5954792f6`.
- Accepted G0–G4 candidates and the accepted G3-007 checkpoint are ancestors of
  the candidate. Tags `gate-g0-accepted` through `gate-g4-accepted` resolve to
  the expected controlled merge commits.
- Independent checkout run: `761 passed, 0 failed, 0 skipped`; Ruff passed.
- Existing tests cover configuration rejection and the Browser Companion
  login/CAPTCHA/rate-limit/session-invalid human-action classifications. The
  contract suite forbids stealth, CAPTCHA solving, Cloudflare bypass, mass
  crawl, and Album Detail fan-out.
- Source-checkout public dry-run succeeded and produced a 3×3 preview without a
  live PushPlus call.
- Nominal backup → truncation → restore rehearsal completed, but it does not
  close G5-007 because the failure assertion and operator procedure are weak.
- Current tracked tree did not show an obvious credential during independent
  inspection; this does not validate the deficient scanner identified in
  G5-004.

## 5. Known limitations at this verdict

- v0.1 uses deterministic narrative generation and no external LLM call, per
  accepted ADR-0002 D8. The Handbook's “LLM failure” case is therefore correctly
  represented by proving that an injected exploding LLM is never invoked.
- The curated source set is intentionally small. Exhaustion is acceptable only
  when its exact cause is explicit and no fabricated/repeated Album is emitted.
- External delivery and SQLite history are not globally atomic; ADR-0001's
  conservative at-most-one protocol and human resolution remain the accepted
  design.
- No live RYM session or real PushPlus message was required or authorized for
  this independent audit.

## 6. Repair and rollback instructions

1. Keep `69ccad929eb9092083ad0a098c12dd9b56d37f8d` immutable as the rejected G5
   candidate and retain this Reviewer commit in the repair branch history.
2. Owner resolves OD-8; Executor repairs only the findings above on top of the
   Reviewer commit and records a new complete candidate SHA.
3. Re-run the full suite, artifact install/dry-run, exact failure matrix,
   redacted secret fixtures, license/provenance audit, strict backup rehearsal,
   and seven observations.
4. Return `G5 / READY_FOR_REVIEW` only, with the original G5 base and the new
   candidate. Do not write acceptance or create a release tag.
5. If a repair regresses behavior, revert only the repair commit(s) to this
   Reviewer checkpoint; do not rewrite accepted G0–G4 history and do not modify
   existing user SQLite data during G5 evidence work.

## 7. Unique verdict

**CHANGES_REQUESTED**

`69ccad929eb9092083ad0a098c12dd9b56d37f8d` is not accepted as
`v0.1.0-rc1`. Do not tag, push, publish, schedule, or enter a post-G5 phase.
