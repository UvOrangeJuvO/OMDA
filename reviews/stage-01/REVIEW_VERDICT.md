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

---

## Re-review 1 — candidate `c45831ea3587e06f9c390786bfabca050314f03d`

### Re-review identity and checks

- Original G1 base: `5361b64d544c3134be9ba2b25a041ff146da613a`
- Original G1 candidate: `4830c53ba163631220a83d985cd1a385362ee17d`
- Original Reviewer commit: `4bce3d3d1a4ddaaba1bab5e783ee239cefdf870a`
- Repair candidate: `c45831ea3587e06f9c390786bfabca050314f03d`
- Repair commits: `79d2be5`, `6f6f0b5`, `c45831e`
- Worktree at review start: clean
- Independent test run: 68 passed, Ruff passed, diff check passed

The Reviewer inspected the complete repair delta, reran the suite, and independently probed batch conflicts, receipt immutability, nested schema-policy validation and nested journal-detail mutation.

### Original finding status

| Finding | Re-review status | Evidence |
|---|---|---|
| G1-001 (P0) atomic official-history commit | **CLOSED for SQLite batch atomicity** | `commit_history()` writes picks, Albums and `HISTORY_COMMITTED` in one SQLite transaction; injected database conflicts roll back all areas |
| G1-002 (P0) immutable receipt evidence | **CLOSED** | exact replay is a no-op; conflicting receipt raises and leaves original evidence intact in SQLite and fake |
| G1-003 (P1) strict unknown-field validation | **PARTIAL / OPEN** | ordinary unknown fields are rejected, but invalid nested `additional_fields` policy silently disables rejection |
| G1-004 (P2) immutable domain snapshots | **PARTIAL / OPEN** | top-level mapping is read-only, but nested mutable values remain externally mutable |

### [P1] G1-005 — Fake and SQLite history semantics diverge, and SQLite errors leak past the Port

- Location: `tests/fakes/__init__.py`, `InMemoryHistory.commit_history`; `src/omda/storage/sqlite_history.py`, `commit_history`; tests expecting raw `sqlite3.IntegrityError`
- Independent reproduction: calling the fake with two `GenrePickRecord` values sharing the same `pick_index` and two Album identities sharing the same `album_id` succeeds, writes a `HISTORY_COMMITTED` journal entry and reports counts of two. SQLite rejects the same duplicate keys and rolls back.
- Additional evidence: SQLite uniqueness conflicts escape as `sqlite3.IntegrityError`, even though the accepted Port contract requires adapters to translate provider-specific failures into the domain taxonomy. The current tests explicitly expect the SQLite exception, locking in the leak.
- Impact: G2 will primarily exercise the Orchestrator with `InMemoryHistory`; a duplicate-batch bug can pass all fake tests and fail in production. Orchestrator code would also need SQLite-specific exception handling, breaking the Port boundary.
- Violated contract: `OMDA_AGENT_HANDOFF_SPEC.md` §3.2, §4, §7.9–§7.11 and §8; G1 T1.4/T1.5 acceptance; repair requirement for fake/SQLite semantic parity.
- Required correction:
  - validate duplicate pick indices and duplicate Album identities **within the incoming batch**, as well as against stored state, before fake mutation;
  - make SQLite and fake raise the same domain exception class for invariant conflicts;
  - translate unexpected SQLite persistence failures to `StateCommitFailureError` while preserving the original exception as the cause;
  - do not expose `sqlite3.IntegrityError` through `HistoryPort` tests or callers;
  - add parameterized parity tests that execute identical success, exact-conflict and intra-batch-conflict scenarios against both implementations and compare result/exception/state.
- Acceptance test: for both fake and SQLite, duplicate pick/Album values within one batch fail with the same domain error and leave pick history, exclusions and journal unchanged.

### [P1] G1-003 remains open — Invalid nested unknown-field policy silently becomes permissive

- Location: `src/omda/schemas/validator.py`, `_validate_value()` object branch and `_validate_fields()`
- Independent reproduction: a nested object schema with `"additional_fields": "typo"` accepts an undeclared nested key and returns success. Only the top-level policy is checked against `reject|allow`; nested policies are passed through without validation, and every value other than the exact string `reject` behaves like `allow`.
- Impact: a schema-author typo can silently disable strict validation for an entire nested object, recreating the original G1-003 failure mode.
- Required correction: centralize policy validation and apply it at every object scope before validating unknown fields. Invalid nested policies must raise `SchemaError` with the full schema path. Add nested-invalid-policy tests in addition to the existing top-level test.
- Acceptance test: nested `additional_fields` values other than `reject` or `allow` always raise `SchemaError`; undeclared nested fields never pass because of an invalid policy.

### [P2] G1-004 remains open — Journal detail is only shallowly immutable

- Location: `src/omda/ports/domain.py`, `JournalEntry.__post_init__`
- Independent reproduction: with `detail={"x": {"y": 1}}`, constructing a `JournalEntry` and then mutating the caller's nested dictionary changes the supposedly immutable entry to `{"x": {"y": 2}}`.
- Impact: nested facts in a durable journal snapshot can change after construction. This is a lower-severity contract-quality issue but contradicts the repair report's closure claim.
- Required correction: recursively snapshot/freeze supported JSON-like values, or deep-copy on input and return defensive/read-only snapshots. Define behavior for nested dict/list values and test both caller-side mutation and attempted mutation through the exposed value.
- Blocking status: P2; fix alongside the blocking repair and close before G2 uses journal details for recovery.

### Re-review verdict

**CHANGES_REQUESTED**

G1-001 and G1-002 are materially repaired. G1-003 remains partially open, G1-004 remains partially open, and G1-005 is a new P1 Port-parity/error-boundary finding. G1 must not be merged and G2 must not begin. The next repair is narrow: domain error translation, fake/SQLite parity, recursive journal snapshots and nested schema-policy validation.
