# Gate G2 Independent Re-review 2 Verdict

## Reviewed object

- Reviewer: GPT-5.6 Sol in Codex
- Review date: 2026-08-19
- Gate: G2 — Recommendation Core and recoverable transaction model
- Original base SHA: `731e0498fecdb0a28c84cf57d55c89569895a5bf`
- Previous candidate SHA: `284fea8e08370ffe0a31cc1ad5f661eaa6bf314d`
- Previous Reviewer commit: `4953297a268a16696752ab3b3400734674dfbc19`
- New candidate SHA: `c0bf31d974a85499082a2e3e6eeb24e66fea1ed9`
- Candidate branch observed: `exec/g2-core`
- Executor report: `reviews/stage-02/EXECUTOR_REPORT.md`
- Repair report: `reviews/stage-02/REPAIR_REPORT.md`
- Test evidence: `reviews/stage-02/TEST_RESULTS.txt`

The candidate is a clean descendant of the exact accepted G1 base and contains the previous
Reviewer commit, four focused repair commits and one handoff commit. The merge-base is the
stated base, the worktree was clean at review start, `git diff --check` passed, and the repair
delta remains within G2 code, tests, schemas and governance artifacts.

The Reviewer independently ran the complete suite with cache disabled: **225 passed**. Ruff
also passed. Independent small-space brute-force checks found the new count/unranking solver's
solution totals correct in 100 randomized cases, and the previous lexical-ID bias, mutable
engine RNG, unbound-history commit, and unreachable parent path are materially repaired.

The Gate still cannot be accepted. The repair introduces an unvalidated mutable configuration
map that can break both execution and provenance; an ambiguous post-delivery receipt is placed
in terminal `FAILED` rather than recovery; and the new unbiased solver constructs and retains
combinatorial state before its claimed fast path can run.

## Previous findings — closure status

| Finding | Severity | Re-review status | Evidence |
|---|---:|---|---|
| G2-001 global pick indices | P0 | **CLOSED** | Exact ordered global records remain preserved through plan, commit and recovery. |
| G2-002 position cooldown / diversity solver | P1 | **PARTIAL** | Position correctness and unbiased feasibility are repaired; bounded resource behavior remains open under G2-013. |
| G2-003 Album identity safety | P0 | **CLOSED** | Exact, namespaced canonical, ambiguity and Unicode cases remain repaired. |
| G2-004 year fallback observability | P1 | **CLOSED** | Structured durable fallback evidence and cap behavior remain correct. |
| G2-005 crash/idempotency | P1 | **CLOSED** | Existing crash and repeated-run tests remain passing. |
| G2-006/G2-008 durable randomness provenance | P1 | **PARTIAL** | Per-run RNG derivation fixes process-lifetime divergence, but mutable effective config can disagree with its journaled fingerprint (G2-011). |
| G2-007 lexical-ID selection bias | P0 | **PARTIAL** | Count/unranking removes the 100,000-prefix bias; its unbounded state construction/cache is a new operational blocker (G2-013). |
| G2-009 receipt binding | P0 | **PARTIAL** | Wrong run/key/channel no longer commits history, but an `ok` receipt after an external call is classified as terminal failure rather than delivery ambiguity (G2-012). |
| G2-010 parent path unreachable | P1 | **PARTIAL** | Parents and limits now reach the Core through the normal path; the new limit configuration is neither value-validated nor immutable (G2-011). |

## Open blocking findings

### [P1] G2-011 — `genre_parent_limits` bypasses configuration validation and breaks immutable provenance

- Location: `data/schemas/config.schema.json:10-15`; `src/omda/config.py:43-64` and
  `:98-107`; `src/omda/orchestrator/run.py:256-268` and `:345-359`
- Evidence:
  - The schema declares an object with `additional_fields="allow"` and no value schema, so
    every dynamic value bypasses type and range validation.
  - Independent probes showed `load_config()` accepts values such as `"one"`, `-1`, `0`,
    `1.5`, `true`, and nested objects as parent limits.
  - With a Genre that carries the affected parent, the string value reaches the Core and
    raises an uncaught `TypeError` after only `PLANNED` has been journaled. The invalid config
    is not rejected at startup and the run does not reach an explicit domain failure.
  - `Config` is declared frozen but stores a mutable `dict`. After constructing a
    `RunEngine`, mutating `config.genre_parent_limits["p"]` changed the constraints used by
    selection while the PLANNED journal retained the old config fingerprint. In the probe,
    the recorded fingerprint was `57c2441f6a46`, while the actually used mutated config
    fingerprint was `a3b71fdc9a65`.
