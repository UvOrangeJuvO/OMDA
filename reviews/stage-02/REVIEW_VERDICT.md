# Gate G2 Independent Re-review 3 Verdict

## Reviewed object

- Reviewer: GPT-5.6 Sol in Codex
- Review date: 2026-08-20
- Gate: G2 — Recommendation Core and recoverable transaction model
- Original base SHA: `731e0498fecdb0a28c84cf57d55c89569895a5bf`
- Previous candidate SHA: `c0bf31d974a85499082a2e3e6eeb24e66fea1ed9`
- Previous Reviewer commit: `266ccdc1c69b5b90d76366af125b3009f688c19d`
- New candidate SHA: `061e1d11fe703a4ee3036dc5d4bad5d847a2ef99`
- Candidate branch observed: `exec/g2-core`
- Executor report: `reviews/stage-02/EXECUTOR_REPORT.md`
- Repair report: `reviews/stage-02/REPAIR_REPORT.md`
- Test evidence: `reviews/stage-02/TEST_RESULTS.txt`

The candidate is a clean descendant of the exact G1 base and contains the previous Reviewer
commit, three focused repair commits, and one handoff commit. The merge-base and branch are
correct, the worktree was clean at review start, `git diff --check` passed, and no G3/G4
implementation was introduced.

The Reviewer independently ran the complete suite with cache disabled: **239 passed**. Ruff
also passed. The new schema value-spec support correctly rejects the six reported malformed
loaded-config values, loaded parent maps are frozen, `ok` misbound receipts no longer become
terminal failures, and terminal DP states are no longer retained.

The three open findings are only partially closed because their new tests use narrower call
shapes than the application actually permits or produces. Direct `Config(...)` construction
still creates mutable maps; receipt binding is checked after status and identical recovery
calls append without a bound; and RunEngine-shaped empty cooldown histories bypass the new
solver fast path.

## Finding status summary

| Finding | Severity | Re-review status | Evidence |
|---|---:|---|---|
| G2-001 global ordered picks | P0 | **CLOSED** | Exact global records remain correct through commit and recovery. |
| G2-002 cooldown/diversity semantics | P1 | **PARTIAL** | Semantic correctness remains; application-scale bounded behavior is still open under G2-013. |
| G2-003 Album identity | P0 | **CLOSED** | Prior exact/canonical/ambiguity/Unicode fixes remain passing. |
| G2-004 year fallback | P1 | **CLOSED** | Durable structured fallback evidence remains passing. |
| G2-005 crash/idempotency | P1 | **PARTIAL** | Delivery calls are idempotent, but unresolved recovery appends unbounded duplicate journal entries under G2-012. |
| G2-006/G2-008 randomness provenance | P1 | **PARTIAL** | Per-run RNG is correct; direct mutable Config still permits behavior/fingerprint divergence under G2-011. |
| G2-007 equal-opportunity solver | P0 | **PARTIAL** | Complete-space probability is unbiased; formal bounded behavior remains open under G2-013. |
| G2-009 receipt binding | P0 | **PARTIAL** | `ok` mismatches enter recovery, but binding is not validated before failed-status classification under G2-012. |
| G2-010 parent plumbing | P1 | **PARTIAL** | Normal parent data path works; not every public Config construction path is immutable under G2-011. |
| G2-011 parent config validation/immutability | P1 | **PARTIAL / OPEN** | `load_config()` is safe, but public direct construction remains mutable. |
| G2-012 delivery ambiguity recovery | P1 | **PARTIAL / OPEN** | `ok` mismatch is recoverable, but misbound failed receipts terminalize and repeated recovery grows the journal. |
| G2-013 solver resource bounds | P1 | **PARTIAL / OPEN** | Terminal memo/cache improvements work, but the fast path does not match RunEngine input shape. |

## Open blocking findings

### [P1] G2-011 — Public `Config(...)` construction still bypasses the immutable snapshot

- Location: `src/omda/config.py:43-53` and `:98-110`; `src/omda/orchestrator/run.py:241-268`;
  `tests/unit/test_config.py`
- What is repaired:
  - `load_config()` validates dynamic parent values with precise paths;
  - config schema version is now 2;
  - `_from_dict()` makes a defensive `MappingProxyType` snapshot.
