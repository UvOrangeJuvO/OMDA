# Gate G2 Independent Re-review 4 Verdict

## Reviewed object

- Reviewer: GPT-5.6 Sol in Codex
- Review date: 2026-08-20
- Gate: G2 — Recommendation Core and recoverable transaction model
- Original base SHA: `731e0498fecdb0a28c84cf57d55c89569895a5bf`
- Previous candidate SHA: `061e1d11fe703a4ee3036dc5d4bad5d847a2ef99`
- Previous Reviewer commit: `1c0265a8aaa35c4a7b4204016ea8760e56304c79`
- New candidate SHA: `bf62ca658a1cbb10d5bbc8b2bae4f2b4a7c87305`
- Candidate branch observed: `exec/g2-core`
- Executor report: `reviews/stage-02/EXECUTOR_REPORT.md`
- Repair report: `reviews/stage-02/REPAIR_REPORT.md`
- Test evidence: `reviews/stage-02/TEST_RESULTS.txt`

The candidate is a clean descendant of the exact accepted G1 base and contains the prior
Reviewer commit, three focused repair commits, and the handoff commit. The merge-base and
branch are correct, the worktree was clean at review start, `git diff --check` passed, and
no G3/G4 implementation was introduced.

The Reviewer independently ran the complete suite with cache disabled: **248 passed**. Ruff
also passed. The repair closes the direct-map mutability hole, correctly checks receipt
binding before the `failed` status, stops identical recovery calls from appending duplicate
rows, and makes the genuine first-run/no-constraint RunEngine shape use the fast path.

G2 is still not acceptable because the prior acceptance requirements were only partially
implemented. Direct `Config(...)` values are frozen but not validated; a receipt with an
unknown status is terminalized as a confirmed failure; and the Genre normalization both
misses semantically stale cooldown history and can discard a real explicit parent mapping.
These are independently reproducible outside the newly added happy-path tests.

## Finding status summary

| Finding | Severity | Re-review status | Evidence |
|---|---:|---|---|
| G2-001 global ordered picks | P0 | **CLOSED** | Exact global records remain correct through commit and recovery. |
| G2-002 cooldown/diversity semantics | P1 | **PARTIAL** | Normal cooldown boundaries pass, but stale no-op history still forces the combinatorial path under G2-013. |
| G2-003 Album identity | P0 | **CLOSED** | Exact/canonical/ambiguity/Unicode protections remain passing. |
| G2-004 year fallback | P1 | **CLOSED** | Durable structured fallback evidence remains passing. |
| G2-005 crash/idempotency | P1 | **CLOSED** | Repeated unchanged recovery is now journal-idempotent and does not re-deliver. |
| G2-006/G2-008 randomness provenance | P1 | **PARTIAL** | Per-run RNG remains correct; invalid direct Config can still create a journaled run whose effective configuration was never validated. |
| G2-007 equal-opportunity solver | P0 | **PARTIAL** | Complete-space sampling remains unbiased on valid inputs, but explicit parent constraints can be dropped by the new normalization. |
| G2-009 receipt binding | P0 | **CLOSED** | Run/key/channel binding is now checked before status classification. |
| G2-010 parent plumbing | P1 | **PARTIAL / REOPENED** | RunEngine's normal `GenreRef.parents` path works, but the public `parents_by_genre` input can be ignored. |
| G2-011 parent config validation/immutability | P1 | **PARTIAL / OPEN** | Every map is now frozen, but direct invalid values still bypass validation. |
| G2-012 delivery ambiguity recovery | P1 | **PARTIAL / OPEN** | Binding order and repeated recovery are repaired; malformed status values still become terminal FAILED. |
| G2-013 solver resource bounds | P1 | **PARTIAL / OPEN** | First-run empty histories are fast; stale inactive histories and non-binding limits still trigger DP, and parent normalization has a correctness regression. |

## Open blocking findings

### [P1] G2-011 — Direct `Config(...)` is immutable but still bypasses value validation

- Location: `src/omda/config.py:43-69`; `src/omda/orchestrator/run.py:241-268` and
  `:325-360`; `tests/unit/test_config.py:145-186`
- Repaired:
  - `Config.__post_init__` makes a defensive copy and freezes it on every construction path;
  - mutating a caller-owned map or the exposed map no longer changes effective rules or the
    fingerprint.