- Impact: malformed operator input can crash a run outside the error taxonomy, and a valid
  run can no longer be reproduced from its recorded effective configuration. This reopens
  the G2-008 provenance contract and leaves G2-010 unsafe at the application boundary.
- Violated contract: Handoff Spec §5-§6 and §8; Implementation Plan T1.2/T1.3 acceptance,
  I-3, R-010 and T2.6; the accepted G1 strict-validation/immutable-input boundary.
- Required correction:
  - validate every parent key/value as an explicit string-to-integer constraint map, with a
    documented safe range that cannot silently become a permanent eligibility filter;
  - reject malformed values before a run journals `PLANNED`, with a precise field path;
  - defensively snapshot/freeze the map so neither caller-owned input nor the exposed Config
    value can change effective behavior after validation or engine construction;
  - serialize that immutable value deterministically for the journaled config fingerprint;
  - follow the repository's schema-version policy for the changed config shape.
- Acceptance tests: invalid scalar/nested/bool/float/negative/zero values reject at their
  exact paths; mutation of original override objects cannot alter Config; direct mutation of
  the Config value is impossible; the journaled fingerprint always equals the exact config
  snapshot used for selection.

### [P1] G2-012 — An ambiguous successful delivery is incorrectly made terminal `FAILED`

- Location: `src/omda/orchestrator/run.py:474-504`; `tests/integration/test_run_engine.py`
  (`test_misbound_receipt_never_commits_history`)
- Evidence:
  - After `delivery.deliver(...)` returns an `ok` receipt with the wrong run ID, key, or
    channel, the system correctly refuses the history commit but immediately appends
    terminal `FAILED` and discards the receipt.
  - The external call may already have delivered the payload; a malformed/misbound success
    receipt cannot prove that no external side effect occurred.
  - `run()` and `recover()` return terminal failure forever for this run, so the explicit
    recovery/manual-review path required by the previous verdict and the state-machine
    contract is unavailable.
  - The added test encodes `FAILED` as the expected result and does not model an external
    side-effect count, so it proves history safety but not delivery-ambiguity safety.
- Impact: the system can send a recommendation, label it as an ordinary failed run, leave
  Albums out of official exclusion history, and allow later runs to recommend them again.
  The central delivery/history ambiguity is hidden rather than recoverable.
- Violated contract: Handoff Spec §4 explicit recovery state; Implementation Plan I-10,
  T2.6 and P0 risk R-001/R-009; previous G2-009 required correction.