- Remaining evidence:
  - `Config.genre_parent_limits` still uses `field(default_factory=dict)` and the frozen
    dataclass has no `__post_init__` normalization.
  - `Config(genre_parent_limits={"p": 1}).genre_parent_limits["p"] = 2` succeeds.
  - Even `Config().genre_parent_limits["p"] = 2` succeeds.
  - `RunEngine` publicly accepts a `Config` directly, and integration tests construct it
    directly, so this is an actual supported entry path rather than an unreachable misuse.
  - The new immutability test covers only the result of `load_config()`, not direct Config
    construction. Therefore the prior fingerprint/behavior divergence remains reproducible
    through the public constructor.
- Impact: callers can mutate effective parent constraints after engine fingerprinting, so a
  journal can again claim a config version different from the selection rules actually used.
- Violated contract: Handoff Spec §5-§6; Implementation Plan T1.3/R-010; G2-011 acceptance
  requirement that every Config value used by the engine be a defensive immutable snapshot.
- Required correction: make every supported construction path normalize and freeze the map
  (for example in `Config.__post_init__`), or make direct construction unavailable and
  enforce the validated factory at the RunEngine boundary. A caller-owned mapping must
  never remain attached to Config. Direct invalid values must either be rejected there or
  demonstrably pass through the same validation boundary before `PLANNED`.
- Acceptance tests: construct `Config()` and `Config(genre_parent_limits=caller_dict)`
  directly; mutating either the original dict or the exposed mapping must not change Config.
  Construct a RunEngine from that direct Config and prove its journaled fingerprint equals
  the immutable rules used for selection.

### [P1] G2-012 — Receipt classification is still ordered incorrectly and recovery journaling is unbounded

- Location: `src/omda/orchestrator/run.py:474-529` and `:551-583`;
  `tests/integration/test_run_engine.py:330-367`, `:610-682`, and `:746-766`
- What is repaired: an `ok` receipt with wrong run/key/channel now enters `RECOVERING`, does
  not commit history, and repeated `run(run_id)` does not call Delivery again.
- Remaining evidence:
  - `_deliver_and_commit()` checks `receipt.status != "ok"` **before** checking whether the
    receipt belongs to the current run/key/channel.
  - The existing `FailedReceiptDelivery` returns `status="failed"` with `run_id=""` and
    `channel="fake"`, so it is not a confirmed failure for `run-1:markdown`; nevertheless the
    engine marks the run terminal `FAILED`.
  - An independent probe using this misbound failed receipt recorded one delivery call and a
    terminal FAILED tail. Only a correctly bound failed receipt can confirm current-run
    failure; a failed receipt for another operation is malformed/ambiguous evidence.
  - For an `ok` misbound receipt, five repeated `run("run-1")` calls caused no re-delivery
    but appended five separate identical `RECOVERING` entries. `MAX_RUN_ATTEMPTS` remains
    unused, so the durable retry path has no journal-growth bound.
  - A receipt-storage conflict after the external call is also terminalized as `FAILED`,
    although the external side effect/evidence relationship is ambiguous.
- Impact: some malformed receipts still hide possible delivery as ordinary failure, while a
  correctly recognized ambiguity can grow durable state indefinitely under retries.
- Violated contract: Handoff Spec §4 explicit recovery state and bounded idempotent retries;
  Implementation Plan I-10/T2.6 and R-001/R-009; G2-012 acceptance requirements.
- Required correction:
  - validate receipt binding/schema first, then interpret status;
  - only an exactly bound, valid `failed` receipt may become terminal FAILED;
  - any misbound/malformed receipt or conflicting evidence after the external call must enter
    the explicit recovery/manual-review path without history mutation or blind re-delivery;
  - repeated recovery of unchanged evidence must be durably idempotent or explicitly bounded,
    rather than appending the same state forever.
- Acceptance tests: cover bound-failed versus wrong-run/key/channel-failed receipts, receipt
  conflict after one recorded external effect, and at least five identical recovery calls;
  assert exact state, one delivery call, zero history, preserved anomaly evidence, and a
  bounded number of recovery journal entries.

### [P1] G2-013 — The solver fast path is still bypassed by normal RunEngine inputs

- Location: `src/omda/orchestrator/run.py:342-359`; `src/omda/core/genre.py:231-292`;
  `tests/property/test_genre_equality.py:147-194`
- What is repaired:
  - terminal states are no longer memoized;
  - the LRU retains at most four DP variants;
  - a direct call with exactly `{}` history and exactly `{}` family/parent limits enters the
    early `rng.sample` path.