- Remaining evidence:
  - `Config(genre_parent_limits={"p": "one"})` still constructs successfully;
  - `RunEngine` accepts that public Config directly and does not pass it through schema
    validation before appending `PLANNED`;
  - an independent run with eligible Genres under parent `p` raised an unhandled
    `TypeError` (`'>=' not supported between instances of 'int' and 'str'`) and left the
    journal at `['PLANNED']`;
  - the new direct-construction tests cover only immutability and a valid value; they do not
    cover direct zero/negative/non-integer values or pre-`PLANNED` rejection.
- Impact: the engine can durably claim a planned run and then escape its bounded domain-error
  state machine because its effective configuration was never validated.
- Required correction: either validate every Config field in `Config.__post_init__`, or make
  RunEngine validate the exact immutable snapshot before it writes `PLANNED`. Direct invalid
  parent limits must be rejected with a controlled validation error and no run journal.
- Acceptance tests: direct `Config(...)` with string, bool, float, zero, negative and
  out-of-range parent values; direct RunEngine construction; assert controlled rejection
  occurs before `PLANNED`, with no uncaught built-in exception.

### [P1] G2-012 — Unknown/malformed receipt status is still treated as confirmed failure

- Location: `src/omda/orchestrator/run.py:474-519` and `:555-588`;
  `tests/integration/test_run_engine.py:327-408` and `:789-868`
- Repaired:
  - binding is validated before status;
  - an exactly bound `failed` receipt becomes terminal FAILED;
  - a misbound `failed` receipt and receipt-save conflict enter RECOVERING;
  - five unchanged recovery calls retain exactly one RECOVERING journal row and never
    re-deliver.
- Remaining evidence:
  - after binding passes, the implementation uses `receipt.status != "ok"` as the entire
    failure test;
  - therefore an exactly bound status such as `"unknown"`, `"pending"`, an empty string, or
    another malformed adapter value becomes terminal FAILED even though it is not the
    schema-valid, explicit `"failed"` evidence required by the previous verdict;
  - an independent exactly bound `status="unknown"` probe ended in `FAILED` and wrote a
    terminal FAILED tail;
  - the new tests cover `ok` and `failed`, but no malformed status.
- Impact: ambiguous delivery evidence can again be hidden as an ordinary terminal failure,
  allowing an operator to assume no delivery occurred when the adapter never actually
  confirmed that fact.
- Required correction: interpret only exactly `status == "failed"` as a confirmed failure;
  exactly `"ok"` may proceed; all other/malformed states must preserve evidence and enter
  RECOVERING/manual review without history mutation or re-delivery.
- Acceptance tests: exactly bound `ok`, exactly bound `failed`, and at least unknown/empty
  statuses; assert one delivery call, exact terminal/recovery state, zero history for all
  non-success cases, durable anomaly evidence, and bounded repeated recovery.

### [P1] G2-013/G2-010 — Constraint normalization is incomplete and can discard a real parent constraint

- Location: `src/omda/core/genre.py:262-315`; `tests/property/test_genre_equality.py:197-269`;
  `tests/unit/test_core_genre.py:164-196`
- Repaired:
  - `{genre_id: ()}` cooldown maps now normalize to no cooldown;
  - limits for families/parents completely absent from the pool are removed;
  - a real 200-Genre first RunEngine run with no active constraints reaches `rng.sample`
    without constructing DP.
- Remaining correctness evidence:
  - `pool_parents` is derived from `GenreRef.parents`, but the solver's documented public
    input and the DP itself use `parents_by_genre`;
  - when GenreRefs have no embedded parents but `parents_by_genre` explicitly maps two Genres
    to `electronic`, the normalization drops `parent_limits={"electronic": 1}` and enters the
    unconstrained fast path;
  - an independent four-Genre probe selected both constrained Genres immediately with seed
    `0`, violating the parent limit;
  - existing tests exercise the separate enumeration function with this explicit-map shape,
    but do not exercise `select_daily_genres`/`build_unbiased_sampler` with it.
