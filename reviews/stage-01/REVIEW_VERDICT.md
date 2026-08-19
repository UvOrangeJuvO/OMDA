# Gate G1 Independent Review Verdict

## Reviewed object

- Reviewer: GPT-5.6 Sol in Codex
- Review date: 2026-08-19
- Gate: G1 — Foundation
- Base SHA: `5361b64d544c3134be9ba2b25a041ff146da613a`
- Candidate SHA: `4830c53ba163631220a83d985cd1a385362ee17d`
- Candidate branch observed: `exec/g1-foundation`
- Executor report: `reviews/stage-01/EXECUTOR_REPORT.md`
- Test evidence: `reviews/stage-01/TEST_RESULTS.txt`

The candidate has a clean worktree, is a descendant of the accepted G0 merge, contains T1.1–T1.6 as separate commits plus a handoff commit, and does not enter G2. `git diff --check` passed. The Reviewer independently reran the suite and lint with the WorkBuddy Python environment: 56 tests passed and Ruff passed.

## Execution-shape observation

The WorkBuddy UI required approximately three manual continuations, but Git records eight coherent checkpoints: G1 start, six atomic-task commits and one handoff commit. This is a healthy resumable execution pattern, not a monolithic or state-losing run. Future prompts should require a pause marker and continuation data, but this behavior is not a Gate defect.

## Findings

### [P0] G1-001 — Official 3×3 history cannot be committed atomically

- Location: `src/omda/ports/history.py:44–56`; `src/omda/storage/sqlite_history.py:156–190`
- Evidence: `HistoryPort` exposes only per-row `record_genre_pick()` and `record_album()` operations. Each SQLite implementation opens and commits its own transaction. There is no Port operation that commits all three Genre picks, all nine Album identities and the `HISTORY_COMMITTED` journal transition in one local transaction.
- Reproduction/analysis: if an Orchestrator writes three Genre rows and then encounters a duplicate/constraint/storage error while writing Album 5, the earlier Genre and Album rows are already committed. The existing transaction test proves only that one failed SQL statement rolls itself back; it does not test a recommendation-run commit.
- Impact: a failed run can consume cooldown indices and permanently exclude only a subset of Albums. This is direct official-history corruption and violates the project's central transaction invariant.
- Violated contract: `OMDA_AGENT_HANDOFF_SPEC.md` §4 and §7.9–§7.11; Master Plan §3.7/§6; G1 T1.5 acceptance; Executor report §8 claim of transaction safety.
- Required correction:
  - add a single Port-level batch/unit-of-work operation for the complete official history commit;
  - its SQLite implementation must insert all Genre picks, all Album histories and the `HISTORY_COMMITTED` journal entry within one `with connection` transaction;
  - a failure anywhere must leave all three official-history/journal areas unchanged;
  - the in-memory fake must implement the same all-or-nothing behavior;
  - individual write methods must not remain the normal Orchestrator commit path (make them private/internal or document and test that only the atomic operation is used).
- Acceptance test: inject a failure after some Genre/Album inserts inside the batch and prove the latest pick index, all Album exclusions and the journal are exactly unchanged.

### [P0] G1-002 — A later write can overwrite immutable successful delivery evidence

- Location: `src/omda/storage/sqlite_history.py:210–224`; analogous fake behavior in `tests/fakes/__init__.py`
- Evidence: `save_delivery_receipt()` uses `INSERT OR REPLACE`. SQLite `REPLACE` deletes/replaces the existing row for the same idempotency key. The in-memory fake similarly assigns directly into a dictionary.
- Independent reproduction: after saving an `ok` receipt for key `k`, saving a different `failed` receipt with the same key changes `find_delivery_receipt("k")` to the later failed record.
- Impact: the durable proof that an external push already succeeded can be destroyed. Recovery may then conclude that delivery did not succeed and push the same recommendation again. This contradicts the append-only claim in source and report.
- Violated contract: `OMDA_AGENT_HANDOFF_SPEC.md` §4; Master Plan §6; G1 data-protection requirement; risk R-001/R-009.
- Required correction:
  - receipt evidence must be immutable by idempotency key;
  - an exact replay may be an idempotent no-op/return of the original record;
  - a conflicting record for an existing key must fail closed with a typed state/invariant error and must not alter the original;
  - failed delivery attempts should be journal events unless the design specifies a separate append-only attempt record; they must never overwrite an `ok` receipt;
  - SQLite and `InMemoryHistory` semantics must match.
- Acceptance test: save an `ok` receipt, attempt both an exact replay and a conflicting failed/different-run write, then prove the original success evidence remains byte-for-byte/domain-value identical and only one external delivery is represented.