- Required correction: distinguish a confirmed failed receipt from an `ok` but misbound or
  malformed receipt. The latter must persist sufficient anomaly evidence and enter
  `RECOVERING` (or the project's explicit manual-review equivalent), never commit official
  history, never blind re-deliver, and never be treated as an ordinary terminal failure.
- Acceptance tests: a delivery fake records one external effect then returns each kind of
  misbound `ok` receipt; the durable tail is recovery/manual-review, repeated `run(run_id)`
  causes no second delivery, history remains unchanged, and the anomaly is auditable. A
  confirmed `status="failed"` path may remain an explicit normal failure.

### [P1] G2-013 — The unbiased solver has combinatorial memory growth and retains it across runs

- Location: `src/omda/core/genre.py:151-228` and `:231-277`
- Evidence:
  - `_counts_cached()` stores every reachable state, including every terminal three-Genre
    set, then returns the entire mutable memo through an LRU cache of 128 input variants.
  - `build_unbiased_sampler()` always calls `_counts_cached()` before returning. The
    `rng.sample` “fast path” is inside the returned sampler, so it cannot avoid DP
    construction even for a completely unconstrained pool.
  - A new global start/history changes the cache key on every successful run, retaining a
    separate combinatorial memo until 128 variants accumulate.
- Independent bounded probes, using only 3 picks and no constraints:
  - 100 Genres: first sampler construction took about 0.9 seconds;
  - five otherwise identical 100-Genre constructions with distinct global starts grew the
    process maximum resident size to about **388 MB**, while cache entries rose 1→5;
  - 150 Genres took about 3.7 seconds for one construction;
  - 200 Genres took about 8.9 seconds for one construction;
  - the growth comes before a single sample is drawn and scales combinatorially with pool
    size; larger open-microgenre catalogs can exhaust memory rather than produce an explicit
    bounded outcome.
- Impact: replacing probability bias with an OOM-prone retained state space makes normal
  repeated use increasingly expensive and can prevent the local Agent from producing any
  result. This contradicts the module/report claim of a bounded solver.
- Violated contract: Handoff Spec §2.3 and §8 bounded/terminating behavior; Implementation
  Plan T2.3, D.3, R-003/R-011; G2-007 required an unbiased **bounded** method.
- Required correction: preserve exact unbiasedness without building/retaining all terminal
  combinations. At minimum, place genuine fast paths before DP construction, avoid memoizing
  terminal states, eliminate or tightly bound cross-run heavyweight caches, and use a compact
  counting strategy for active cooldown/family/parent constraints. Never reintroduce lexical
  truncation or probabilistic false insufficiency.
- Acceptance tests: exercise a documented realistic upper-bound Genre pool over multiple
  distinct run histories/global starts; demonstrate a stable explicit time/memory bound and
  bounded cache behavior, alongside the existing exact-count, equality, cooldown, parent,
  satisfiable and unsatisfiable tests.

## Acceptance matrix

| G2 criterion | Status | Evidence |
|---|---|---|
| T2.1 equal-opportunity Genre selection | **PASS** | Complete-space count/unranking is unbiased; 100 randomized brute-force totals matched. |
| T2.2 global cooldown and ordered picks | **PASS** | Exact global records and position-specific cooldown remain correct. |
| T2.3 family/parent diversity and bounded outcome | **FAIL** | Parent plumbing works, but config is unsafe and solver resources are not bounded. |
| T2.4 permanent Album exclusion and run dedup | **PASS** | Prior fixes and tests remain passing. |
| T2.5 year constraint and rating composition | **PASS** | Prior fixes and tests remain passing. |
| T2.6 recoverable run transaction | **PARTIAL** | Receipt binding prevents history corruption, but post-delivery ambiguity is terminalized. |
| Config/schema boundary | **FAIL** | Dynamic parent-limit values are unvalidated and mutable after fingerprinting. |
| Determinism and durable reproducibility | **PARTIAL** | Per-run RNG is fixed; mutable effective config can differ from recorded provenance. |
| Core purity / no concrete external dependencies | **PASS** | Architecture tests and source inspection pass. |
| No G3/G4 scope creep | **PASS** | No live adapter or network implementation was added. |
| Review package / Git evidence | **PASS** | Exact SHAs, clean tree, repair report and committed test output are present. |

## Checks performed and limitations

- Verified exact base/candidate/previous-Reviewer ancestry, branch, clean worktree and repair
  sequence.
- Reviewed `4953297..c0bf31d` and the necessary full G2 regression surface.
- Independently ran `pytest -q -p no:cacheprovider`: **225 passed**.
- Independently ran Ruff: **passed**.
- Ran `git diff --check`: **passed**.
- Compared DP solution totals to full enumeration in 100 randomized small constrained cases:
  all matched.
- Reproduced acceptance of six malformed parent-limit value shapes and an uncaught runtime
  type error when the affected parent is present.
- Reproduced mutation of effective constraints after engine fingerprinting.
- Inspected both fresh-delivery and recovery receipt-binding paths.
- Measured sampler construction at 100/150/200 Genres and cache growth across five distinct
  starts. These are diagnostic measurements, not a proposed flaky CI threshold.
- No production code, merge, tag, push, G3 work, live network or external service was used.

## Required repair scope

Remain on `exec/g2-core`. Repair only parent-limit configuration validation/immutability,
ambiguous-receipt state handling, unbiased solver resource bounds, focused regression tests
and stage-02 evidence. Do not change product defaults, introduce popularity weighting,
restore prefix truncation, weaken tests, merge, tag or enter G3. No ADR is currently required;
these are implementation corrections within already-approved contracts.

## Verdict

**CHANGES_REQUESTED**

Open blockers: G2-011 (P1), G2-012 (P1), G2-013 (P1). G2 must not be merged and G3 must not
begin. Acceptance can apply only to a future exact candidate SHA after independent re-review.