- Remaining evidence:
  - RunEngine constructs `pick_history` with one key for **every** eligible Genre, even when
    every value is an empty tuple on the first-ever run. Therefore `not pick_history` is
    false and the advertised no-cooldown fast path is unreachable from the application.
  - RunEngine also uses `DEFAULT_FAMILY_LIMITS`; a nonempty configured limit keeps DP active
    even when no eligible Genre belongs to that limited family.
  - The new 200-Genre fast-path test passes a hand-built empty history and explicitly
    `family_limits={}`, unlike the normal Orchestrator path.
- Independent application-shape measurements with three picks, no actual cooldown, no
  active family/parent constraint, but `{genre_id: ()}` history:
  - 100 Genres: about 0.47 seconds and a DP cache entry;
  - 200 Genres: about 5.14 seconds and a DP cache entry;
  - with normal default-limit shape, 300 Genres still took about 19.2 seconds.
  These costs occur before one Genre sample is returned. No documented realistic maximum
  catalog size or constrained-path time/memory bound was added.
- Impact: the optimization proved in tests does not optimize OMDA's actual initial run;
  catalog growth still causes steep pre-sampling delay and can make repeated local operation
  impractical despite the “bounded solver” claim.
- Violated contract: Handoff Spec §2.3/§8; Implementation Plan T2.3/D.3; G2-013's explicit
  requirement to test realistic RunEngine-shaped inputs over multiple starts.
- Required correction: normalize semantically empty cooldown histories before fast-path
  selection, ignore configured family/parent limits that cannot apply to the current pool,
  and keep exact unbiasedness. For genuinely active constraints, document a supported upper
  pool bound and demonstrate stable time/memory behavior over multiple distinct histories,
  or use a compact counting method that meets that bound. Do not restore prefix truncation or
  probabilistic false insufficiency.
- Acceptance tests: use the exact mapping shape produced by RunEngine and a real orchestrated
  first run with a large pool; assert no DP construction when no constraint is semantically
  active. Add an active-constraint upper-bound test and verify the four-entry cache remains
  bounded across distinct starts.

## Acceptance matrix

| G2 criterion | Status | Evidence |
|---|---|---|
| T2.1 equal opportunity | **PASS** | Complete-space sampling remains unbiased. |
| T2.2 global cooldown/order | **PASS** | Prior global-index and boundary fixes remain passing. |
| T2.3 family/parent diversity and bounded result | **FAIL** | Semantics pass; application-shaped solver resource bound does not. |
| T2.4 Album identity/exclusion | **PASS** | Prior fixes remain passing. |
| T2.5 year/rating rules | **PASS** | Prior fixes remain passing. |
| T2.6 recoverable transaction | **PARTIAL** | `ok` mismatch recovers; failed mismatch/conflict and repeated recovery remain unsafe. |
| Config/schema boundary | **PARTIAL** | Loaded config is validated/frozen; direct Config remains mutable. |
| Determinism/provenance | **PARTIAL** | Per-run RNG passes; direct Config mutation can invalidate fingerprint evidence. |
| Core purity | **PASS** | Architecture tests pass. |
| No G3/G4 scope creep | **PASS** | Repair delta remains in G2/foundation support files. |
| Review package / Git evidence | **PASS** | Exact SHAs, repair report and test output are committed. |

## Checks performed and limitations

- Verified exact base/candidate/previous-Reviewer ancestry, branch, repair chain, clean
  worktree, and review package.
- Independently ran `pytest -q -p no:cacheprovider`: **239 passed**.
- Independently ran Ruff: **passed**.
- Ran `git diff --check`: **passed**.
- Re-ran loaded-config malformed-value and immutability behavior; those paths are repaired.
- Reproduced mutability through both `Config()` and direct Config with a caller map.
- Reproduced terminal FAILED for a misbound failed receipt after one delivery call.
- Reproduced five identical RECOVERING journal entries from five unchanged retry calls while
  confirming only one Delivery call and zero official history.
- Measured solver construction with exact RunEngine-style empty cooldown maps at 100/200
  Genres and the normal default-limit shape at 300 Genres.
- No production code, merge, tag, push, G3 work, live network, or external service was used.

## Required repair scope

Remain on `exec/g2-core`. Repair only the remaining construction-boundary immutability,
receipt classification/recovery idempotency, application-shaped solver fast path/resource
bound, focused regression tests, and stage-02 evidence. Do not alter product defaults,
reintroduce selection bias, weaken tests, merge, tag, or enter G3. No ADR is currently needed.

## Verdict

**CHANGES_REQUESTED**

Open blockers: G2-011 (P1), G2-012 (P1), G2-013 (P1), all PARTIAL. G2 must not be merged and
G3 must not begin. Acceptance applies only to a future exact candidate after independent
re-review.
