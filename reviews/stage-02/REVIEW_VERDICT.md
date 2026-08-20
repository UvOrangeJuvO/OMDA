# Gate G2 Independent Re-review 5 Verdict

## Reviewed object

- Reviewer: GPT-5.6 Sol in Codex
- Review date: 2026-08-20
- Gate: G2 — Recommendation Core and recoverable transaction model
- Original base SHA: `731e0498fecdb0a28c84cf57d55c89569895a5bf`
- Previous candidate SHA: `bf62ca658a1cbb10d5bbc8b2bae4f2b4a7c87305`
- Previous Reviewer commit: `3fd88ad71491353ac6228a01dc45f43b439587e1`
- New candidate SHA: `0594b2774a3a5f07f15086dc1474af9d8ef5bce6`
- Candidate branch observed: `exec/g2-core`
- Executor report: `reviews/stage-02/EXECUTOR_REPORT.md`
- Repair report: `reviews/stage-02/REPAIR_REPORT.md`
- Test evidence: `reviews/stage-02/TEST_RESULTS.txt`

The candidate is a clean descendant of the exact accepted G1 base and contains the previous
Reviewer commit, three focused repair commits, and the handoff commit. The merge-base and
branch are correct, the worktree was clean at review start, `git diff --check` passed, and
no G3/G4 implementation was introduced.

The Reviewer independently ran the complete suite with cache disabled: **261 passed**. Ruff
also passed. Receipt status is now classified correctly into success, confirmed failure and
ambiguous recovery. Explicit `parents_by_genre` constraints are preserved, stale cooldown
history reaches the fast path, and limits that mathematically cannot bind are removed.

Two prior acceptance requirements remain incomplete. The candidate validates only direct
`genre_parent_limits`, although the prior verdict and repair prompt required every direct
`Config(...)` value to cross the same validation boundary before `PLANNED`. In addition, the
solver still has no documented or demonstrated bound for a genuinely active constraint;
the test named “active upper bound” now uses a constraint that normalization correctly drops.

## Finding status summary

| Finding | Severity | Re-review status | Evidence |
|---|---:|---|---|
| G2-001 global ordered picks | P0 | **CLOSED** | Exact global records remain correct through commit and recovery. |
| G2-002 cooldown/diversity semantics | P1 | **PASS / resource bound tracked in G2-013** | Cooldown correctness and stale-history normalization pass. |
| G2-003 Album identity | P0 | **CLOSED** | Exact/canonical/ambiguity/Unicode protections remain passing. |
| G2-004 year fallback | P1 | **CLOSED** | Durable structured fallback evidence remains passing. |
| G2-005 crash/idempotency | P1 | **CLOSED** | Recovery remains journal-idempotent and never blindly re-delivers. |
| G2-006/G2-008 randomness provenance | P1 | **PARTIAL** | Valid configurations reproduce; other invalid direct Config fields still bypass validation. |
| G2-007 equal-opportunity solver | P0 | **CLOSED** | Complete-space sampling and explicit parent-map correctness now pass. |
| G2-009 receipt binding | P0 | **CLOSED** | Exact binding remains enforced before status interpretation. |
| G2-010 parent plumbing | P1 | **CLOSED** | Embedded and explicit parent memberships now reach the solver without dropping the limit. |
| G2-011 configuration validation/immutability | P1 | **PARTIAL / OPEN** | Parent maps are frozen and parent values validated; the rest of direct Config still bypasses Schema. |
| G2-012 delivery ambiguity recovery | P1 | **CLOSED** | Only exact `failed` terminalizes; malformed states recover with durable evidence. |
| G2-013 solver resource bounds | P1 | **PARTIAL / OPEN** | Semantically inactive inputs are fast; no genuine active-constraint maximum/bound is documented or tested. |

## Open blocking findings

### [P1] G2-011 — Direct Config validation covers only `genre_parent_limits`

- Location: `src/omda/config.py:39-86`; `src/omda/orchestrator/run.py:241-268` and
  `:325-360`; `tests/unit/test_config.py:189-218`
- Repaired:
  - direct parent keys and values are validated before a Config can exist;
  - string/bool/float/zero/negative/out-of-range parent limits are rejected;
  - defensive immutability and fingerprint stability remain correct.
- Remaining evidence:
  - direct `Config(daily_genre_count="three")`, `Config(albums_per_genre=0)`,
    `Config(genre_cooldown_picks=False)`, `Config(modern_album_year="new")`,
    `Config(seed="")`, and `Config(delivery=DeliveryConfig(channel="bogus"))` all still
    construct successfully despite violating the committed config schema;
  - an independent run using `daily_genre_count="three"` raised an unhandled `TypeError`
    after the journal already contained `['PLANNED']`;
  - RunEngine still fingerprints and accepts the direct object without validating
    `config_to_dict(config)` before it writes any run state;
  - the new tests cover only `genre_parent_limits`, despite the previous verdict requiring
    either validation of every Config field or validation of the exact snapshot at the
    RunEngine boundary.
- Impact: supported direct construction can still escape the bounded state machine and
  create a durable half-run from an effective configuration that never passed Schema.