- Remaining resource evidence:
  - cooldown entries are retained whenever their tuple is nonempty, even if every historical
    pick is older than the full next-pick window and therefore cannot constrain this run;
  - with 200 Genres, history `{genre_id: (1,)}` and `global_start_index=1000` is semantically
    unconstrained, but still built a DP cache entry and took about **4.01 seconds** before
    sampling; 100 Genres took about **0.31 seconds**;
  - a family/parent limit is retained merely when one matching member exists, even if the
    number of matching eligible Genres is less than or equal to the limit and the constraint
    cannot possibly bind;
  - the new “active upper bound” test uses only 61 Genres, one Regional Genre and a limit of
    one. That limit cannot be violated, and the test asserts neither a supported catalog
    bound nor a time/memory ceiling.
- Impact: the optimization still misses normal later-run shapes, while the new parent
  normalization can violate the diversity contract on a supported Core input.
- Required correction:
  - derive effective parent memberships from the authoritative `parents_by_genre` mapping
    (or remove the duplicate input through an explicit API change with regression coverage);
  - discard cooldown histories only when they cannot block any of the next `count` global
    positions, not merely when the tuple is empty;
  - discard family/parent limits that cannot bind for this pool/count;
  - preserve exact complete-space unbiasedness and explicit insufficiency;
  - document and test a realistic supported bound for the genuinely constrained path, or
    provide a compact method that demonstrably meets it.
- Acceptance tests: public selector with explicit `parents_by_genre`; stale nonempty
  RunEngine-shaped history at multiple global starts; limits with zero/one/enough matching
  members; real active constraints at the documented maximum; assert constraint correctness,
  zero DP for every semantically unconstrained case, bounded cache/time behavior, and no
  lexical/probability bias.

## Acceptance matrix

| G2 criterion | Status | Evidence |
|---|---|---|
| T2.1 equal opportunity | **PARTIAL** | Unbiased valid-input sampling passes; parent normalization can change the valid solution space. |
| T2.2 global cooldown/order | **PASS** | 30/31 semantics and global indices remain correct. |
| T2.3 family/parent diversity and bounded result | **FAIL** | Explicit parent-map bypass and stale-history resource path remain. |
| T2.4 Album identity/exclusion | **PASS** | Prior fixes remain passing. |
| T2.5 year/rating rules | **PASS** | Prior fixes remain passing. |
| T2.6 recoverable transaction | **PARTIAL** | Binding and journal idempotency pass; malformed receipt status is terminalized incorrectly. |
| Config/schema boundary | **PARTIAL** | Maps are frozen; direct invalid Config values still bypass validation. |
| Determinism/provenance | **PARTIAL** | Valid runs reproduce; invalid direct Config can write PLANNED before uncontrolled failure. |
| Core purity | **PASS** | Architecture tests pass. |
| No G3/G4 scope creep | **PASS** | Candidate remains within G2/foundation support and review files. |
| Review package / Git evidence | **PASS** | Exact SHAs, repair report and test output are committed. |

## Checks performed and limitations

- Verified exact base/candidate/previous-Reviewer ancestry, branch, repair chain, clean
  worktree and stage-02 review package.
- Independently ran `pytest -q -p no:cacheprovider`: **248 passed**.
- Independently ran Ruff: **passed**.
- Ran `git diff --check`: **passed**.
- Confirmed direct Config defensive-copy and mapping immutability behavior.
- Reproduced an unhandled direct-config TypeError after `PLANNED`.
- Confirmed bound-failed versus misbound-failed receipt behavior and bounded duplicate
  recovery journaling.
- Reproduced terminal FAILED for an exactly bound unknown receipt status.
- Confirmed the real first-run 200-Genre fast path from the committed test.
- Reproduced explicit parent-map constraint bypass and stale-history 100/200-Genre DP costs.
- No production code, merge, tag, push, G3 work, live network or external service was used.

## Required repair scope

Remain on `exec/g2-core`. Repair only direct Config validation at the engine boundary,
three-way receipt status classification, parent/cooldown/limit semantic normalization,
focused regression tests and stage-02 evidence. Do not alter product defaults, reintroduce
selection bias, weaken tests, merge, tag or enter G3. No ADR is currently needed.

## Verdict

**CHANGES_REQUESTED**

Open blockers: G2-011 (P1), G2-012 (P1), and G2-013/G2-010 (P1), all PARTIAL. G2 must not
be merged and G3 must not begin. Acceptance applies only to a future exact candidate after
independent re-review.