### [P1] G1-003 — Schema validation silently accepts misspelled fields

- Location: `src/omda/schemas/validator.py:131–168`; `tests/unit/test_schemas.py` forward-compatibility expectation
- Evidence: `_validate_fields()` checks only declared fields and never reports unknown keys. `validate_record()` explicitly accepts all unknown extra fields. Independent checks showed that config `{ "genre_cooldown_pick": 999 }` and an Album with misspelled `canoncial_id` both pass validation.
- Impact: a user may believe a safety-critical configuration took effect when it was ignored; a community contribution may silently lose optional canonical identity/provenance because of a typo. This conflicts with precise machine validation and makes malformed contributions difficult to review.
- Violated contract: `OMDA_AGENT_HANDOFF_SPEC.md` §3.3, §5 and §7.1; Master Plan §3.5; G1 T1.2/T1.3 acceptance.
- Required correction:
  - schemas must explicitly declare unknown-field policy;
  - config and canonical community/runtime records should be strict by default and reject unknown keys with field/location evidence;
  - if future extensions are needed, provide an explicitly named/versioned extension field or an opt-in schema policy rather than accepting every typo;
  - nested objects must enforce the same policy;
  - replace the current “unknown fields always pass” test with strict and explicitly extensible cases.
- Acceptance test: misspelled top-level and nested config/Album/Genre fields are rejected with the exact location, while a deliberately declared extension mechanism passes.

### [P2] G1-004 — Immutability claims are stronger than the actual domain types

- Location: `src/omda/ports/domain.py:40–63`; `src/omda/ports/history.py:59–60`
- Evidence: frozen dataclasses contain mutable `dict` detail values, and `excluded_album_identities()` returns a mutable `set` while its docstring calls the result immutable.
- Impact: callers can mutate journal detail or the exclusion collection after retrieval, weakening deterministic snapshots. It is not the current cause of state corruption because SQLite returns new objects.
- Required correction: use immutable/read-only mappings or defensive copies for journal detail and return `frozenset[AlbumIdentity]` (or explicitly document copy semantics). Keep fake and SQLite signatures aligned.
- Blocking status: P2; may be fixed with the blocking repair and should not be deferred beyond G2 Core inputs.

## Acceptance matrix

| G1 criterion | Status | Evidence |
|---|---|---|
| T1.1 repository/tooling and clean install | PASS | package installs; smoke test and lint pass |
| T1.2 versioned schemas and precise malformed-record rejection | FAIL | G1-003: unknown/misspelled fields pass silently |
| T1.3 layered configuration and invalid-value rejection | PARTIAL | precedence/ranges pass; misspelled config keys are silently ignored |
| T1.4 minimal Ports and domain errors | PARTIAL | shape exists; official commit unit-of-work is missing |
| T1.5 auditable, transactional, protected SQLite runtime state | FAIL | G1-001 and G1-002 |
| T1.6 deterministic fixtures/test foundation | PASS WITH GAP | tooling works; critical transaction/idempotency semantics were not tested |
| G0-007 follow-up | PASS | stale reference fixed; journal ownership decision recorded |
| No G2/external-adapter scope creep | PASS | no selection or live adapter implementation found |

## Checks performed

- Verified exact SHAs, merge-base, branch, clean worktree, commit sequence and full diff.
- Read all changed implementation, schema, test and governance files relevant to G1.
- Independently ran 56 tests with cache disabled: all passed.
- Independently ran Ruff: passed.
- Reproduced mutable receipt overwrite for a repeated idempotency key.
- Demonstrated that unknown/misspelled config and Album fields pass validation.
- Examined Port/SQLite transaction boundaries and compared them with the required full-run commit semantics.
- No live network or external service was used.

## Required repair scope

The Executor should remain on `exec/g1-foundation`, read this verdict, and create focused repair commits. Allowed scope:

- History/domain Port contracts and fakes;
- SQLite history adapter and migration only as necessary;
- schema policy/validator and affected schemas;
- focused unit/contract/failure-injection tests;
- G1 repair report, test evidence, risk/state updates;
- no Recommendation Core, RYM, MusicBrainz, LLM provider or PushPlus implementation.

The repair must rerun the full suite and add explicit tests for batch rollback, immutable receipt conflicts, fake/SQLite semantic parity and unknown-field rejection.

## Verdict

**CHANGES_REQUESTED**

Open blocking findings: G1-001 (P0), G1-002 (P0), G1-003 (P1). G1 must not be merged and G2 must not begin.