- Required correction: establish one complete validation boundary for the exact immutable
  Config snapshot used by RunEngine. Either all Config/DeliveryConfig construction paths
  enforce the committed schema, or RunEngine validates the complete `config_to_dict`
  snapshot before fingerprinting and before `PLANNED`. Do not maintain a second partial copy
  of schema rules that can drift.
- Acceptance tests: direct invalid values for every schema field/type/range/enum/pattern,
  including bool-as-int cases and invalid DeliveryConfig; valid direct Config round-trip;
  assert controlled rejection before any journal entry and no uncaught built-in exception.

### [P1] G2-013 — Genuine active-constraint resource behavior is still unbounded and untested

- Location: `src/omda/core/genre.py:151-230` and `:262-358`;
  `tests/property/test_genre_equality.py:259-272` and `:313-355`
- Repaired:
  - empty and stale cooldown maps no longer construct DP;
  - absent and mathematically non-binding family/parent limits are dropped;
  - the explicit parent-map correctness regression is closed.
- Remaining evidence:
  - `test_active_constraint_upper_bound_stays_bounded` builds 60 ordinary Genres plus only
    one Regional Genre with limit one. Under the new correct normalization this limit cannot
    bind and is dropped, so the test now exercises the fast path, not an active constraint;
  - no source file, governance document or test defines a supported maximum eligible Genre
    pool for genuinely active family/parent/cooldown constraints;
  - no test asserts a time, state-count or memory ceiling across multiple genuinely active
    histories at such a maximum;
  - an independent pool with 200 ordinary Genres plus two Regional Genres (default Regional
    limit one, therefore genuinely active) took about **3.41 seconds** merely to construct
    the sampler and created a DP cache entry; 100 ordinary plus two Regional took about
    **0.29 seconds**. This steep growth is the exact constrained-path risk retained from the
    earlier verdict.
- Impact: a realistic taxonomy containing at least two members of a default-limited family
  can still incur sharply increasing pre-sampling delay, while the project has no enforceable
  operational boundary or explicit bounded failure policy.
- Required correction: satisfy the already stated alternative from the previous verdict:
  either implement a compact exact counting method that meets a documented realistic bound,
  or document/enforce a supported constrained-pool bound with an explicit, unbiased and
  bounded outcome beyond it. A silent prefix cap, lexical truncation, rejection loop or
  popularity-based prefilter remains forbidden.
- Acceptance tests: use at least two members of a limited family/parent so the constraint is
  provably active; test the documented maximum over multiple global starts and active
  histories; assert exact constraint correctness, equal opportunity, deterministic replay,
  bounded memo/cache size and a stable performance budget. Also assert that the test really
  entered the constrained path.

## Acceptance matrix

| G2 criterion | Status | Evidence |
|---|---|---|
| T2.1 equal opportunity | **PASS** | Exact complete-space sampling and parent-map regression tests pass. |
| T2.2 global cooldown/order | **PASS** | 30/31 semantics, global indices and stale-history normalization pass. |
| T2.3 family/parent diversity and bounded result | **PARTIAL** | Constraint correctness passes; genuine active-path resource bound does not. |
| T2.4 Album identity/exclusion | **PASS** | Prior fixes remain passing. |
| T2.5 year/rating rules | **PASS** | Prior fixes remain passing. |
| T2.6 recoverable transaction | **PASS** | Binding, three-way status classification, recovery and history isolation pass. |
| Config/schema boundary | **PARTIAL** | Parent direct values pass; other direct Config fields bypass Schema. |
| Determinism/provenance | **PARTIAL** | Valid runs reproduce; invalid direct Config can journal before uncontrolled failure. |
| Core purity | **PASS** | Architecture tests pass. |
| No G3/G4 scope creep | **PASS** | Candidate remains within G2/foundation support and review files. |
| Review package / Git evidence | **PASS** | Exact SHAs, repair report and test output are committed. |

## Checks performed and limitations

- Verified exact base/candidate/previous-Reviewer ancestry, branch, repair chain, clean
  worktree and stage-02 review package.
- Independently ran `pytest -q -p no:cacheprovider`: **261 passed**.
- Independently ran Ruff: **passed**.
- Ran `git diff --check`: **passed**.
- Confirmed all six direct parent-limit invalid cases reject before Config construction.
- Reproduced successful construction of invalid direct non-parent Config fields and an
  unhandled direct daily-count TypeError after `PLANNED`.
- Confirmed bound `ok`/`failed`/malformed receipt behavior and zero official history on all
  non-success paths.
- Confirmed explicit parent mapping, stale cooldown and non-binding-limit regressions close.
- Measured genuinely active default-family constraint construction at 102 and 202 Genres.
- No production code, merge, tag, push, G3 work, live network or external service was used.

## Required repair scope

Remain on `exec/g2-core`. Repair only the complete direct-Config validation boundary and the
genuinely active solver resource bound, plus focused regression tests and stage-02 evidence.
Do not alter product defaults, reintroduce selection bias, weaken tests, merge, tag or enter
G3. If the proposed solver bound changes product semantics rather than only making failure
explicit and safe, stop and propose an ADR before implementation.

## Verdict

**CHANGES_REQUESTED**

Open blockers: G2-011 (P1) and G2-013 (P1), both PARTIAL. G2 must not be merged and G3 must
not begin. Acceptance applies only to a future exact candidate after independent re-review.
